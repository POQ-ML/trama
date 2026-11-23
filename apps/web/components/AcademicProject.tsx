"use client";
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useProjectResource } from '../lib/useProjectResource';
import { githubRepoUrl, projectMessage, projectsApi, type AcademicProjectDetail } from '../lib/projects';
import { projectHref, sourceHref } from '../lib/projectRoutes';
import { runLabel } from '../lib/discovery';
import ProjectSourcesMap from './ProjectSourcesMap';
import { Button } from './ui/button';

export default function AcademicProject({projectId}:{projectId:string}): JSX.Element {
  const state=useProjectResource<AcademicProjectDetail>(projectHref(projectId));
  const [repo,setRepo]=useState(''),[view,setView]=useState<'map'|'list'>('map');
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
  const mutation=useRef<AbortController>();
  useEffect(()=>()=>mutation.current?.abort(),[]);
  const project=state.data;
  return <div className="space-y-8"><nav aria-label="Caminho de navegação" className="text-sm"><Link className="source-link" href="/">Projetos</Link><span aria-hidden="true"> / </span><span>Projeto acadêmico</span></nav>
    {state.loading && <p role="status" className="notice">Carregando projeto e fontes…</p>}
    {state.error && <div role="alert" className="notice"><p>{state.error}</p><Button className="mt-3" size="sm" variant="outline" disabled={state.loading} onClick={state.refresh}>Tentar novamente</Button></div>}
    {project && <><header className="flex flex-wrap items-end justify-between gap-5"><div className="min-w-0"><p className="eyebrow">Projeto acadêmico</p><h1 className="mt-3 break-words font-hand text-5xl">{project.name}</h1><p className="mt-4 max-w-3xl whitespace-pre-wrap break-words text-muted">{project.description || 'Sem descrição.'}</p></div><a href="#add-source" className="source-link">Adicionar fonte →</a></header>
    <section aria-labelledby="sources-title"><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><h2 id="sources-title" className="font-hand text-3xl">Fontes do projeto ({project.source_count})</h2><div className="flex gap-1 rounded-md border border-border bg-surface-tabs p-1" aria-label="Visualização das fontes"><Button size="sm" variant={view==='map'?'default':'ghost'} aria-pressed={view==='map'} onClick={()=>setView('map')}>Mapa</Button><Button size="sm" variant={view==='list'?'default':'ghost'} aria-pressed={view==='list'} onClick={()=>setView('list')}>Lista</Button></div></div>
      {!project.sources.length ? <div className="rounded-md border border-dashed border-border-dashed p-8"><h3 className="font-hand text-3xl">Reúna as fontes desta pesquisa.</h3><p className="mt-3 text-sm text-muted">Adicione um repositório público do GitHub. Você poderá iniciar o diagnóstico na página da fonte.</p></div> : view==='map' ? <ProjectSourcesMap project={project} sources={project.sources}/> : <ul className="grid gap-4 sm:grid-cols-2">{project.sources.map(s=><li key={s.id}><Link href={sourceHref({projectId,sourceId:s.id})} className="block h-full rounded-md border border-border bg-surface p-5 hover:border-ink"><span className="eyebrow">Fonte vinculada · GitHub</span><h3 className="mt-3 break-words font-semibold">{s.label}</h3><p className="mt-2 break-all text-xs text-muted">{s.repo_url}</p><p className="mt-4 text-sm">{s.latest_run?runLabel[s.latest_run.status]:'Ainda não analisada'}</p><span className="source-link mt-3 inline-block text-xs">Abrir fonte e diagnóstico →</span></Link></li>)}</ul>}
      <p className="mt-4 text-xs text-muted">O mesmo repositório pode estar em vários projetos e compartilhar análises, monitoramento e avaliações.</p>
    </section>
    <form id="add-source" aria-labelledby="add-source-title" className="rounded-md border-[1.5px] border-ink bg-surface p-6 shadow-solid-md" onSubmit={async event=>{
      event.preventDefault();if(mutation.current)return;
      let repoUrl:string;try{repoUrl=githubRepoUrl(repo);}catch{setError('Use https://github.com/organizacao/repositorio, sem caminhos de arquivo ou parâmetros.');return;}
      const controller=new AbortController();mutation.current=controller;setBusy(true);setError(null);setNotice(null);
      try{await projectsApi.addSource(projectId,repoUrl,controller.signal);if(!controller.signal.aborted){setRepo('');setNotice('Fonte adicionada. Abra a fonte para iniciar ou consultar sua análise.');state.refresh();}}
      catch(cause){if(!controller.signal.aborted)setError(projectMessage(cause));}
      finally{if(mutation.current===controller)mutation.current=undefined;if(!controller.signal.aborted)setBusy(false);}
    }}><h2 id="add-source-title" className="font-hand text-3xl">Adicionar fonte</h2><p className="mt-3 text-sm text-muted">Adicione um repositório público. A análise será iniciada por você na página da fonte.</p>
      <label htmlFor="source-type" className="mt-5 block text-sm font-medium">Tipo de fonte</label><select id="source-type" name="source_type" defaultValue="github" disabled={busy} className="mt-2 block h-11 w-full rounded-md border border-border bg-bg px-3 text-sm"><option value="github">GitHub</option></select>
      <label htmlFor="source-repo" className="mt-5 block text-sm font-medium">URL do repositório GitHub</label><div className="mt-2 flex flex-col gap-3 sm:flex-row"><input id="source-repo" type="url" required autoCapitalize="none" spellCheck={false} value={repo} disabled={busy} onChange={e=>setRepo(e.target.value)} placeholder="https://github.com/organizacao/repositorio" className="h-11 min-w-0 flex-1 rounded-md border border-border bg-bg px-3 text-sm"/><Button type="submit" disabled={busy}>{busy?'Adicionando…':'Adicionar fonte'}</Button></div>{error && <p role="alert" className="mt-3 text-sm">{error}</p>}{notice && <p role="status" className="mt-3 text-sm">{notice}</p>}</form></>}
  </div>;
}
