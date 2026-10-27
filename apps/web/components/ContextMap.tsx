"use client";

import { useEffect, useId, useRef, useState } from "react";
import { GitBranch, Minus, Plus, RotateCcw } from "lucide-react";
import type { ProjectRead, SuggestionRead } from "../../../packages/shared/src";
import { type MapSelection } from "../lib/discovery";
import { ARTICLE_HEIGHT, ARTICLE_WIDTH, MAP_CENTER, MAP_HEIGHT, MAP_PAGE_SIZE, MAP_WIDTH, orbitLayout } from "../lib/contextMapLayout";
import { Button } from "./ui/button";

interface Props {
  project: ProjectRead;
  suggestions: SuggestionRead[];
  totalSuggestions: number;
  selection: MapSelection | null;
  onSelect: (selection: MapSelection) => void;
}

const labels = { pending: "A avaliar", confirmed: "Avaliado como relevante", rejected: "Avaliado como não relevante" } as const;
type Filter = "all" | SuggestionRead["status"];

export default function ContextMap({ project, suggestions, totalSuggestions, selection, onSelect }: Props): JSX.Element {
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState(1);
  const viewport = useRef<HTMLDivElement>(null);
  const uid = useId();
  const filtered = suggestions.filter(s => filter === "all" || s.status === filter);
  const pages = Math.max(1, Math.ceil(filtered.length / MAP_PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(currentPage * MAP_PAGE_SIZE, (currentPage + 1) * MAP_PAGE_SIZE);
  const positions = orbitLayout(visible.length);
  const scale = fit * zoom;
  const selectedId = selection && selection.kind !== "project" ? selection.id : null;
  const selectedOutside = selectedId !== null && !visible.some(s => s.id === selectedId);

  const center = (): void => {
    const element = viewport.current;
    if (element) element.scrollTo({ left: (MAP_WIDTH * scale - element.clientWidth) / 2, top: (MAP_HEIGHT * scale - element.clientHeight) / 2, behavior: "auto" });
  };

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setFit(Math.max(.85, Math.min(1, (entry.contentRect.width - 16) / MAP_WIDTH, (entry.contentRect.height - 16) / MAP_HEIGHT))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = viewport.current;
    if (element) element.scrollTo({ left: (MAP_WIDTH * scale - element.clientWidth) / 2, top: (MAP_HEIGHT * scale - element.clientHeight) / 2, behavior: "auto" });
  }, [scale, currentPage, filter]);

  return <section className="context-map-shell" aria-labelledby={`${uid}-title`}>
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border bg-surface px-5 py-4">
      <div><p className="eyebrow">Projeto analisado em contexto</p><h3 id={`${uid}-title`} className="mt-1 font-hand text-3xl">Mapa de conexões</h3><p className="mt-1 text-xs text-muted">Projeto → artigo · associações sugeridas, a avaliar com as evidências.</p></div>
      <div className="flex items-center gap-1" aria-label="Zoom do mapa">
        <Button size="icon" variant="ghost" aria-label="Diminuir zoom" disabled={zoom <= .8} onClick={() => setZoom(value => Math.max(.8, +(value - .1).toFixed(1)))}><Minus size={17} aria-hidden="true" /></Button>
        <span className="w-12 text-center font-mono text-xs" aria-live="polite">{Math.round(zoom * 100)}%</span>
        <Button size="icon" variant="ghost" aria-label="Aumentar zoom" disabled={zoom >= 1.4} onClick={() => setZoom(value => Math.min(1.4, +(value + .1).toFixed(1)))}><Plus size={17} aria-hidden="true" /></Button>
        <Button size="sm" variant="outline" aria-label="Restaurar zoom e centralizar projeto" onClick={() => { setZoom(1); center(); }}><RotateCcw size={14} aria-hidden="true" />Restaurar</Button>
      </div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg px-5 py-3">
      <label className="flex items-center gap-2 text-xs">Avaliações no mapa
        <select value={filter} onChange={event => { setFilter(event.target.value as Filter); setPage(0); }} className="min-h-10 max-w-[220px] rounded-md border border-border bg-surface px-2 text-xs">
          <option value="all">Todas</option><option value="pending">A avaliar</option><option value="confirmed">Avaliadas como relevantes</option><option value="rejected">Avaliadas como não relevantes</option>
        </select>
      </label>
      <p className="font-mono text-[11px] text-muted" role="status">{visible.length} artigos visíveis · {suggestions.length} carregados de {totalSuggestions}</p>
    </div>
    <p id={`${uid}-instructions`} className="border-b border-border bg-surface px-5 py-3 text-xs leading-relaxed text-muted">Selecione o projeto, um artigo ou uma conexão numerada. Use Tab e Enter; Escape fecha o detalhe. Deslize o mapa para explorar ou escolha a visualização Lista.</p>
    <div ref={viewport} tabIndex={0} role="region" aria-label="Área navegável do mapa" aria-describedby={`${uid}-instructions`} className="context-map-viewport map-grid">
      <div className="context-map-stage" style={{ width: MAP_WIDTH * scale, height: MAP_HEIGHT * scale }}>
        <div className="context-map-world" style={{ width: MAP_WIDTH, height: MAP_HEIGHT, transform: `scale(${scale})` }}>
          <svg width={MAP_WIDTH} height={MAP_HEIGHT} role="group" aria-label="Conexões do projeto com os artigos" className="absolute inset-0">
            <defs><marker id={`${uid}-arrow`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="var(--ink)" /></marker></defs>
            <g aria-hidden="true" className="context-map-orbits"><ellipse cx={MAP_CENTER.x} cy={MAP_CENTER.y} rx={350} ry={280} /><circle cx={MAP_CENTER.x} cy={MAP_CENTER.y} r={112} /></g>
            {visible.map((s, index) => {
              const p = positions[index];
              const path = `M${p.startX} ${p.startY} L${p.endX} ${p.endY}`;
              const selected = s.id === selectedId;
              return <g key={s.id}>
                {selected && <path aria-hidden="true" d={path} stroke="var(--ink)" strokeWidth={12} opacity={.08} />}
                <path aria-hidden="true" d={path} fill="none" stroke={s.status === "rejected" ? "var(--muted)" : "var(--ink)"} strokeWidth={selected ? 3 : 1.5} strokeDasharray={s.status === "pending" ? "6 5" : s.status === "rejected" ? "2 5" : undefined} markerEnd={`url(#${uid}-arrow)`} />
                <circle aria-hidden="true" cx={p.labelX} cy={p.labelY} r={14} fill="var(--surface)" stroke="var(--border)" />
                <text aria-hidden="true" x={p.labelX} y={p.labelY + 4} textAnchor="middle" fontSize={10} fill="var(--ink)" fontFamily="monospace">{currentPage * MAP_PAGE_SIZE + index + 1}</text>
                <path d={path} fill="none" stroke="transparent" strokeWidth={52} role="button" tabIndex={0} className="context-map-edge" aria-controls="selection-panel" aria-pressed={selection?.kind === "relationship" && selected} aria-label={`Conexão ${currentPage * MAP_PAGE_SIZE + index + 1} com ${s.article.label} · ${labels[s.status]}`} onClick={() => onSelect({ kind: "relationship", id: s.id })} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect({ kind: "relationship", id: s.id }); } }} />
              </g>;
            })}
          </svg>
          <button type="button" aria-label={`Projeto analisado · GitHub · ${project.label}`} aria-pressed={selection?.kind === "project"} aria-controls="selection-panel" className="context-map-hub" style={{ left: MAP_CENTER.x - 92, top: MAP_CENTER.y - 92 }} onClick={() => onSelect({ kind: "project" })}>
            <GitBranch size={22} aria-hidden="true" /><span className="font-mono text-[9px] uppercase tracking-wider">Projeto analisado · GitHub</span><span className="break-words font-hand text-[21px] leading-tight">{project.label}</span>
          </button>
          {visible.map((s, index) => <button type="button" key={s.id} aria-label={`Artigo ${currentPage * MAP_PAGE_SIZE + index + 1} · OpenAlex · ${s.article.label} · ${labels[s.status]}`} aria-pressed={selection?.kind === "article" && selectedId === s.id} aria-controls="selection-panel" className={`context-map-article ${selectedId === s.id ? "context-map-selected" : ""}`} style={{ left: positions[index].x - ARTICLE_WIDTH / 2, top: positions[index].y - ARTICLE_HEIGHT / 2, width: ARTICLE_WIDTH, height: ARTICLE_HEIGHT }} onClick={() => onSelect({ kind: "article", id: s.id })}>
            <span className="flex items-center justify-between gap-2"><span className="eyebrow">{String(currentPage * MAP_PAGE_SIZE + index + 1).padStart(2, "0")} · Artigo · OpenAlex</span><span className={`context-map-state context-map-state-${s.status}`} aria-hidden="true">{s.status === "confirmed" ? "✓" : s.status === "rejected" ? "×" : "?"}</span></span>
            <span className="context-map-article-title">{s.article.label}</span>
            <span className="mt-auto block text-[11px] font-medium">{labels[s.status]}</span>
            <span className="context-map-topic" title={s.topics[0]?.label}>Classificação OpenAlex: {s.topics[0]?.label ?? "não disponível"}</span>
          </button>)}
        </div>
      </div>
    </div>
    {visible.length === 0 && <p role="status" className="border-t border-border bg-surface px-5 py-3 text-sm">Nenhum artigo carregado corresponde a esta avaliação. Troque o filtro ou consulte a lista.</p>}
    {selectedOutside && <p role="status" className="border-t border-border px-5 py-3 text-xs text-muted">A conexão em detalhe está fora desta página ou filtro do mapa.</p>}
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-5 py-3">
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-[11px]" aria-label="Legenda das avaliações humanas">
        <span className="flex items-center gap-2"><i className="context-map-swatch context-map-pending" aria-hidden="true" />A avaliar</span>
        <span className="flex items-center gap-2"><i className="context-map-swatch" aria-hidden="true" />Avaliado como relevante</span>
        <span className="flex items-center gap-2"><i className="context-map-swatch context-map-rejected" aria-hidden="true" />Avaliado como não relevante</span>
      </div>
      <div className="flex items-center gap-2"><Button variant="ghost" size="sm" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} aria-label="Página anterior de artigos no mapa">←</Button><span className="font-mono text-[11px]">{currentPage + 1} / {pages}</span><Button variant="ghost" size="sm" disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)} aria-label="Próxima página de artigos no mapa">→</Button></div>
    </div>
    <p className="border-t border-border bg-bg px-5 py-3 text-xs leading-relaxed text-muted">Linhas indicam associações sugeridas e avaliação humana, não uso comprovado. Posição, distância e tamanho apenas organizam o mapa; não representam score. Temas são classificações OpenAlex do artigo.</p>
  </section>;
}
