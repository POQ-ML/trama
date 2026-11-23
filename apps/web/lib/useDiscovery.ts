"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DiscoveryPage, FeedbackUpdate, RunRead, SuggestionRead } from "../../../packages/shared/src";
import { ApiError, discoveryApi, messageOf } from "./discovery";

import { diagnosisApi } from "./scopedDiscovery";
import { scopeIdentity, type SourceScope } from "./projectRoutes";

const terminal = (run: RunRead): boolean => !["queued", "running"].includes(run.status);
const validId = (value: string): boolean => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

/** Single owner for run polling, pagination and feedback. No overlapping reads. */
export function useDiscovery(source?: { scope: SourceScope; initialRun: RunRead | null; repoUrl: string }) {
  const projectId = source?.scope.projectId, sourceId = source?.scope.sourceId;
  const scopeKey = scopeIdentity(source?.scope);
  const api = useMemo(() => diagnosisApi(projectId && sourceId ? { projectId, sourceId } : undefined), [projectId, sourceId]);
  const [identity, setIdentity] = useState<{ scope: string; id: string | null }>({ scope: '', id: null });
  const currentScope = identity.scope === scopeKey;
  const runId = currentScope ? identity.id : null;
  const setRunId = (id: string): void => setIdentity({ scope: scopeKey, id });
  const generation = useRef(0);
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

  const initialRunId = source?.initialRun?.id ?? null;
  useEffect(() => {
    generation.current += 1;
    createController.current?.abort(); feedbackController.current?.abort(); pageController.current?.abort();
    createController.current = undefined; feedbackController.current = undefined; pageController.current = undefined;
    feedbackTimes.current.clear(); idempotency.current = undefined;
    setRun(null); setSuggestions([]); setTotal(0); setCursor(null); setError(null);
    setStarting(false); setSavingId(null); setFeedbackError(null); setFeedbackErrorId(null);
    const id = new URL(window.location.href).searchParams.get("run") ?? initialRunId;
    const valid = !!id && validId(id);
    setIdentity({ scope: scopeKey, id: valid ? id : null });
    setLoading(valid);
    if (id && !valid) setError("O identificador da análise é inválido. Confira o endereço.");
    return () => { createController.current?.abort(); feedbackController.current?.abort(); pageController.current?.abort(); };
  }, [scopeKey, initialRunId]);

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
      const stamp = generation.current;
      try {
        const page = await api.read(runId, active.signal);
        if (disposed || stamp !== generation.current) return;
        acceptPage(page, false); setError(null);
        finished = terminal(page.run);
        delay = Math.min(5000, Math.round(delay * 1.4));
      } catch (cause) {
        if (disposed || active.signal.aborted || stamp !== generation.current) return;
        setError(messageOf(cause));
        finished = cause instanceof ApiError && !cause.retryable;
        delay = Math.min(60000, delay * 2);
      } finally {
        active = undefined;
        if (!disposed && stamp === generation.current) { setLoading(false); schedule(); }
      }
    };
    const visible = (): void => {
      if (document.hidden) { clearTimeout(timer); active?.abort(); }
      else if (!active && !finished) { clearTimeout(timer); void poll(); }
    };
    void poll();
    document.addEventListener("visibilitychange", visible);
    return () => { disposed = true; clearTimeout(timer); active?.abort(); document.removeEventListener("visibilitychange", visible); };
  }, [runId, revision, acceptPage, api]);

  const start = async (repoUrl: string, reanalyzeId?: string): Promise<void> => {
    if (createController.current && !createController.current.signal.aborted) return;
    const controller = new AbortController(); createController.current = controller;
    setStarting(true); setError(null);
    try {
      if (!idempotency.current || idempotency.current.url !== repoUrl) {
        idempotency.current = { url: repoUrl, key: crypto.randomUUID() };
      }
      const next = await api.start(source?.repoUrl ?? repoUrl, idempotency.current.key, controller.signal, reanalyzeId);
      if (controller.signal.aborted) return;
      generation.current += 1;
      pageController.current?.abort(); feedbackController.current?.abort();
      feedbackTimes.current.clear(); setSuggestions([]); setTotal(0); setCursor(null);
      setRun(next); setFeedbackError(null); setSavingId(null);
      const url = new URL(window.location.href); url.searchParams.set("run", next.id);
      window.history.replaceState(null, "", url);
      setRunId(next.id);
      idempotency.current = undefined;
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally { if (!controller.signal.aborted) setStarting(false); if (createController.current === controller) createController.current = undefined; }
  };

  const loadMore = async (): Promise<void> => {
    if (!runId || !cursor || pageController.current || loading || (run && !terminal(run))) return;
    const id = runId; const controller = new AbortController(); pageController.current = controller; setLoading(true);
    try {
      const page = await api.read(id, controller.signal, cursor);
      if (!controller.signal.aborted && currentId.current === id) { acceptPage(page, true); setError(null); }
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally { if (pageController.current === controller) pageController.current = undefined; if (!controller.signal.aborted) setLoading(false); }
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
    finally { if (feedbackController.current === controller) feedbackController.current = undefined; if (!controller.signal.aborted) setSavingId(null); }
  };

  return { run: currentScope ? run : null, runId, suggestions: currentScope ? suggestions : [], total: currentScope ? total : 0, cursor: currentScope ? cursor : null,
    loading: !currentScope || loading, starting, error: currentScope ? error : null, feedbackError, feedbackErrorId, savingId,
    start, loadMore, feedback, reanalyze: () => run ? start(run.repo_url, run.id) : Promise.resolve(),
    refresh: () => setRevision(value => value + 1) };
}
