"use client";
import Link from 'next/link';
import type { ProjectActivityRead } from '../lib/projects';
import { projectHref, sourceHref } from '../lib/projectRoutes';
import { dateLabel } from '../lib/discovery';
import { useProjectResource } from '../lib/useProjectResource';
import { Button } from './ui/button';
export default function ProjectActivity(): JSX.Element | null {
  const state=useProjectResource<ProjectActivityRead[]>('/projects/activity');
  if(state.error)return <div className="notice" role="alert"><p>Não foi possível consultar as mudanças recentes.</p><Button className="mt-2" variant="outline" size="sm" disabled={state.loading} onClick={state.refresh}>Tentar atualizar mudanças</Button></div>;
  if(!state.data?.length)return null;
  return <section aria-labelledby="activity-title"><h2 id="activity-title" className="font-hand text-3xl">Mudanças recentes nas fontes</h2><p className="mt-2 text-xs text-muted">Até dez registros de mudanças detectadas. Um aviso pode corresponder a contexto já reanalisado.</p><ul className="mt-5 space-y-3">{state.data.map(event=><li key={`${event.project_id}/${event.source_id}/${event.id}`} className="rounded-md border border-border bg-surface p-4"><div className="flex flex-wrap items-center justify-between gap-2"><Link className="source-link break-words font-medium" href={sourceHref({projectId:event.project_id,sourceId:event.source_id})}>{event.source_label}</Link><span className="status-chip">{event.read_at?'Lido':'Não lido'}</span></div><p className="mt-2 text-xs text-muted">Mudança detectada · {dateLabel(event.observed_at)}</p><Link className="source-link mt-3 inline-block text-xs" href={projectHref(event.project_id)}>Projeto: {event.project_name}</Link></li>)}</ul></section>;
}
