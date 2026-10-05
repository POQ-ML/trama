interface NodeCardProps {
  title: string;
  subtitle?: string;
  kind?: "center" | "source" | "event";
  active?: boolean;
}

const kindAccent: Record<NonNullable<NodeCardProps["kind"]>, string> = {
  center: "border-teal-300/60 bg-teal-300/10 text-teal-100 shadow-glow",
  source: "border-white/10 bg-panel/90 text-slate-200",
  event: "border-violet-400/30 bg-violet-500/10 text-violet-100"
};

export default function NodeCard({
  title,
  subtitle = "nó fictício",
  kind = "source",
  active = false
}: NodeCardProps): JSX.Element {
  return (
    <div
      className={`rounded-xl border px-3 py-2 text-sm backdrop-blur-md transition-colors ${kindAccent[kind]} ${
        active ? "ring-1 ring-teal-300/60" : ""
      }`}
    >
      <p className="font-medium leading-tight">{title}</p>
      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-widest opacity-50">
        {subtitle}
      </p>
    </div>
  );
}
