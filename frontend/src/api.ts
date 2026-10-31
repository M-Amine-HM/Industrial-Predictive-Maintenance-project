import type { BatchResponse, DriftResponse, ErrorDetail, Figure, ModelInfo, Prediction, Reading } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public details: ErrorDetail[] = [], public requestId?: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    let details: ErrorDetail[] = [];
    let requestId: string | undefined;
    try {
      const body = await res.json();
      message = body.message ?? (typeof body.detail === "string" ? body.detail : message);
      details = body.details ?? [];
      requestId = body.request_id ?? undefined;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message, details, requestId);
  }
  return res.json() as Promise<T>;
}

const upload = <T>(path: string, file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return request<T>(path, { method: "POST", body: fd });
};

export const api = {
  health: () => request<{ status: string; model_loaded: boolean; model_version: string }>("/api/health"),
  modelInfo: () => request<ModelInfo>("/api/model-info"),
  predict: (r: Reading, signal?: AbortSignal) =>
    request<Prediction>("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(r),
      signal,
    }),
  sample: (kind: string) => request<Reading>(`/api/samples?kind=${encodeURIComponent(kind)}`),
  predictFile: (file: File) => upload<BatchResponse>("/api/predict/file", file),
  driftFile: (file: File) => upload<DriftResponse>("/api/drift/file", file),
  figures: () => request<Figure[]>("/api/figures"),
  figureUrl: (url: string) => BASE + url,
};
