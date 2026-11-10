export interface ApiHealth {
  status: string;
  database?: string;
  version?: string;
  apiUrl: string;
  detail?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toStringField(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

/**
 * Consulta a saúde do backend em `/api/v1/health`.
 * Nunca lança exceção: em falha de rede/resposta retorna
 * `{ status: "unreachable", ... }` para a UI degradar com graça.
 */
export async function getApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  const apiUrl = getApiBaseUrl();
  const target = `${apiUrl.replace(/\/$/, "")}/api/v1/health`;

  try {
    const res = await fetch(target, { cache: "no-store", signal });

    if (!res.ok) {
      return {
        status: "unreachable",
        apiUrl,
        detail: `HTTP ${res.status} em ${target}`
      };
    }

    const data: unknown = await res.json();

    if (!isRecord(data)) {
      return {
        status: "unreachable",
        apiUrl,
        detail: "Resposta inesperada do backend"
      };
    }

    return {
      status: toStringField(data["status"]) ?? "unknown",
      database: toStringField(data["database"]),
      version: toStringField(data["version"]),
      apiUrl,
      detail: toStringField(data["detail"])
    };
  } catch (err: unknown) {
    const detail = err instanceof Error ? err.message : "fetch falhou";
    return {
      status: "unreachable",
      apiUrl,
      detail
    };
  }
}
