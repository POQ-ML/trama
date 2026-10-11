import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import ContextMap from "../components/ContextMap";
import NodeCard from "../components/NodeCard";

const highlights: Array<{
  title: string;
  subtitle: string;
  kind: "center" | "source" | "event";
}> = [
  { title: "Cálculo II · P1",  subtitle: "12 OUT · EVENTO",        kind: "event"  },
  { title: "projeto-final",    subtitle: "3 COMMITS HOJE · SOURCE", kind: "source" },
  { title: "Trilha de Grafos", subtitle: "HUB ATIVO · CENTER",      kind: "center" },
];

export default function Home(): JSX.Element {
  return (
    <main className="min-h-screen bg-bg">
      <Navbar />

      {/* ─── Grade de 3 colunas ─────────────────────────────────────────── */}
      <div className="mx-auto grid max-w-[1200px] gap-5 px-7 py-5
                      lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)_minmax(0,300px)]">

        {/* Coluna esquerda */}
        <Sidebar side="left" />

        {/* Coluna central */}
        <div className="min-w-0 space-y-4">
          <ContextMap />

          {/* Cards inferiores */}
          <div className="grid gap-4 sm:grid-cols-3">
            {highlights.map((h) => (
              <NodeCard
                key={h.title}
                title={h.title}
                subtitle={h.subtitle}
                kind={h.kind}
              />
            ))}
          </div>

          {/* Nota informativa — borda tracejada, fundo branco */}
          <div
            className="flex gap-3 rounded-md bg-surface px-4 py-3.5 text-[13px] leading-relaxed text-muted"
            style={{ border: "1px dashed #a3a3a3" }}
          >
            {/* Ícone "i" desenhado */}
            <span
              aria-hidden="true"
              className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-semibold text-ink"
              style={{ border: "1.5px solid #0a0a0a" }}
            >
              i
            </span>
            <p>
              TRAMA · Initial Build — interface mockada com dados locais. O mapa,
              os botões e os cards acima são placeholders visuais: nenhuma ação
              executa lógica real ainda. A saúde do backend é consultada em{" "}
              <span className="font-mono font-medium text-ink">/api/v1/health</span>.
            </p>
          </div>
        </div>

        {/* Coluna direita */}
        <Sidebar side="right" />
      </div>
    </main>
  );
}
