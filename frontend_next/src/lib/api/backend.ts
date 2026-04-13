import { getBackendApiBaseUrl } from "@/lib/env";


export class BackendApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "BackendApiError";
    this.status = status;
  }
}


type BackendRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  token?: string | null;
  jsonBody?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
};


function buildUrl(path: string, query?: BackendRequestOptions["query"]): string {
  const url = new URL(`${getBackendApiBaseUrl()}${path}`);
  if (!query) {
    return url.toString();
  }

  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    url.searchParams.set(key, String(value));
  }

  return url.toString();
}


export async function backendFetch<T>(
  path: string,
  options: BackendRequestOptions = {},
): Promise<T> {
  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers: {
      Accept: "application/json",
      ...(options.jsonBody !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.jsonBody !== undefined ? JSON.stringify(options.jsonBody) : undefined,
    cache: "no-store",
  });

  if (response.ok) {
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  let detail = `HTTP ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      detail = payload.detail.trim();
    }
  } catch {
    const textBody = await response.text();
    if (textBody.trim()) {
      detail = textBody.trim();
    }
  }

  throw new BackendApiError(detail, response.status);
}
