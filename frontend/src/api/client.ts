import type { Cameras, LogEntry, ReidPerson, ReidStats, ApiStatus, ApiError } from "../types"

const BASE = ""

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as ApiError).error || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  // Detection control
  start: () => request<ApiStatus>("/start", { method: "POST" }),
  stop: () => request<ApiStatus>("/stop", { method: "POST" }),

  // Cameras
  getCameras: () => request<{ cameras: Cameras }>("/cameras"),
  addCamera: (name: string, source: string | number) =>
    request<ApiStatus & { name: string }>("/api/cameras", {
      method: "POST",
      body: JSON.stringify({ name, source }),
    }),
  updateCamera: (id: string, source: string | number) =>
    request<ApiStatus>(`/api/cameras/${id}`, {
      method: "PUT",
      body: JSON.stringify({ source }),
    }),
  deleteCamera: (id: string) =>
    request<ApiStatus>(`/api/cameras/${id}`, { method: "DELETE" }),
  renameCamera: (id: string, newName: string) =>
    request<ApiStatus>(`/api/cameras/${id}/rename`, {
      method: "POST",
      body: JSON.stringify({ name: newName }),
    }),

  // Logs
  getLogs: (camId?: string) => {
    const params = camId ? `?cam_id=${camId}` : ""
    return request<{ logs: LogEntry[] }>(`/detection_log${params}`)
  },

  // ReID
  getReidPersons: () => request<{ persons: ReidPerson[] }>("/api/reid/persons"),
  renameReidPerson: (id: number, name: string) =>
    request<ApiStatus>(`/api/reid/persons/${id}/rename`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteReidPerson: (id: number) =>
    request<ApiStatus>(`/api/reid/persons/${id}`, { method: "DELETE" }),
  clearReid: () =>
    request<ApiStatus>("/api/reid/clear", { method: "POST" }),
  getReidStats: () => request<ReidStats>("/api/reid/stats"),

  // Frame URL helper
  getFrameUrl: (camId: string) => `/video_frame/${camId}?t=${Date.now()}`,
}
