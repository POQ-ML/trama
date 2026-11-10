"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DiscoveryPage, FeedbackUpdate, RunRead, SuggestionRead } from "../../../packages/shared/src";
import { ApiError, discoveryApi, messageOf } from "./discovery";

const terminal = (run: RunRead): boolean => !["queued", "running"].includes(run.status);
const validId = (value: string): boolean => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

/** Single owner for run polling, pagination and feedback. No overlapping reads. */
export function useDiscovery() {
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunRead | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionRead[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackErrorId, setFeedbackErrorId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const createController = useRef<AbortController>();
  const feedbackController = useRef<AbortController>();
  const pageController = useRef<AbortController>();
  const currentId = useRef(runId);
  currentId.current = runId;
  const feedbackTimes = useRef(new Map<string, string>());
  const idempotency = useRef<{ url: string; key: string }>();

  useEffect(() => {
    const id = new URL(window.location.href).searchParams.get("run");
    if (id && validId(id)) setRunId(id);
    else if (id) setError("O identificador da análise é inválido. Inicie uma nova análise.");
    return () => { createController.current?.abort(); feedbackController.current?.abort(); pageController.current?.abort(); };
  }, []);

  const acceptPage = useCallback((page: DiscoveryPage, append: boolean) => {
    setRun(page.run); setTotal(page.total_suggestions); setCursor(page.next_cursor);
    setSuggestions(previous => {
      const merged = new Map((append ? previous : []).map(s => [s.id, s]));
      const oldById = new Map(previous.map(s => [s.id, s]));
      for (const incoming of page.suggestions) {
        // A read begun before a successful feedback mutation cannot overwrite it.
        const old = oldById.get(incoming.id);
        const feedbackTime = feedbackTimes.current.get(incoming.id);
        merged.set(incoming.id, old && feedbackTime && Date.parse(old.updated_at) >= Date.parse(incoming.updated_at) ? old : incoming);
      }
      return Array.from(merged.values());
    });
  }, []);

  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let active: AbortController | undefined;
    let delay = 1000;
    let finished = false;
    const schedule = (): void => { if (!disposed && !finished) timer = setTimeout(() => void poll(), delay); };
    const poll = async (): Promise<void> => {
      if (disposed || active || document.hidden) return;
      active = new AbortController();
      setLoading(true);
      try {
        const page = await discoveryApi.read(runId, active.signal);
        if (disposed) return;
        acceptPage(page, false); setError(null);
        finished = terminal(page.run);
        delay = Math.min(5000, Math.round(delay * 1.4));
      } catch (cause) {
        if (disposed || active.signal.aborted) return;
        setError(messageOf(cause));
        finished = cause instanceof ApiError && !cause.retryable;
        delay = Math.min(60000, delay * 2);
      } finally {
        active = undefined;
        if (!disposed) { setLoading(false); schedule(); }
      }
    };
    const visible = (): void => {
      if (document.hidden) { clearTimeout(timer); active?.abort(); }
      else if (!active && !finished) { clearTimeout(timer); void poll(); }
    };
    void poll();
    document.addEventListener("visibilitychange", visible);
    return () => { disposed = true; clearTimeout(timer); active?.abort(); document.removeEventListener("visibilitychange", visible); };
  }, [runId, revision, acceptPage]);

  const start = async (repoUrl: string, reanalyzeId?: string): Promise<void> => {
    if (createController.current && !createController.current.signal.aborted) return;
    const controller = new AbortController(); createController.current = controller;
    setStarting(true); setError(null);
    try {
      if (!idempotency.current || idempotency.current.url !== repoUrl) {
        idempotency.current = { url: repoUrl, key: crypto.randomUUID() };
      }
      const next = reanalyzeId
        ? await discoveryApi.reanalyze(reanalyzeId, controller.signal)
        : await discoveryApi.create(repoUrl, idempotency.current.key, controller.signal);
      if (controller.signal.aborted) return;
      pageController.current?.abort(); feedbackController.current?.abort();
      feedbackTimes.current.clear(); setSuggestions([]); setTotal(0); setCursor(null);
      setRun(next); setFeedbackError(null); setSavingId(null);
      const url = new URL(window.location.href); url.searchParams.set("run", next.id);
      window.history.replaceState(null, "", url);
      setRunId(next.id);
      idempotency.current = undefined;
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally { if (!controller.signal.aborted) setStarting(false); createController.current = undefined; }
  };

  const loadMore = async (): Promise<void> => {
    if (!runId || !cursor || pageController.current || loading || (run && !terminal(run))) return;
    const id = runId; const controller = new AbortController(); pageController.current = controller; setLoading(true);
    try {
      const page = await discoveryApi.read(id, controller.signal, cursor);
      if (!controller.signal.aborted && currentId.current === id) { acceptPage(page, true); setError(null); }
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally { pageController.current = undefined; if (!controller.signal.aborted) setLoading(false); }
  };

  const feedback = async (id: string, status: FeedbackUpdate["status"]): Promise<void> => {
    if (feedbackController.current) return;
    const controller = new AbortController(); feedbackController.current = controller;
    setSavingId(id); setFeedbackError(null); setFeedbackErrorId(id);
    try {
      const result = await discoveryApi.feedback(id, status, controller.signal);
      if (controller.signal.aborted) return;
      feedbackTimes.current.set(result.id, result.updated_at);
      setSuggestions(previous => previous.map(s => s.id === result.id ? { ...s, status: result.status, updated_at: result.updated_at } : s));
    } catch (cause) { if (!controller.signal.aborted) setFeedbackError(messageOf(cause)); }
    finally { feedbackController.current = undefined; if (!controller.signal.aborted) setSavingId(null); }
  };

  return { run, runId, suggestions, total, cursor, loading, starting, error, feedbackError, feedbackErrorId, savingId,
    start, loadMore, feedback, reanalyze: () => run ? start(run.repo_url, run.id) : Promise.resolve(),
    refresh: () => setRevision(value => value + 1) };
}
