"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, GitBranch, Network, Search } from "lucide-react";
import { useDiscovery } from "../lib/useDiscovery";
import { dateLabel, runLabel, sourceErrorLabel, sourceUrl, statusLabel, warningLabel, type MapSelection } from "../lib/discovery";
import { analysisLabel } from "../lib/readableAnalysis";
import ContextMap from "./ContextMap";
import SuggestionDetail from "./SuggestionDetail";
import SourceMonitor from "./SourceMonitor";
import { Button } from "./ui/button";

export default function DiscoveryWorkspace(): JSX.Element {
  const discovery = useDiscovery();
  const [repoUrl, setRepoUrl] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "map">("map");
  const [selection, setSelection] = useState<MapSelection | null>(null);
  const detailContainer = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  useEffect(() => { setSelection(null); }, [discovery.runId]);
  const { run, suggestions } = discovery;
  const busy = discovery.starting || !!run && ["queued", "running"].includes(run.status);
  const selected = selection && selection.kind !== "project" ? suggestions.find(s => s.id === selection.id) : undefined;

  const select = (next: MapSelection): void => {
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelection(next);
    requestAnimationFrame(() => {
      const heading = detailContainer.current?.querySelector<HTMLElement>("h2");
      heading?.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 1023px)").matches) heading?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
  };
  const close = (): void => { setSelection(null); trigger.current?.focus({ preventScroll: true }); };

  return <div className="space-y-8">
    <section className="grid items-end gap-8 lg:grid-cols-[1fr_440px]" aria-labelledby="hero-title">
      <div><p className="eyebrow mb-4">Uma ponte entre código e pesquisa</p>
        <h1 id="hero-title" className="max-w-2xl font-hand text-5xl leading-[1.05] sm:text-6xl">Seu próximo insight<br /><span className="hero-underline">pode estar num artigo.</span></h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted">Parta de um repositório público. Explore artigos que podem contribuir com o projeto e confira os trechos que sustentam cada conexão.</p>
      </div>
      <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-5 font-mono text-xs" aria-label="Fluxo: GitHub, conexões com evidência, OpenAlex">
        <div className="space-y-3"><GitBranch aria-hidden="true" size={24} /><p>GITHUB</p><p className="text-muted">Seu projeto</p></div>
        <div className="flex flex-col items-center gap-3"><span aria-hidden="true">······→······</span><span className="rounded-full border border-ink px-3 py-1 text-[10px]">EVIDÊNCIAS</span></div>
        <div className="space-y-3"><BookOpen aria-hidden="true" size={24} /><p>OPENALEX</p><p className="text-muted">Pesquisa aberta</p></div>
      </div>
    </section>

    <form id="discovery-form" className="rounded-md border-[1.5px] border-ink bg-surface p-5 shadow-solid-md sm:p-6"
      onSubmit={event => {
        event.preventDefault(); setFormError(null);
        try {
          const url = new URL(repoUrl.trim());
          if (url.protocol !== "https:" || url.hostname !== "github.com" || url.port || url.username || url.password || url.search || url.hash || !/^\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(url.pathname) || url.pathname.split("/").some(p => p === "." || p === "..")) throw new Error();
          void discovery.start(url.href.replace(/\/$/, ""));
        } catch { setFormError("Use uma URL como https://github.com/organizacao/projeto, sem parâmetros ou caminho de arquivo."); }
      }}>
      <label htmlFor="repo-url" className="mb-3 block font-medium">Qual projeto você quer explorar?</label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1"><GitBranch aria-hidden="true" className="absolute left-3 top-3.5 text-muted" size={20} />
          <input id="repo-url" name="repo_url" type="url" required value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="https://github.com/organizacao/projeto" autoCapitalize="none" autoCorrect="off" spellCheck={false}
            aria-describedby="repo-help repo-error" aria-invalid={!!formError} className="h-12 w-full rounded-md border border-border bg-bg pl-11 pr-3 text-sm" />
        </div>
        <Button type="submit" size="lg" className="h-12" disabled={busy}><Search size={17} aria-hidden="true" />{discovery.starting ? "Iniciando…" : "Encontrar conexões"}<ArrowRight size={17} aria-hidden="true" /></Button>
      </div>
      <p id="repo-help" className="mt-3 text-xs leading-relaxed text-muted">Apenas repositórios públicos · sem token GitHub · o tempo depende das fontes e da fila de processamento.</p>
      <div id="repo-error">{formError && <p role="alert" className="mt-2 text-sm">{formError}</p>}</div>
    </form>

    {discovery.error && <div className="notice" role="alert"><p>{discovery.error}</p><p className="mt-1 text-xs text-muted">Os dados já carregados continuam visíveis.</p>{discovery.runId && <Button variant="outline" size="sm" className="mt-3" disabled={discovery.loading} onClick={discovery.refresh}>Tentar atualizar</Button>}</div>}

    {run && <section className="rounded-md border border-border bg-surface p-5" aria-label="Andamento da análise">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="eyebrow">Sua análise</p><p className="mt-2 break-all text-sm font-medium">{run.repo_url.replace("https://github.com/", "")}</p></div>
        <p role="status" className="status-chip">{busy && <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-ink motion-reduce:animate-none" />}{runLabel[run.status]}</p>
      </div>
      <ol className="mt-5 grid grid-cols-3 gap-3 border-t border-border pt-4 text-xs text-muted" aria-label="Etapas">
        <li className="text-ink">01 · Projeto recebido</li><li className={run.status !== "queued" ? "text-ink" : ""}>02 · Buscar e relacionar</li><li className={["completed", "partial"].includes(run.status) ? "text-ink" : ""}>03 · Conferir evidências</li>
      </ol>
      <p className="mt-4 text-xs text-muted">Iniciada em {dateLabel(run.created_at)} · {run.finished_at ? `Finalizada em ${dateLabel(run.finished_at)}` : "Você pode recarregar esta página para recuperar o andamento."}</p>
      {(run.status === "partial" || run.status === "failed") && <p className="mt-3 text-sm">{run.status === "partial" ? "Resultados parciais preservados. " : ""}{sourceErrorLabel(run.error_code)}</p>}
      {run.warnings.length > 0 && <div className="mt-4 rounded-md border border-border bg-surface-muted p-3"><h3 className="text-sm font-medium">Ressalvas desta análise</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-muted">{Array.from(new Set(run.warnings)).map(warning => <li key={warning}>{warningLabel(warning)}</li>)}</ul></div>}
      {!busy && <Button variant="outline" size="sm" className="mt-4" onClick={() => void discovery.reanalyze()}>Reanalisar projeto</Button>}
    </section>}

    {run && <SourceMonitor key={run.id} run={run} reanalyzing={busy} onReanalyze={() => void discovery.reanalyze()} />}

    {!run && !discovery.loading && !discovery.starting && <section className="grid gap-4 sm:grid-cols-3" aria-label="Como explorar">
      {[
        ["01", "Comece pelo que está construindo", "O contexto vem do repositório público e do README disponível."],
        ["02", "Siga as conexões", "Leia a contribuição sugerida e os trechos do projeto e do artigo."],
        ["03", "Dê seu parecer", "Marque o que é relevante. Sua avaliação acompanha a relação."],
      ].map(([n, title, body]) => <div key={n} className="rounded-md border border-border p-5"><span className="eyebrow">{n}</span><h2 className="mt-4 font-hand text-2xl">{title}</h2><p className="mt-2 text-sm leading-relaxed text-muted">{body}</p></div>)}
    </section>}
    {discovery.loading && !run && <p role="status" className="notice">Recuperando sua análise…</p>}

    {run && <div className={`grid items-start gap-6 ${selection ? "lg:grid-cols-[minmax(0,1fr)_minmax(330px,390px)]" : "grid-cols-1"}`}>
      <section className="min-w-0" aria-labelledby="results-title" aria-busy={discovery.loading}>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div><p className="eyebrow">Explore as relações</p><h2 id="results-title" className="mt-2 font-hand text-3xl">Artigos & possibilidades <span className="text-xl text-muted">({discovery.total})</span></h2></div>
          <div className="flex gap-1 rounded-md border border-border bg-surface-tabs p-1" aria-label="Visualização dos resultados">
            <Button size="sm" variant={view === "list" ? "default" : "ghost"} aria-pressed={view === "list"} onClick={() => setView("list")}><BookOpen size={14} aria-hidden="true" />Lista</Button>
            <Button size="sm" variant={view === "map" ? "default" : "ghost"} aria-pressed={view === "map"} onClick={() => setView("map")}><Network size={14} aria-hidden="true" />Mapa</Button>
          </div>
        </div>
        {suggestions.length === 0 ? <div className="rounded-md border border-dashed border-border-dashed p-8 text-center"><BookOpen className="mx-auto mb-4" aria-hidden="true" /><h3 className="font-hand text-2xl">{busy ? "Costurando o contexto…" : run.status === "failed" ? "A análise precisa de outra tentativa" : run.status === "partial" ? "Sem conexões nesta análise parcial" : "Nenhuma conexão encontrada"}</h3><p className="mt-3 text-sm leading-relaxed text-muted">{busy ? "Os resultados aparecem conforme a análise avança. Não há uma estimativa de conclusão." : run.status === "failed" || run.status === "partial" ? "O processamento terminou com limitações, sem sugestões disponíveis. Confira o motivo acima e tente reanalisar o projeto." : "A busca terminou sem conexões com evidências suficientes. Isso não significa que não exista pesquisa relacionada ao projeto."}</p></div>
        : view === "map" && run.project ? <ContextMap project={run.project} suggestions={suggestions} totalSuggestions={discovery.total} selection={selection} onSelect={select} />
        : <ul className="space-y-3" aria-label="Artigos relacionados">{suggestions.map((s, index) => <li key={s.id}>
          <button type="button" onClick={() => select({ kind: "relationship", id: s.id })} aria-pressed={selected?.id === s.id} aria-controls="selection-panel"
            className={`result-card w-full rounded-md border bg-surface p-5 text-left ${selected?.id === s.id ? "border-ink shadow-solid-sm" : "border-border hover:border-ink"}`}>
            <span className="flex items-center justify-between gap-2"><span className="eyebrow">{String(index + 1).padStart(2, "0")} · OpenAlex</span><span className="status-chip">{statusLabel[s.status]}</span></span>
            <span className="mt-3 block text-base font-semibold leading-snug">{s.article.label}</span>
            <span className="mt-3 block text-sm leading-relaxed text-muted">{analysisLabel(s.justification)}. Abra os detalhes para ler a explicação completa.</span>
            <span className="mt-4 flex flex-wrap items-center gap-2">{s.topics.slice(0, 2).map(t => <span key={t.id} className="rounded border border-border px-2 py-1 text-[11px]">{t.label}</span>)}</span>
            <span className="mt-4 block text-xs font-medium underline underline-offset-4">Contribuição e evidências →</span>
          </button>
        </li>)}</ul>}
        {suggestions.length > 0 && <p className="mt-4 text-xs text-muted">{suggestions.length} de {discovery.total} conexões carregadas · ordem estável, não classificação por relevância.</p>}
        {discovery.cursor && <Button variant="outline" className="mt-4" disabled={discovery.loading || busy} onClick={() => void discovery.loadMore()}>{discovery.loading ? "Carregando…" : "Carregar mais artigos"}</Button>}
      </section>
      <div id="selection-panel" ref={detailContainer} className={selection ? "min-w-0" : "hidden"} onKeyDown={e => { if (e.key === "Escape") close(); }}>
        {selected ? <SuggestionDetail suggestion={selected} saving={discovery.savingId !== null} error={discovery.feedbackErrorId === selected.id ? discovery.feedbackError : null} onFeedback={status => void discovery.feedback(selected.id, status)} onClose={close} />
        : selection?.kind === "project" && run.project ? <section className="card"><h2 tabIndex={-1} className="font-hand text-3xl">{run.project.label}</h2><p className="text-sm text-muted">Projeto público do GitHub usado como origem das conexões.</p>{sourceUrl(run.project.original_url) && <a href={sourceUrl(run.project.original_url)} target="_blank" rel="noopener noreferrer" className="source-link">Abrir repositório ↗</a>}<Button variant="outline" onClick={close}>Fechar detalhes</Button></section>
        : <div className="rounded-md border border-dashed border-border-dashed bg-surface-muted p-8"><Network aria-hidden="true" size={28} /><h2 className="mt-5 font-hand text-3xl">Toda conexão tem uma história.</h2><p className="mt-3 text-sm leading-relaxed text-muted">Selecione um artigo ou uma aresta do mapa para explorar a contribuição, as fontes e as evidências dos dois lados.</p></div>}
      </div>
    </div>}
  </div>;
}
