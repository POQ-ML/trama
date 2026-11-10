"use client";

import { useEffect, useState } from "react";
import type { RunRead } from "../../../packages/shared/src";
import { useMonitor } from "../lib/useMonitor";
import { dateLabel, sourceErrorLabel } from "../lib/discovery";
import { Button } from "./ui/button";
import { Bell, RefreshCw } from "lucide-react";

export default function SourceMonitor({ run, reanalyzing, onReanalyze }: { run: RunRead; reanalyzing: boolean; onReanalyze: () => void }): JSX.Element {
  const state = useMonitor(run.id, run.status);
  const [interval, setInterval] = useState(300);
  const { monitor } = state;
  const configuredInterval = monitor?.interval_seconds;
  useEffect(() => { if (configuredInterval !== undefined) setInterval(configuredInterval); }, [configuredInterval]);
  const oldRun = monitor && monitor.latest_run_id !== run.id;
  const unread = state.changes.filter(e => !e.read_at);
  return <section aria-labelledby="monitor-title" className="rounded-md border border-border bg-surface p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="eyebrow flex items-center gap-2"><Bell size={14} aria-hidden="true" />Acompanhe o contexto</p><h2 id="monitor-title" className="mt-2 font-hand text-3xl">Quando a fonte muda, vale olhar de novo.</h2></div>
      <span className="status-chip">{monitor ? monitor.enabled ? "Monitoramento ativo" : "Monitoramento desativado" : state.error ? "Estado indisponível" : state.loading ? "Consultando estado" : "Não configurado"}</span>
    </div>
    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">Acompanha mudanças no contexto público coletado do repositório e do README, não em todos os commits. As checagens são periódicas, em segundo plano.</p>

    {(monitor?.stale || oldRun || unread.length > 0) && <div className="notice mt-5 border-l-4" role="status">
      <h3 className="font-semibold">{oldRun ? "Você está vendo uma análise anterior" : monitor?.stale ? "A fonte mudou: sugestões podem estar antigas" : "Há avisos de mudança para revisar"}</h3>
      <p className="mt-2 text-sm">{oldRun ? "Já existe outra análise para esta fonte. As evidências desta página pertencem à execução anterior." : monitor?.stale ? "Confira o contexto atual com uma nova análise. As evidências anteriores ficam preservadas." : "Consulte o histórico abaixo. Esses avisos podem corresponder a mudanças já reanalisadas."}</p>
      {oldRun && <a className="source-link mt-3 inline-block" href={`?run=${encodeURIComponent(monitor.latest_run_id)}`}>Abrir análise mais recente →</a>}
      {(monitor?.stale || oldRun) && <div><Button className="mt-3" variant={oldRun ? "outline" : "default"} size="sm" disabled={reanalyzing} onClick={onReanalyze}><RefreshCw size={14} aria-hidden="true" />{reanalyzing ? "Análise em andamento…" : "Reanalisar contexto atual"}</Button></div>}
    </div>}

    <div className="mt-5 flex flex-wrap items-end gap-3">
      <label className="text-xs font-medium">Intervalo solicitado
        <select value={interval} onChange={e => setInterval(Number(e.target.value))} disabled={state.busy} className="mt-2 block h-10 rounded-md border border-border bg-bg px-3 text-sm">
          <option value={60}>1 minuto</option><option value={300}>5 minutos</option><option value={900}>15 minutos</option><option value={3600}>1 hora</option><option value={86400}>24 horas</option>
          {![60, 300, 900, 3600, 86400].includes(interval) && <option value={interval}>{interval} segundos</option>}
        </select>
      </label>
      <Button variant="outline" disabled={state.busy || state.loading || !run.project} onClick={() => void state.configure(!monitor?.enabled, monitor?.enabled ? monitor.interval_seconds : interval)}>
        {state.busy ? "Salvando…" : monitor?.enabled ? "Desativar monitoramento" : "Ativar monitoramento"}
      </Button>
      {monitor?.enabled && <Button variant="ghost" disabled={state.busy || state.loading} onClick={() => void state.configure(true, interval)}>Aplicar intervalo</Button>}
      {monitor && <Button variant="ghost" disabled={state.busy || state.loading || !monitor.enabled} onClick={() => void state.check()}>Checar agora</Button>}
    </div>
    {!run.project && <p className="mt-3 text-xs text-muted">Disponível quando a análise tiver identificado o projeto.</p>}
    {monitor && <>
      <p className="mt-3 text-xs text-muted">Intervalo configurado: {monitor.interval_seconds} segundos. A fila pode atrasar uma checagem. Reanálise automática {monitor.reanalyze_on_change ? "ativada na configuração existente" : "desativada"}.</p>
      <dl className="mt-5 grid gap-4 border-t border-border pt-4 text-xs sm:grid-cols-3">
        <div><dt className="text-muted">Última checagem</dt><dd className="mt-1">{dateLabel(monitor.last_checked_at)}</dd></div>
        <div><dt className="text-muted">Última mudança detectada</dt><dd className="mt-1">{dateLabel(monitor.last_changed_at)}</dd></div>
        <div><dt className="text-muted">Próxima checagem prevista</dt><dd className="mt-1">{monitor.enabled ? dateLabel(monitor.next_check_at) : "Monitoramento pausado"}</dd></div>
      </dl>
      {monitor.error_code && <p className="mt-3 text-sm" role="status">{sourceErrorLabel(monitor.error_code)} O contexto anterior foi preservado.</p>}
    </>}
    {state.notice && <p className="mt-4 text-sm" role="status">{state.notice}</p>}
    {state.error && <div className="notice mt-4" role="alert"><p>{state.error}</p><Button size="sm" variant="outline" className="mt-2" disabled={state.loading} onClick={state.refresh}>Atualizar monitor</Button></div>}
    {state.loading && !monitor && <p role="status" className="mt-3 text-xs text-muted">Consultando monitoramento…</p>}
    {monitor && <details className="mt-5 border-t border-border pt-4">
      <summary className="text-sm font-medium">Histórico de mudanças {unread.length > 0 ? `· ${unread.length} avisos não lidos carregados` : ""}</summary>
      {!state.changes.length && <p className="mt-3 text-sm text-muted">Nenhuma mudança registrada até o momento.</p>}
      <ul className="mt-4 space-y-3">{state.changes.map(event => <li key={event.id} className="rounded-md border border-border p-3 text-xs">
        <p className="font-medium">Contexto da fonte alterado · {dateLabel(event.observed_at)}</p>
        <details className="mt-2 text-muted"><summary>Comparar versões coletadas</summary><dl className="mt-2 space-y-2 break-all"><div><dt>Anterior</dt><dd className="font-mono">{event.previous_hash}</dd></div><div><dt>Atual</dt><dd className="font-mono">{event.current_hash}</dd></div></dl></details>
        {event.read_at ? <p className="mt-2 text-muted">Lido em {dateLabel(event.read_at)}</p> : <Button size="sm" variant="outline" className="mt-3" disabled={state.busy} onClick={() => void state.markRead(event.id)}>Marcar aviso como lido</Button>}
      </li>)}</ul>
      {state.cursor && <Button size="sm" variant="outline" className="mt-4" disabled={state.busy || state.loading} onClick={() => void state.loadMore()}>Carregar mais mudanças</Button>}
    </details>}
  </section>;
}
