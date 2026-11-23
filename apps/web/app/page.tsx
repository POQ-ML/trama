import { Suspense } from 'react';
import AppFrame from '../components/AppFrame';
import RootWorkspace from '../components/RootWorkspace';
export default function Home(): JSX.Element {
  return <AppFrame><Suspense fallback={<p role="status">Carregando espaço de projetos…</p>}><RootWorkspace /></Suspense></AppFrame>;
}
