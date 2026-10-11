import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

interface MapNode {
  id: string;
  label: string;
  sub: string;
  x: number;
  y: number;
  center?: boolean;
}

const nodes: MapNode[] = [
  { id: "voce",     label: "Você",     sub: "hub central",    x: 400, y: 210, center: true },
  { id: "moodle",   label: "Moodle",   sub: "Cálculo II",     x: 150, y: 110 },
  { id: "github",   label: "GitHub",   sub: "projeto-final",  x: 630, y: 100 },
  { id: "ufc",      label: "UFC",      sub: "SIGAA",          x: 200, y: 330 },
  { id: "openalex", label: "OpenAlex", sub: "grafos · 3 arts", x: 590, y: 320 },
];

const links: Array<{ from: string; to: string }> = [
  { from: "voce", to: "moodle"   },
  { from: "voce", to: "github"   },
  { from: "voce", to: "ufc"      },
  { from: "voce", to: "openalex" },
  { from: "moodle", to: "ufc"   },
];

function findNode(id: string): MapNode {
  const found = nodes.find((n) => n.id === id);
  if (found === undefined) throw new Error(`nó desconhecido: ${id}`);
  return found;
}

export default function ContextMap(): JSX.Element {
  return (
    <section
      aria-label="Context Map — placeholder visual"
      className="flex flex-col overflow-hidden rounded-md bg-surface shadow-solid-lg"
      style={{ border: "1.5px solid #0a0a0a" }}
    >
      {/* ─── Cabeçalho ───────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="font-hand text-[22px] leading-none text-ink">
            Context map — placeholder visual
          </h2>
          <p className="mt-1 text-[13px] text-muted">
            Mapa interativo chega no próximo marco · nós fictícios
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm">+ Zoom</Button>
          <Button variant="outline" size="sm">- Zoom</Button>
          <Button variant="outline" size="sm">↺ Reset</Button>
          <Button variant="default" size="sm">◈ Filtros</Button>
        </div>
      </div>

      {/* ─── Área do mapa com grade ───────────────────────────────────────── */}
      <div className="map-grid relative min-h-[380px] flex-1">
        <svg
          viewBox="0 0 800 440"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Grafo fictício com 5 nós"
        >
          {/* Arestas tracejadas em ink */}
          {links.map((l) => {
            const a = findNode(l.from);
            const b = findNode(l.to);
            return (
              <line
                key={`${l.from}-${l.to}`}
                x1={a.x} y1={a.y}
                x2={b.x} y2={b.y}
                stroke="#0a0a0a"
                strokeOpacity={0.7}
                strokeWidth={1.5}
                strokeDasharray="6 5"
              />
            );
          })}

          {/* Nós */}
          {nodes.map((n) => (
            <g key={n.id}>
              {n.center === true ? (
                <>
                  {/* Anel externo tracejado do hub */}
                  <circle
                    cx={n.x} cy={n.y} r={46}
                    fill="none"
                    stroke="#0a0a0a"
                    strokeOpacity={0.25}
                    strokeWidth={1}
                    strokeDasharray="2 4"
                  />
                  {/* Hub preenchido em ink */}
                  <circle
                    cx={n.x} cy={n.y} r={33}
                    fill="#0a0a0a"
                    stroke="#0a0a0a"
                    strokeWidth={2}
                  />
                  <text
                    x={n.x} y={n.y - 3}
                    textAnchor="middle"
                    fill="#ffffff"
                    fontSize={14}
                    fontFamily="'Patrick Hand', cursive"
                    fontWeight={400}
                  >
                    {n.label}
                  </text>
                  <text
                    x={n.x} y={n.y + 13}
                    textAnchor="middle"
                    fill="rgba(255,255,255,0.6)"
                    fontSize={9}
                    fontFamily="monospace"
                  >
                    {n.sub}
                  </text>
                </>
              ) : (
                <>
                  {/* Nó de fonte — fundo branco, borda ink */}
                  <circle
                    cx={n.x} cy={n.y} r={22}
                    fill="#ffffff"
                    stroke="#0a0a0a"
                    strokeWidth={1.5}
                  />
                  <text
                    x={n.x} y={n.y - 2}
                    textAnchor="middle"
                    fill="#0a0a0a"
                    fontSize={12}
                    fontFamily="'Geist', sans-serif"
                    fontWeight={500}
                  >
                    {n.label}
                  </text>
                  <text
                    x={n.x} y={n.y + 13}
                    textAnchor="middle"
                    fill="#737373"
                    fontSize={9}
                    fontFamily="monospace"
                  >
                    {n.sub}
                  </text>
                </>
              )}
            </g>
          ))}
        </svg>

        {/* Legenda */}
        <div className="absolute bottom-4 left-4 flex gap-4 rounded-[6px] border border-border bg-surface px-3 py-2 font-mono text-[10px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-ink" /> HUB
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full border border-ink bg-surface" /> FONTE
          </span>
          <span className="hidden sm:inline">5 NÓS · 5 LINKS</span>
        </div>

        {/* Badge placeholder */}
        <div className="absolute bottom-4 right-4">
          <Badge variant="dashed">SEM LÓGICA REAL</Badge>
        </div>
      </div>
    </section>
  );
}
