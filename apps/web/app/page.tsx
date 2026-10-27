import Navbar from "../components/Navbar";
import DiscoveryWorkspace from "../components/DiscoveryWorkspace";

export default function Home(): JSX.Element {
  return <>
    <a href="#main-content" className="skip-link">Ir para o conteúdo</a>
    <Navbar />
    <main id="main-content" className="mx-auto max-w-[1440px] px-5 py-8 sm:px-9 sm:py-12">
      <DiscoveryWorkspace />
    </main>
    <footer className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-3 border-t border-border px-5 py-6 text-xs text-muted sm:px-9">
      <span>TRAMA · Contexto que conecta.</span><span>GitHub + OpenAlex · evidências rastreáveis, decisões suas.</span>
    </footer>
  </>;
}
