interface MapNode {
  id: string;
  label: string;
  sub: string;
  x: number;
  y: number;
  center?: boolean;
}

const nodes: MapNode[] = [
  { id: "voce", label: "Você", sub: "hub central", x: 400, y: 210, center: true },
  { id: "moodle", label: "Moodle", sub: "Cálculo II", x: 150, y: 110 },
  { id: "github", label: "GitHub", sub: "projeto-final", x: 630, y: 100 },
  { id: "ufc", label: "UFC", sub: "SIGAA", x: 200, y: 330 },
  { id: "openalex", label: "OpenAlex", sub: "grafos · 3 arts", x: 590, y: 320 }
];

const links: Array<{ from: string; to: string }> = [
  { from: "voce", to: "moodle" },
  { from: "voce", to: "github" },
  { from: "voce", to: "ufc" },
  { from: "voce", to: "openalex" },
  { from: "moodle", to: "ufc" }
];

function findNode(id: string): MapNode {
  const found = nodes.find((n) => n.id === id);
  if (found === undefined) throw new Error(`nó desconhecido: ${id}`);
  return found;
}

const toolbar: string[] = ["＋ Zoom", "－ Zoom", "⟲ Reset", "◈ Filtros"];

export default function ContextMap(): JSX.Element {
  return (
    <section
      aria-label="Context Map — placeholder visual"
      className="hud-corner relative flex min-h-[520px] flex-col overflow-hidden rounded-2xl border border-teal-300/15 bg-panel/70"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 px-5 py-4">
        <div>
          <p className="font-mono text-[11px] tracking-[0.3em] text-slate-400">
            CONTEXT MAP — PLACEHOLDER VISUAL
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Mapa interativo chega no próximo marco · nós fictícios
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {toolbar.map((t) => (
            <button
              key={t}
              type="button"
              className="rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-xs text-slate-300 transition-colors hover:border-teal-300/40 hover:text-neon"
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="hud-grid relative flex-1">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-teal-400/10 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-10 top-10 h-40 w-40 rounded-full bg-violet-500/10 blur-3xl"
        />

        <svg
          viewBox="0 0 800 440"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Grafo fictício com 5 nós"
        >
          {links.map((l) => {
            const a = findNode(l.from);
            const b = findNode(l.to);
            return (
              <line
                key={`${l.from}-${l.to}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#5eead4"
                strokeOpacity={0.45}
                strokeWidth={1.5}
                strokeDasharray="5 7"
              />
            );
          })}

          {nodes.map((n) => (
            <g key={n.id}>
              <circle
                cx={n.x}
                cy={n.y}
                r={n.center === true ? 34 : 24}
                fill={n.center === true ? "rgba(94,234,212,0.15)" : "rgba(11,17,30,0.95)"}
                stroke={n.center === true ? "#5eead4" : "rgba(255,255,255,0.2)"}
                strokeWidth={n.center === true ? 2 : 1.2}
              />
              {n.center === true && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={46}
                  fill="none"
                  stroke="#5eead4"
                  strokeOpacity={0.25}
                  strokeDasharray="3 6"
                />
              )}
              <text
                x={n.x}
                y={n.y - 2}
                textAnchor="middle"
                fill="#e2e8f0"
                fontSize={n.center === true ? 14 : 12}
                fontWeight={700}
              >
                {n.label}
              </text>
              <text
                x={n.x}
                y={n.y + 14}
                textAnchor="middle"
                fill="#64748b"
                fontSize={9}
                fontFamily="monospace"
              >
                {n.sub}
              </text>
            </g>
          ))}
        </svg>

        <div className="absolute bottom-4 left-4 flex gap-4 rounded-lg border border-white/5 bg-black/50 px-3 py-2 font-mono text-[10px] tracking-widest text-slate-400 backdrop-blur">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-teal-300" /> HUB
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full border border-white/40" /> FONTE
          </span>
          <span className="hidden sm:inline">5 NÓS · 5 LINKS</span>
        </div>

        <div className="absolute bottom-4 right-4 rounded-lg border border-amber-300/20 bg-amber-400/10 px-3 py-1.5 font-mono text-[10px] tracking-widest text-amber-200">
          SEM LÓGICA REAL
        </div>
      </div>
    </section>
  );
}
