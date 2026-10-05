import type { ReactNode } from "react";

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
  date: string;
}

const changes: ChangeItem[] = [
  { id: 1, text: "Nota de Cálculo II atualizada", time: "2h", tag: "Moodle" },
  { id: 2, text: "Novo commit em projeto-final", time: "5h", tag: "GitHub" },
  { id: 3, text: "Artigo salvo sobre grafos", time: "1d", tag: "OpenAlex" }
];

const connections: ConnectionItem[] = [
  { id: 1, text: "Moodle ⇄ GitHub", strength: 82 },
  { id: 2, text: "UFC ⇄ OpenAlex", strength: 64 },
  { id: 3, text: "Você ⇄ Cálculo II", strength: 91 }
];

const events: EventItem[] = [
  { id: 1, text: "P1 — Cálculo II", date: "12 OUT" },
  { id: 2, text: "Entrega parcial — Projeto", date: "20 OUT" },
  { id: 3, text: "Seminário de Redes", date: "28 OUT" }
];

const sources: string[] = ["Moodle", "GitHub", "UFC", "OpenAlex"];

interface SidebarProps {
  side: "left" | "right";
}

function Panel({
  title,
  children
}: {
  title: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className="hud-corner relative rounded-2xl border border-white/5 bg-panel/70 p-4 backdrop-blur-md">
      <h2 className="mb-3 font-mono text-[11px] tracking-[0.25em] text-teal-200/80">
        {title.toUpperCase()}
      </h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

export default function Sidebar({ side }: SidebarProps): JSX.Element {
  if (side === "left") {
    return (
      <aside className="space-y-4" aria-label="Mudanças e conexões">
        <Panel title="Mudanças">
          {changes.map((c) => (
            <div
              key={c.id}
              className="rounded-lg border border-white/5 bg-black/30 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="rounded border border-teal-300/20 bg-teal-300/10 px-1.5 py-0.5 font-mono text-[10px] text-teal-200">
                  {c.tag}
                </span>
                <span className="font-mono text-[11px] text-slate-500">{c.time}</span>
              </div>
              <p className="mt-1.5 text-sm text-slate-300">{c.text}</p>
            </div>
          ))}
        </Panel>

        <Panel title="Conexões">
          {connections.map((c) => (
            <div
              key={c.id}
              className="rounded-lg border border-white/5 bg-black/30 px-3 py-2"
            >
              <p className="text-sm text-slate-300">{c.text}</p>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-teal-300 to-violet-400"
                  style={{ width: `${c.strength}%` }}
                />
              </div>
              <p className="mt-1 font-mono text-[10px] text-slate-500">
                força {c.strength}% · mock
              </p>
            </div>
          ))}
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="space-y-4" aria-label="Eventos e fontes">
      <Panel title="Eventos">
        {events.map((e) => (
          <div
            key={e.id}
            className="flex items-center gap-3 rounded-lg border border-white/5 bg-black/30 px-3 py-2"
          >
            <div className="flex h-10 w-12 shrink-0 flex-col items-center justify-center rounded-md border border-violet-400/20 bg-violet-500/10 font-mono text-[10px] font-bold text-violet-200">
              {e.date}
            </div>
            <p className="text-sm text-slate-300">{e.text}</p>
          </div>
        ))}
      </Panel>

      <Panel title="Fontes">
        <div className="grid grid-cols-2 gap-2">
          {sources.map((s) => (
            <div
              key={s}
              className="flex items-center gap-2 rounded-lg border border-white/5 bg-black/30 px-3 py-2 text-sm text-slate-300"
            >
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full bg-teal-300 shadow-[0_0_8px_rgba(94,234,212,0.8)]"
              />
              {s}
            </div>
          ))}
        </div>
        <p className="mt-2 font-mono text-[10px] tracking-widest text-slate-500">
          4 FONTES · PLACEHOLDER
        </p>
      </Panel>
    </aside>
  );
}
