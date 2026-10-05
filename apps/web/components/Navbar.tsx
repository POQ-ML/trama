"use client";

import HealthBadge from "./HealthBadge";

const links: Array<{ label: string; active?: boolean }> = [
  { label: "Mapa", active: true },
  { label: "Fontes" },
  { label: "Timeline" },
  { label: "Docs" }
];

export default function Navbar(): JSX.Element {
  return (
    <header className="relative z-20 flex items-center justify-between gap-4 border-b border-teal-300/10 bg-abyss/80 px-4 py-3 backdrop-blur-md sm:px-6">
      <div className="flex items-center gap-3">
        <div
          aria-hidden="true"
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-teal-300/40 bg-gradient-to-br from-teal-300/20 via-panel to-violet-500/20 font-mono text-lg font-bold text-neon shadow-glow"
        >
          T
        </div>
        <div className="leading-tight">
          <p className="font-mono text-sm font-bold tracking-[0.35em] text-neon">
            TRAMA
          </p>
          <p className="text-xs text-slate-400">
            Agente de Contexto Acadêmico
          </p>
        </div>
        <span className="ml-2 hidden rounded-full border border-violet-400/30 bg-violet-500/10 px-2.5 py-0.5 font-mono text-[10px] tracking-widest text-violet-200 lg:inline-block">
          MVP · MOCK
        </span>
      </div>

      <nav aria-label="Navegação principal" className="hidden items-center gap-6 text-sm md:flex">
        {links.map((link) => (
          <a
            key={link.label}
            href="#"
            onClick={(e): void => e.preventDefault()}
            className={
              link.active
                ? "font-medium text-neon"
                : "text-slate-400 transition-colors hover:text-slate-200"
            }
          >
            {link.label}
          </a>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <HealthBadge />
      </div>
    </header>
  );
}
