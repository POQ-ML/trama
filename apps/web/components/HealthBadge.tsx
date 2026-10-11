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

/* dot monocromático: preenchido = ok, vazio = offline, pulsando = checando */
const dotStyles: Record<BadgeState, string> = {
  checking: "bg-muted animate-pulse",
  healthy:  "bg-ink",
  degraded: "border border-ink bg-surface-muted",
  unreachable: "border border-ink bg-surface",
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

    return (): void => { alive = false; };
  }, []);

  return (
    <div
      role="status"
      title={detail}
      className="flex items-center gap-2 rounded-md border border-ink bg-surface px-3 py-1.5 font-mono text-xs text-ink"
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 shrink-0 rounded-full ${dotStyles[state]}`}
      />
      <span className="hidden sm:inline">{detail}</span>
      <span className="sm:hidden">
        {state === "healthy" ? "ok" : state === "checking" ? "…" : "err"}
      </span>
    </div>
  );
}
