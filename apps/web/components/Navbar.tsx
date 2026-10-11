"use client";

import HealthBadge from "./HealthBadge";
import { Badge } from "./ui/badge";

const links: Array<{ label: string; active?: boolean }> = [
  { label: "Mapa", active: true },
  { label: "Fontes" },
  { label: "Timeline" },
  { label: "Docs" }
];

export default function Navbar(): JSX.Element {
  return (
    <header className="relative z-20 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface px-6 py-3">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div
          aria-hidden="true"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border-strong border-ink bg-ink shadow-solid-logo font-hand text-lg font-bold text-white"
          style={{ borderWidth: "1.5px" }}
        >
          T
        </div>
        <div className="leading-tight">
          <p className="font-hand text-xl tracking-[0.3em] text-ink">
            TRAMA
          </p>
          <p className="text-xs text-muted">
            Agente de Contexto Acadêmico
          </p>
        </div>
        <Badge variant="outline" className="hidden lg:inline-flex">
          MVP · MOCK
        </Badge>
      </div>

      {/* Tabs de navegação */}
      <nav
        aria-label="Navegação principal"
        className="hidden items-center md:flex"
      >
        {/* Lista de tabs — fundo #f0f0f0, aba ativa branca */}
        <div
          role="tablist"
          className="inline-flex gap-0.5 rounded-md border border-border bg-surface-tabs p-[3px]"
        >
          {links.map((link) => (
            <a
              key={link.label}
              href="#"
              role="tab"
              aria-selected={link.active === true}
              onClick={(e): void => e.preventDefault()}
              className={[
                "min-h-8 rounded-[6px] px-4 py-1.5 text-sm font-medium transition-colors",
                link.active === true
                  ? "bg-surface text-ink shadow-solid-tab"
                  : "text-muted hover:text-ink"
              ].join(" ")}
            >
              {link.label}
            </a>
          ))}
        </div>
      </nav>

      {/* Health badge */}
      <div className="flex items-center gap-3">
        <HealthBadge />
      </div>
    </header>
  );
}
