"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeRead, MonitorRead, RunStatus } from "../../../packages/shared/src";
import { ApiError, messageOf, monitorApi } from "./discovery";

function mergeChanges(previous: ChangeRead[], incoming: ChangeRead[], append: boolean): ChangeRead[] {
  const old = new Map(previous.map(e => [e.id, e]));
  const merged = new Map((append ? previous : []).map(e => [e.id, e]));
  for (const event of incoming) {
    const prior = old.get(event.id);
    merged.set(event.id, prior?.read_at && !event.read_at ? { ...event, read_at: prior.read_at } : event);
  }
  return Array.from(merged.values());
}

/** Server checks the source. This hook only reads status, never schedules checks. */
export function useMonitor(runId: string, runStatus: RunStatus) {
  const [monitor, setMonitor] = useState<MonitorRead | null>(null);
  const [changes, setChanges] = useState<ChangeRead[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const mutation = useRef<AbortController>();
  const pagination = useRef<AbortController>();
  const generation = useRef(0);
  const reset = useRef(runId);
  const expanded = useRef(false);
  const invalidate = useCallback(() => { generation.current++; }, []);

  useEffect(() => {
    if (reset.current !== runId) {
      reset.current = runId; expanded.current = false; setMonitor(null); setChanges([]); setCursor(null); setError(null); setNotice(null); setBusy(false);
    }
    return () => { invalidate(); mutation.current?.abort(); mutation.current = undefined; pagination.current?.abort(); pagination.current = undefined; };
  }, [runId, invalidate]);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = 15000;
    let keepPolling = true;
    const poll = async (): Promise<void> => {
      if (disposed || controller || document.hidden) return;
      if (mutation.current || pagination.current) { timer = setTimeout(() => void poll(), 15000); return; }
      const stamp = generation.current;
      controller = new AbortController(); setLoading(true);
      try {
        const result = await monitorApi.read(runId, controller.signal);
        const page = await monitorApi.changes(runId, controller.signal);
        if (disposed || stamp !== generation.current) return;
        setMonitor(result);
        setChanges(old => {
          const fresh = mergeChanges(old, page.items, false);
          return expanded.current ? [...fresh, ...old.filter(e => !page.items.some(item => item.id === e.id))] : fresh;
        });
        if (!expanded.current) setCursor(page.next_cursor);
        setError(null);
        keepPolling = result.enabled; delay = 15000;
      } catch (cause) {
        if (disposed || controller.signal.aborted || stamp !== generation.current) return;
        if (cause instanceof ApiError && cause.status === 404) { setMonitor(null); setError(null); keepPolling = false; }
        else { setError(messageOf(cause)); keepPolling = !(cause instanceof ApiError) || cause.retryable; delay = Math.min(60000, delay * 2); }
      } finally {
        controller = undefined;
        if (!disposed) { setLoading(false); if (keepPolling) timer = setTimeout(() => void poll(), delay); }
      }
    };
    const visible = (): void => {
      if (document.hidden) { clearTimeout(timer); controller?.abort(); }
      else if (!controller && keepPolling) { clearTimeout(timer); void poll(); }
    };
    void poll(); document.addEventListener("visibilitychange", visible);
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); document.removeEventListener("visibilitychange", visible); };
  }, [runId, runStatus, revision]);

  const perform = async (operation: (signal: AbortSignal) => Promise<MonitorRead | ChangeRead>, success: string): Promise<void> => {
    if (mutation.current) return;
    const controller = new AbortController(); mutation.current = controller;
    generation.current++; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await operation(controller.signal);
      if (controller.signal.aborted) return;
      if ("enabled" in result) setMonitor(result);
      else setChanges(previous => previous.map(e => e.id === result.id ? result : e));
      setNotice(success);
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally {
      if (!controller.signal.aborted) { mutation.current = undefined; setBusy(false); setRevision(value => value + 1); }
    }
  };

  const loadMore = async (): Promise<void> => {
    if (!cursor || pagination.current || mutation.current || loading) return;
    const controller = new AbortController(); pagination.current = controller;
    const stamp = generation.current; setLoading(true);
    try {
      const page = await monitorApi.changes(runId, controller.signal, cursor);
      if (!controller.signal.aborted && stamp === generation.current) {
        expanded.current = true;
        setChanges(old => mergeChanges(old, page.items, true)); setCursor(page.next_cursor); setError(null);
      }
    } catch (cause) { if (!controller.signal.aborted) setError(messageOf(cause)); }
    finally { if (!controller.signal.aborted) { pagination.current = undefined; setLoading(false); } }
  };

  return { monitor, changes, cursor, loading, busy, error, notice,
    refresh: () => setRevision(value => value + 1), loadMore,
    configure: (enabled: boolean, interval: number) => perform(signal => monitorApi.update(runId, {
      enabled, interval_seconds: interval, reanalyze_on_change: monitor?.reanalyze_on_change ?? false,
    }, signal), enabled ? "Monitoramento ativado. As checagens são processadas em segundo plano." : "Monitoramento desativado. O histórico foi preservado."),
    check: () => perform(signal => monitorApi.check(runId, signal), "Checagem solicitada. Aguarde o processamento em segundo plano; a última checagem abaixo informa quando ela ocorreu."),
    markRead: (id: string) => perform(signal => monitorApi.markRead(id, signal), "Aviso marcado como lido. Isso não atualiza as sugestões da análise."),
  };
}
