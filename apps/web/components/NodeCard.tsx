import { cn } from "@/lib/utils";

interface NodeCardProps {
  title: string;
  subtitle?: string;
  kind?: "center" | "source" | "event";
  active?: boolean;
}

/*
 * center  = hub ativo → fundo branco + shadow-solid-md
 * source  = fonte     → fundo branco simples
 * event   = evento    → fundo surface-muted
 */
const kindStyles: Record<NonNullable<NodeCardProps["kind"]>, string> = {
  center: "bg-surface shadow-solid-md",
  source: "bg-surface",
  event:  "bg-surface-muted",
};

export default function NodeCard({
  title,
  subtitle = "nó fictício",
  kind = "source",
  active = false,
}: NodeCardProps): JSX.Element {
  return (
    <div
      className={cn(
        "rounded-md px-4 py-3 transition-colors",
        "border-strong border-ink",
        kindStyles[kind],
        active && "ring-2 ring-ink ring-offset-1"
      )}
      style={{ borderWidth: "1.5px" }}
    >
      <p className="font-hand text-xl leading-tight text-ink">{title}</p>
      <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-muted">
        {subtitle}
      </p>
    </div>
  );
}
