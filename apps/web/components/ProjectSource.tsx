"use client";
import Link from 'next/link';
import { useProjectResource } from '../lib/useProjectResource';
import type { AcademicProjectDetail, ProjectSourceRead } from '../lib/projects';
import { projectHref, sourceHref, type SourceScope } from '../lib/projectRoutes';
import { sourceUrl } from '../lib/discovery';
import DiscoveryWorkspace from './DiscoveryWorkspace';
import { Button } from './ui/button';
export default function ProjectSource({scope}:{scope:SourceScope}): JSX.Element {
  const parent=useProjectResource<AcademicProjectDetail>(projectHref(scope.projectId));
  const state=useProjectResource<ProjectSourceRead>(sourceHref(scope));
  const source=state.data;
  const error=state.error || parent.error;
  return <div className="space-y-8"><nav aria-label="Caminho de navegação" className="flex flex-wrap gap-2 text-sm"><Link className="source-link" href="/">Projetos</Link><span aria-hidden="true">/</span><Link className="source-link" href={projectHref(scope.projectId)}>{parent.data?.name || 'Projeto acadêmico'}</Link><span aria-hidden="true">/</span><span>Fonte GitHub</span></nav>
    {(state.loading || parent.loading) && <p role="status" className="notice">Carregando fonte e última análise…</p>}
    {error && <div role="alert" className="notice"><p>{error}</p><Button className="mt-3" variant="outline" size="sm" disabled={state.loading || parent.loading} onClick={()=>{state.refresh();parent.refresh();}}>Tentar novamente</Button></div>}
    {source && parent.data && !error && <><header><p className="eyebrow">Fonte vinculada · GitHub</p><h1 className="mt-3 break-words font-hand text-4xl sm:text-5xl">{source.label}</h1>{sourceUrl(source.repo_url) && <a className="source-link mt-4 inline-block break-all" href={sourceUrl(source.repo_url)} target="_blank" rel="noopener noreferrer">{source.repo_url} ↗</a>}<p className="mt-4 max-w-3xl text-sm text-muted">Diagnóstico deste repositório. Análises, monitoramento e avaliações podem ser compartilhados com outros projetos que usam a mesma fonte.</p></header><DiscoveryWorkspace key={`${scope.projectId}/${scope.sourceId}`} source={{scope,repoUrl:source.repo_url,initialRun:source.latest_run}}/></>}
  </div>;
}
