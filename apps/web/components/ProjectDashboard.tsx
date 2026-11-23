"use client";
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Folder, Plus, ArrowRight } from 'lucide-react';
import { useProjectResource } from '../lib/useProjectResource';
import { projectsApi, projectMessage, type AcademicProjectRead } from '../lib/projects';
import { projectHref } from '../lib/projectRoutes';
import ProjectActivity from './ProjectActivity';
import { Button } from './ui/button';

export default function ProjectDashboard(): JSX.Element {
  const state=useProjectResource<AcademicProjectRead[]>('/projects');
  const [name,setName]=useState(''),[description,setDescription]=useState('');
  const [creating,setCreating]=useState(false),[error,setError]=useState<string|null>(null);
  const mutation=useRef<AbortController>();
  const router=useRouter();
  useEffect(()=>()=>mutation.current?.abort(),[]);
  return <div className="space-y-8">
    <header className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">Seu espaço de pesquisa</p><h1 className="mt-3 font-hand text-5xl">Projetos acadêmicos</h1><p className="mt-4 max-w-2xl text-muted">Organize um objetivo, reúna suas fontes e explore as conexões de cada repositório com a literatura científica.</p></div><a className="source-link" href="#new-project"><Plus size={16} className="mr-2 inline" aria-hidden="true"/>Criar projeto</a></header>
    <p className="text-xs text-muted">Espaço local compartilhado, sem contas individuais. As fontes e avaliações não são privadas por projeto.</p>
    <section aria-labelledby="projects-title"><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><h2 id="projects-title" className="font-hand text-3xl">Projetos {state.data && <span className="text-xl text-muted">({state.data.length})</span>}</h2>{state.data && <p className="text-xs text-muted">{state.data.reduce((n,p)=>n+p.source_count,0)} vínculos com fontes</p>}</div>
      {state.loading && <p role="status" className="notice">Carregando projetos…</p>}
      {state.error && <div role="alert" className="notice"><p>{state.error}</p><Button variant="outline" size="sm" className="mt-3" onClick={state.refresh} disabled={state.loading}>Tentar novamente</Button></div>}
      {state.data?.length===0 && <div className="rounded-md border border-dashed border-border-dashed p-8"><Folder aria-hidden="true"/><h3 className="mt-4 font-hand text-3xl">Um lugar para começar sua pesquisa.</h3><p className="mt-3 text-sm text-muted">Crie seu primeiro projeto. Depois você poderá adicionar um ou mais repositórios públicos do GitHub.</p></div>}
      {!!state.data?.length && <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{state.data.map(p=><li key={p.id}><Link href={projectHref(p.id)} className="block h-full rounded-md border-[1.5px] border-ink bg-surface p-6 shadow-solid-sm hover:bg-surface-muted"><span className="eyebrow">Projeto acadêmico</span><h3 className="mt-3 break-words font-hand text-3xl">{p.name}</h3><p className="mt-3 whitespace-pre-wrap break-words text-sm text-muted">{p.description || 'Sem descrição.'}</p><div className="mt-6 flex items-center justify-between text-xs"><span>{p.source_count} {p.source_count===1?'fonte':'fontes'}</span><span>Abrir projeto <ArrowRight size={14} className="ml-1 inline" aria-hidden="true"/></span></div></Link></li>)}</ul>}
    </section>
    <ProjectActivity />
    <form id="new-project" className="rounded-md border-[1.5px] border-ink bg-surface p-6 shadow-solid-md" aria-labelledby="new-project-title" onSubmit={async event=>{
      event.preventDefault();if(mutation.current)return;
      if(!name.trim()){setError('Informe um nome para o projeto.');return;}
      const controller=new AbortController();mutation.current=controller;setCreating(true);setError(null);
      try{const p=await projectsApi.create(name.trim(),description.trim() || null,controller.signal);if(!controller.signal.aborted)router.push(projectHref(p.id));}
      catch(cause){if(!controller.signal.aborted)setError(projectMessage(cause));}
      finally{if(mutation.current===controller)mutation.current=undefined;if(!controller.signal.aborted)setCreating(false);}
    }}><h2 id="new-project-title" className="font-hand text-3xl">Novo projeto</h2><div className="mt-5 grid gap-4"><label className="text-sm font-medium" htmlFor="project-name">Nome do projeto<input id="project-name" required maxLength={160} value={name} disabled={creating} onChange={e=>setName(e.target.value)} className="mt-2 block h-11 w-full rounded-md border border-border bg-bg px-3" autoComplete="off"/></label><label className="text-sm font-medium" htmlFor="project-description">Descrição <span className="font-normal text-muted">(opcional)</span><textarea id="project-description" maxLength={4000} rows={3} value={description} disabled={creating} onChange={e=>setDescription(e.target.value)} className="mt-2 block w-full rounded-md border border-border bg-bg p-3"/></label></div>{error && <p role="alert" className="mt-3 text-sm">{error}</p>}<Button className="mt-5" disabled={creating} type="submit">{creating?'Criando…':'Criar projeto'}</Button></form>
  </div>;
}
