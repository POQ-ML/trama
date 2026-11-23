import type { AcademicProjectRead, AcademicProjectDetail, ProjectSourceRead, ProjectActivityRead } from '../../../packages/shared/src';
export type { AcademicProjectRead, AcademicProjectDetail, ProjectSourceRead, ProjectActivityRead } from '../../../packages/shared/src';
import { ApiError, messageOf, request } from './discovery';
import { projectHref, sourceHref, type SourceScope } from './projectRoutes';

export const projectsApi = {
  list: (signal: AbortSignal): Promise<AcademicProjectRead[]> => request('/projects', signal),
  activity: (signal: AbortSignal): Promise<ProjectActivityRead[]> => request('/projects/activity', signal),
  create: (name: string, description: string | null, signal: AbortSignal): Promise<AcademicProjectRead> => request('/projects', signal, { method:'POST', body:JSON.stringify({name,description}) }),
  read: (id: string, signal: AbortSignal): Promise<AcademicProjectDetail> => request(projectHref(id), signal),
  addSource: (projectId: string, repo_url: string, signal: AbortSignal): Promise<ProjectSourceRead> => request(`${projectHref(projectId)}/sources`, signal, { method:'POST', body:JSON.stringify({source_type:'github',repo_url}) }),
  source: (scope: SourceScope, signal: AbortSignal): Promise<ProjectSourceRead> => request(sourceHref(scope), signal),
};
export function projectMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return 'Projeto ou fonte não encontrado neste espaço. Confira o endereço ou volte aos projetos.';
  if (error instanceof ApiError && error.status === 422) return 'Confira os campos: nome do projeto e URL pública do GitHub, conforme o formulário.';
  return messageOf(error);
}
export function githubRepoUrl(value: string): string {
  const url = new URL(value.trim());
  if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.port || url.username || url.password || url.search || url.hash || !/^\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(url.pathname) || url.pathname.split('/').some(p => p === '.' || p === '..')) throw new Error('invalid_repo');
  return url.href.replace(/\/$/, '');
}
