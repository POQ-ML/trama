import type { DiscoveryPage, RunRead } from '../../../packages/shared/src';
import { discoveryApi, request } from './discovery';
import { sourceHref, type SourceScope } from './projectRoutes';

/** The server validates all queried run IDs against the source; never fall back to a global read. */
export function diagnosisApi(scope?: SourceScope) {
  return {
    read: (id: string, signal: AbortSignal, cursor?: string): Promise<DiscoveryPage> => scope
      ? request(`${sourceHref(scope)}/discoveries/${encodeURIComponent(id)}?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, signal)
      : discoveryApi.read(id, signal, cursor),
    start: (repoUrl: string, key: string, signal: AbortSignal, reanalyzeId?: string): Promise<RunRead> => scope
      ? request(`${sourceHref(scope)}/discoveries`, signal, { method: 'POST', headers: { 'Idempotency-Key': key } })
      : reanalyzeId ? discoveryApi.reanalyze(reanalyzeId, signal) : discoveryApi.create(repoUrl, key, signal),
  };
}
