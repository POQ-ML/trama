import HealthBadge from "./HealthBadge";

export default function Navbar(): JSX.Element {
  return <header className="border-b border-border bg-surface">
    <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-9">
      <a href="/" aria-label="TRAMA, início" className="flex items-center gap-3 no-underline">
        <span aria-hidden="true" className="flex h-11 w-11 items-center justify-center rounded-md bg-ink font-hand text-2xl text-white shadow-solid-logo">T</span>
        <span><span className="block font-hand text-2xl tracking-[.25em]">TRAMA</span><span className="block text-xs text-muted">Agente de Contexto Acadêmico</span></span>
      </a>
      <div className="flex items-center gap-4"><nav aria-label="Navegação principal" className="flex flex-wrap gap-4 text-sm"><a href="/" className="underline-offset-4 hover:underline">Projetos</a><a href="/discoveries" className="underline-offset-4 hover:underline">Diagnóstico avulso</a></nav><HealthBadge /></div>
    </div>
  </header>;
}
