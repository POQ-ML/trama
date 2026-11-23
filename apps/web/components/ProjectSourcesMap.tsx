"use client";
import { useState } from 'react';
import Link from 'next/link';
import { sourceHref } from '../lib/projectRoutes';
import { orbitLayout, MAP_WIDTH, MAP_HEIGHT, MAP_CENTER, ARTICLE_WIDTH, ARTICLE_HEIGHT } from '../lib/contextMapLayout';
import { Button } from './ui/button';

type SourceNode = { id: string; label: string };
export default function ProjectSourcesMap({ project, sources }: { project: { id: string; name: string }; sources: SourceNode[] }): JSX.Element {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(sources.length / 5));
  const current = Math.min(page, pages - 1);
  const visible = sources.slice(current * 5, (current + 1) * 5);
  const positions = orbitLayout(visible.length);
  return <section aria-label="Mapa de fontes do projeto acadêmico" className="overflow-hidden rounded-md border-[1.5px] border-ink bg-surface shadow-solid-md">
    <div className="border-b border-border p-5"><h2 className="font-hand text-3xl">Um projeto, suas fontes</h2><p className="mt-2 text-sm text-muted">Linhas contínuas indicam fontes vinculadas ao projeto. Selecione uma fonte para consultar seu diagnóstico. Deslize para explorar ou use a lista.</p></div>
    <div tabIndex={0} role="region" aria-label="Mapa navegável de fontes" className="overflow-auto bg-surface-muted" style={{maxHeight:650}}>
      <div className="relative" style={{width:MAP_WIDTH,height:MAP_HEIGHT,backgroundImage:'linear-gradient(#e5e5e5 1px,transparent 1px),linear-gradient(90deg,#e5e5e5 1px,transparent 1px)',backgroundSize:'24px 24px'}}>
        <svg aria-hidden="true" width={MAP_WIDTH} height={MAP_HEIGHT} className="absolute inset-0">
          {positions.map((p,i) => <g key={visible[i].id}><line x1={MAP_CENTER.x} y1={MAP_CENTER.y} x2={p.x} y2={p.y} stroke="currentColor" strokeWidth={2}/><rect x={p.labelX-51} y={p.labelY-11} width={102} height={22} fill="white" stroke="#d4d4d4"/><text x={p.labelX} y={p.labelY+4} textAnchor="middle" fontSize={11}>Fonte vinculada</text></g>)}
        </svg>
        <div className="absolute flex flex-col items-center justify-center rounded-full border-2 border-ink bg-ink p-5 text-center text-white shadow-solid-md" style={{left:MAP_CENTER.x-112,top:MAP_CENTER.y-112,width:224,height:224}}><span className="font-mono text-[10px] uppercase tracking-widest">Projeto acadêmico</span><h3 title={project.name} className="mt-3 line-clamp-4 max-w-full break-words font-hand text-2xl leading-tight">{project.name}</h3></div>
        {visible.map((s,i)=><Link key={s.id} href={sourceHref({projectId:project.id,sourceId:s.id})} aria-label={`Fonte GitHub ${s.label}. Abrir fonte e diagnóstico`} title={s.label} className="absolute rounded-md border-[1.5px] border-ink bg-surface p-4 shadow-solid-sm hover:bg-surface-muted" style={{left:positions[i].x-ARTICLE_WIDTH/2,top:positions[i].y-ARTICLE_HEIGHT/2,width:ARTICLE_WIDTH,height:ARTICLE_HEIGHT}}><span className="eyebrow">Fonte · GitHub</span><span className="mt-3 line-clamp-3 break-words font-semibold">{s.label}</span><span className="mt-3 block text-xs underline underline-offset-4">Abrir fonte e diagnóstico →</span></Link>)}
      </div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-4 text-xs"><p>{visible.length} fontes visíveis · {sources.length} carregadas. Posição e distância apenas organizam a navegação; vínculos não representam relevância descoberta.</p><div className="flex items-center gap-3"><Button size="sm" variant="outline" disabled={current===0} onClick={()=>setPage(current-1)} aria-label="Página anterior de fontes">←</Button><span>{current+1} / {pages}</span><Button size="sm" variant="outline" disabled={current+1>=pages} onClick={()=>setPage(current+1)} aria-label="Próxima página de fontes">→</Button></div></div>
  </section>;
}
