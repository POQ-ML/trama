import type { ISODateTime, RunRead, UUID } from './discovery';

/** Academic container; distinct from discovery.ProjectRead, the repo entity. */
export interface AcademicProjectCreate {
  name: string;
  description?: string | null;
}
export interface AcademicProjectRead {
  id: UUID;
  name: string;
  description: string | null;
  source_count: number;
  created_at: ISODateTime;
}
export interface AcademicProjectDetail extends AcademicProjectRead {
  sources: ProjectSourceRead[];
}
export interface ProjectSourceCreate {
  source_type: 'github';
  repo_url: string;
}
export interface ProjectSourceRead {
  id: UUID;
  project_id: UUID;
  source_type: 'github';
  label: string;
  repo_url: string;
  latest_run: RunRead | null;
  created_at: ISODateTime;
}
export interface ProjectActivityRead {
  id: UUID;
  project_id: UUID;
  project_name: string;
  source_id: UUID;
  source_label: string;
  observed_at: ISODateTime;
  read_at: ISODateTime | null;
  kind: 'source_changed';
}
