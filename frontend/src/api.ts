import type { BatchResponse, Figure, ModelInfo, Prediction, Reading } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; model_loaded: boolean }>("/api/health"),
  modelInfo: () => request<ModelInfo>("/api/model-info"),
  predict: (r: Reading, signal?: AbortSignal) =>
    request<Prediction>("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(r),
      signal,
    }),
  sample: (kind: string) => request<Reading>(`/api/samples?kind=${encodeURIComponent(kind)}`),
  predictCsv: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<BatchResponse>("/api/predict/csv", { method: "POST", body: fd });
  },
  figures: () => request<Figure[]>("/api/figures"),
  figureUrl: (url: string) => BASE + url,
};
