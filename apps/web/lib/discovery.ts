import type { ChangePage, ChangeRead, DiscoveryPage, FeedbackRead, FeedbackUpdate, MonitorRead, MonitorUpdate, RunRead } from "../../../packages/shared/src";
import { getApiBaseUrl } from "./api";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly retryable = false, public readonly code?: string) { super(message); this.name = "ApiError"; }
}

/** Callers own cancellation and retry policy. Mutations are never retried here. */
export async function request<T>(path: string, signal: AbortSignal, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const cancel = (): void => controller.abort();
  signal.addEventListener("abort", cancel, { once: true });
  if (signal.aborted) controller.abort();
  const timeout = setTimeout(cancel, 30000);
  try {
  const response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}/api/v1${path}`, {
    ...init, signal: controller.signal, cache: "no-store",
    headers: { ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const messages: Record<number, string> = {
      404: "Esta análise não foi encontrada. Confira o endereço ou inicie outra.",
      409: "A fonte ou a análise mudou. Atualize os dados antes de continuar.",
      422: "Confira os dados enviados. Use a URL de um repositório público do GitHub.",
      429: "Muitas solicitações. Aguarde um pouco antes de tentar novamente.",
      503: "O serviço está indisponível no momento. Tente novamente mais tarde.",
    };
    let code: string | undefined;
    let retryable = response.status === 429 || response.status >= 500;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "error" in body && body.error && typeof body.error === "object") {
        if ("code" in body.error && typeof body.error.code === "string") code = body.error.code;
        if ("retryable" in body.error && typeof body.error.retryable === "boolean") retryable = body.error.retryable;
      }
    } catch { /* A non-JSON response still gets a safe status-based message. */ }
    throw new ApiError(response.status, messages[response.status] ?? "Não foi possível concluir a solicitação. Tente novamente.", retryable, code);
  }
  return await response.json() as T;
  } finally { clearTimeout(timeout); signal.removeEventListener("abort", cancel); }
}

export const discoveryApi = {
  create: (repo_url: string, key: string, signal: AbortSignal): Promise<RunRead> =>
    request("/discoveries", signal, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ repo_url }) }),
  reanalyze: (id: string, signal: AbortSignal): Promise<RunRead> =>
    request(`/discoveries/${encodeURIComponent(id)}/reanalyze`, signal, { method: "POST", body: "{}" }),
  read: (id: string, signal: AbortSignal, cursor?: string): Promise<DiscoveryPage> =>
    request(`/discoveries/${encodeURIComponent(id)}?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`, signal),
  feedback: (id: string, status: FeedbackUpdate["status"], signal: AbortSignal): Promise<FeedbackRead> =>
    request(`/relationships/${encodeURIComponent(id)}/feedback`, signal, { method: "PATCH", body: JSON.stringify({ status }) }),
};

export const monitorApi = {
  read: (runId: string, signal: AbortSignal): Promise<MonitorRead> => request(`/discoveries/${encodeURIComponent(runId)}/monitor`, signal),
  update: (runId: string, input: MonitorUpdate, signal: AbortSignal): Promise<MonitorRead> =>
    request(`/discoveries/${encodeURIComponent(runId)}/monitor`, signal, { method: "PUT", body: JSON.stringify(input) }),
  check: (runId: string, signal: AbortSignal): Promise<MonitorRead> =>
    request(`/discoveries/${encodeURIComponent(runId)}/monitor/check`, signal, { method: "POST", body: "{}" }),
  changes: (runId: string, signal: AbortSignal, cursor?: string): Promise<ChangePage> =>
    request(`/discoveries/${encodeURIComponent(runId)}/changes?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`, signal),
  markRead: (id: string, signal: AbortSignal): Promise<ChangeRead> =>
    request(`/source-changes/${encodeURIComponent(id)}/read`, signal, { method: "POST", body: "{}" }),
};

export function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Não foi possível acessar o serviço. Verifique a conexão e tente novamente.";
}

export function sourceUrl(value: string | null): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : undefined; }
  catch { return undefined; }
}

export function dateLabel(value: string | null): string {
  if (!value) return "Ainda não disponível";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Data indisponível" : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export const statusLabel = { pending: "A avaliar", confirmed: "Relevante", rejected: "Não relevante" } as const;
export const runLabel = { queued: "Na fila", running: "Buscando conexões", completed: "Análise concluída", partial: "Análise parcial", failed: "Análise interrompida" } as const;
export function sourceErrorLabel(code: string): string {
  const labels: Record<string, string> = {
    source_unavailable: "A fonte está indisponível ou não pôde ser acessada. Confira se o repositório continua público.",
    timeout: "A consulta excedeu o tempo disponível. Tente novamente mais tarde.",
    insufficient_context: "Não há contexto suficiente na fonte para sustentar as conexões.",
    analysis_warning: "A análise tem ressalvas. Confira os limites de busca e explicação abaixo.",
    invalid_evidence: "Não foi possível validar as evidências necessárias.",
    internal_error: "O processamento encontrou uma falha. Tente novamente.",
  };
  return labels[code] ?? "Não foi possível concluir a consulta à fonte. Tente novamente mais tarde.";
}
export function warningLabel(code: string): string {
  const labels: Record<string, string> = {
    context_window_limited: "O contexto do projeto excedeu a janela de análise; apenas parte foi considerada.",
    search_timeout: "Parte da busca excedeu o tempo disponível.",
    source_unavailable: "Uma fonte de pesquisa não estava disponível para parte da busca.",
    invalid_candidate: "Um resultado sem dados válidos foi descartado.",
    candidate_budget_reached: "A busca atingiu o limite de artigos candidatos desta análise.",
    explanation_timeout: "Há explicações de contingência porque a geração excedeu o tempo interno desta análise.",
    explanation_unavailable: "Há explicações de contingência porque a geração estava indisponível.",
    explanation_budget_reached: "Há explicações de contingência pelo limite interno de geração desta análise; este aviso não informa a quota do provedor.",
    explanation_invalid: "Há explicações de contingência porque textos gerados não passaram na validação.",
  };
  return labels[code] ?? "Uma etapa da análise registrou uma ressalva. Avalie os resultados com as evidências disponíveis.";
}
export type MapSelection = { kind: "project" } | { kind: "article" | "relationship"; id: string };
