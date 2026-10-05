"use client";

import { useEffect, useState } from "react";
import { getApiHealth } from "../lib/api";

type BadgeState = "checking" | "healthy" | "degraded" | "unreachable";

function resolveState(status: string): BadgeState {
  const s = status.toLowerCase();
  if (s === "ok" || s === "healthy" || s === "up") return "healthy";
  if (s === "unreachable" || s === "down" || s === "offline") return "unreachable";
  if (s === "checking") return "checking";
  return "degraded";
}

const styles: Record<BadgeState, { dot: string; text: string; ring: string; label: string }> = {
  checking: {
    dot: "bg-slate-400 animate-pulse",
    text: "text-slate-300",
    ring: "border-white/10",
    label: "checando…"
  },
  healthy: {
    dot: "bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]",
    text: "text-emerald-200",
    ring: "border-emerald-300/30",
    label: "online"
  },
  degraded: {
    dot: "bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.9)]",
    text: "text-amber-200",
    ring: "border-amber-300/30",
    label: "degradado"
  },
  unreachable: {
    dot: "bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.9)]",
    text: "text-rose-200",
    ring: "border-rose-400/30",
    label: "offline"
  }
};

export default function HealthBadge(): JSX.Element {
  const [state, setState] = useState<BadgeState>("checking");
  const [detail, setDetail] = useState<string>("API: checando…");

  useEffect(() => {
    let alive = true;

    getApiHealth()
      .then((h) => {
        if (!alive) return;
        const next = resolveState(h.status);
        setState(next);
        const db = h.database !== undefined && h.database !== "" ? ` · db ${h.database}` : "";
        setDetail(`API: ${h.status}${db}`);
      })
      .catch(() => {
        if (!alive) return;
        setState("unreachable");
        setDetail("API: unreachable");
      });

    return (): void => {
      alive = false;
    };
  }, []);

  const s = styles[state];

  return (
    <div
      role="status"
      title={detail}
      className={`flex items-center gap-2 rounded-full border ${s.ring} bg-black/40 px-3 py-1.5 font-mono text-xs ${s.text}`}
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${s.dot}`} />
      <span className="hidden sm:inline">{detail}</span>
      <span className="sm:hidden">{s.label}</span>
    </div>
  );
}
