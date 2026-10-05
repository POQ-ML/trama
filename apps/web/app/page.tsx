import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import ContextMap from "../components/ContextMap";
import NodeCard from "../components/NodeCard";

const highlights: Array<{ title: string; subtitle: string; kind: "center" | "source" | "event" }> = [
  { title: "Cálculo II · P1", subtitle: "12 OUT · evento", kind: "event" },
  { title: "projeto-final", subtitle: "3 commits hoje · source", kind: "source" },
  { title: "Trilha de Grafos", subtitle: "hub ativo · center", kind: "center" }
];

export default function Home(): JSX.Element {
  return (
    <main className="hud-grid min-h-screen bg-void">
      <Navbar />

      <div className="mx-auto grid max-w-[1440px] gap-4 px-4 py-6 sm:px-6 lg:grid-cols-[300px_minmax(0,1fr)_300px]">
        <Sidebar side="left" />

        <div className="space-y-4">
          <ContextMap />

          <div className="grid gap-3 sm:grid-cols-3">
            {highlights.map((h) => (
              <NodeCard
                key={h.title}
                title={h.title}
                subtitle={h.subtitle}
                kind={h.kind}
              />
            ))}
          </div>

          <p className="rounded-xl border border-white/5 bg-black/30 px-4 py-3 text-xs leading-relaxed text-slate-500">
            TRAMA · Initial Build — interface mockada com dados locais. O mapa,
            os botões e os cards acima são placeholders visuais: nenhuma ação
            executa lógica real ainda. A saúde do backend é consultada em{" "}
            <span className="font-mono text-slate-400">/api/v1/health</span>.
          </p>
        </div>

        <Sidebar side="right" />
      </div>

      <footer className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2 px-6 pb-6 font-mono text-[11px] tracking-widest text-slate-600">
        <span>TRAMA · HUD SCI-FI MINIMALISTA</span>
        <span>FRONT MOCK · SEM LÓGICA REAL</span>
      </footer>
    </main>
  );
}
