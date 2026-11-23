"use client";
import { useSearchParams } from 'next/navigation';
import DiscoveryWorkspace from './DiscoveryWorkspace';
import ProjectDashboard from './ProjectDashboard';
export default function RootWorkspace(): JSX.Element {
  const query = useSearchParams();
  return query.has('run') ? <DiscoveryWorkspace /> : <ProjectDashboard />;
}
