import type { ReactNode } from "react";
import { Progress } from "./ui/progress";

interface ChangeItem {
  id: number;
  text: string;
  time: string;
  tag: string;
}

interface ConnectionItem {
  id: number;
  text: string;
  strength: number;
}

interface EventItem {
  id: number;
  text: string;
  day: string;
  month: string;
}

const changes: ChangeItem[] = [
  { id: 1, text: "Nota de Cálculo II atualizada",   time: "2h", tag: "Moodle"   },
  { id: 2, text: "Novo commit em projeto-final",     time: "5h", tag: "GitHub"   },
  { id: 3, text: "Artigo salvo sobre grafos",        time: "1d", tag: "OpenAlex" },
];

const connections: ConnectionItem[] = [
  { id: 1, text: "Moodle ⇄ GitHub",    strength: 82 },
  { id: 2, text: "UFC ⇄ OpenAlex",     strength: 64 },
  { id: 3, text: "Você ⇄ Cálculo II",  strength: 91 },
];

const events: EventItem[] = [
  { id: 1, text: "P1 — Cálculo II",          day: "12", month: "OUT" },
  { id: 2, text: "Entrega parcial — Projeto", day: "20", month: "OUT" },
  { id: 3, text: "Seminário de Redes",        day: "28", month: "OUT" },
];

const sources: string[] = ["Moodle", "GitHub", "UFC", "OpenAlex"];

interface SidebarProps {
  side: "left" | "right";
}

/* ─── Card (seção lateral) ─────────────────────────────────────────────────── */
function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className="rounded-md border-strong border-ink bg-surface p-4" style={{ borderWidth: "1.5px" }}>
      <h2 className="font-hand text-[22px] leading-none text-ink">{title}</h2>
      {subtitle !== undefined && (
        <p className="mt-1 text-[13px] text-muted">{subtitle}</p>
      )}
      <div className="mt-3 space-y-2">{children}</div>
    </section>
  );
}

/* ─── Sidebar esquerda ─────────────────────────────────────────────────────── */
function LeftSidebar(): JSX.Element {
  return (
    <aside className="space-y-4" aria-label="Mudanças e conexões">
      <Panel title="Mudanças" subtitle="Últimas atualizações das fontes">
        {changes.map((c) => (
          <div
            key={c.id}
            className="rounded-[6px] border border-border bg-surface px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="rounded-[6px] border border-border bg-surface-muted px-2 py-0.5 font-mono text-[11px] text-ink">
                {c.tag}
              </span>
              <span className="font-mono text-[11px] text-muted">{c.time}</span>
            </div>
            <p className="mt-1.5 text-sm text-ink">{c.text}</p>
          </div>
        ))}
      </Panel>

      <Panel title="Conexões" subtitle="Relações entre contextos">
        {connections.map((c) => (
          <div
            key={c.id}
            className="rounded-[6px] border border-border bg-surface px-3 py-2.5"
          >
            <p className="text-sm text-ink">{c.text}</p>
            <Progress value={c.strength} className="mt-2" />
            <p className="mt-1 font-mono text-[11px] text-muted">
              força {c.strength}% · mock
            </p>
          </div>
        ))}
      </Panel>
    </aside>
  );
}

/* ─── Sidebar direita ──────────────────────────────────────────────────────── */
function RightSidebar(): JSX.Element {
  return (
    <aside className="space-y-4" aria-label="Eventos e fontes">
      <Panel title="Eventos" subtitle="Próximos prazos">
        {events.map((e) => (
          <div
            key={e.id}
            className="flex items-center gap-3 rounded-[6px] border border-border bg-surface px-3 py-2"
          >
            {/* Chip de data */}
            <div
              className="flex w-12 shrink-0 flex-col items-center justify-center rounded-[6px] bg-surface-muted py-1 text-center"
              style={{ border: "1.5px solid #0a0a0a" }}
            >
              <span className="font-mono text-sm font-semibold leading-none text-ink">
                {e.day}
              </span>
              <span className="font-mono text-[10px] font-semibold uppercase leading-none text-muted">
                {e.month}
              </span>
            </div>
            <p className="text-sm text-ink">{e.text}</p>
          </div>
        ))}
      </Panel>

      <Panel title="Fontes" subtitle={`${sources.length} fontes · placeholder`}>
        <div className="grid grid-cols-2 gap-2">
          {sources.map((s) => (
            <div
              key={s}
              className="flex items-center gap-2 rounded-[6px] border border-border bg-surface px-3 py-2 text-sm text-ink"
            >
              {/* Dot indicador de fonte */}
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-full bg-ink"
              />
              {s}
            </div>
          ))}
        </div>
        <button
          type="button"
          className="mt-2 w-full rounded-[6px] border border-border bg-surface-muted py-2 text-sm font-medium text-ink transition-colors hover:bg-border-soft"
        >
          Gerenciar fontes
        </button>
      </Panel>
    </aside>
  );
}

export default function Sidebar({ side }: SidebarProps): JSX.Element {
  return side === "left" ? <LeftSidebar /> : <RightSidebar />;
}
