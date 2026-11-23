export type SourceScope = { projectId: string; sourceId: string };
export const projectHref = (id: string): string => `/projects/${encodeURIComponent(id)}`;
export const sourceHref = (scope: SourceScope): string => `${projectHref(scope.projectId)}/sources/${encodeURIComponent(scope.sourceId)}`;
export const runHref = (scope: SourceScope | undefined, id: string): string => `${scope ? sourceHref(scope) : '/discoveries'}?run=${encodeURIComponent(id)}`;
export const scopeIdentity = (scope?: SourceScope): string => scope ? JSON.stringify([scope.projectId, scope.sourceId]) : 'legacy';
