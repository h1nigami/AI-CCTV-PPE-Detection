import type {
  Cameras,
  LogEntry,
  ReidPerson,
  ReidStats,
  ApiStatus,
  ApiError,
  AuthResponse,
  User,
  TimelineEvent,
} from "../types"

// ============================================================
// API-клиент. Все запросы через единый механизм с JWT-авторизацией
// и автоматическим refresh токена.
// ============================================================

const BASE = ""

let accessToken: string | null = localStorage.getItem("access_token")
let refreshToken: string | null = localStorage.getItem("refresh_token")

export function setTokens(access: string, refresh: string) {
  accessToken = access
  refreshToken = refresh
  localStorage.setItem("access_token", access)
  localStorage.setItem("refresh_token", refresh)
}

export function clearTokens() {
  accessToken = null
  refreshToken = null
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

export function getAccessToken() {
  return accessToken
}

export function isAuthenticated() {
  return !!accessToken
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`
  }
  const res = await fetch(`${BASE}${url}`, { headers, ...options })
  if (res.status === 401 && refreshToken) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      headers["Authorization"] = `Bearer ${accessToken}`
      const retry = await fetch(`${BASE}${url}`, { headers, ...options })
      if (!retry.ok) {
        const body = await retry.json().catch(() => ({}))
        throw new Error((body as ApiError).error || `HTTP ${retry.status}`)
      }
      return retry.json()
    }
    clearTokens()
    window.location.href = "/login"
    throw new Error("Session expired")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as ApiError).error || `HTTP ${res.status}`)
  }
  return res.json()
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const data = await res.json()
    accessToken = data.access_token
    localStorage.setItem("access_token", data.access_token)
    return true
  } catch {
    return false
  }
}

export const api = {
  // ---- Аутентификация ----
  login: (username: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string, email?: string) =>
    request<{ id: number; username: string; role: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password, email }),
    }),
  me: () => request<User>("/api/auth/me"),

  // ---- Статус системы ----
  getStatus: () => request<{ running: boolean }>("/api/status"),

  // ---- Управление детекцией ----
  start: () => request<ApiStatus>("/start", { method: "POST" }),
  stop: () => request<ApiStatus>("/stop", { method: "POST" }),

  // ---- Камеры ----
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
  toggleAnalytics: (id: string, detect_enabled: boolean) =>
    request<ApiStatus>(`/api/cameras/${id}/analytics`, {
      method: "PUT",
      body: JSON.stringify({ detect_enabled }),
    }),

  // ---- Логи ----
  getLogs: (camId?: string) => {
    const params = camId ? `?cam_id=${camId}` : ""
    return request<{ logs: LogEntry[] }>(`/detection_log${params}`)
  },

  // ---- ReID ----
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

  // ---- События (для таймлайна) ----
  getEvents: (opts?: { camera?: string; label?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams()
    if (opts?.camera) params.set("camera", opts.camera)
    if (opts?.label) params.set("label", opts.label)
    if (opts?.limit) params.set("limit", String(opts.limit))
    if (opts?.offset) params.set("offset", String(opts.offset))
    const qs = params.toString()
    return request<{ events: TimelineEvent[]; total: number; offset: number; limit: number }>(
      `/api/events${qs ? `?${qs}` : ""}`
    )
  },
  getEventClipUrl: (eventId: string) => `/api/events/${eventId}/clip`,
  getEventSnapshotUrl: (eventId: string) => `/api/events/${eventId}/snapshot`,

  // ---- Режимы детекции ----
  getDetectModes: () =>
    request<{ modes: Record<string, boolean> }>("/api/detect-modes"),
  setDetectModes: (modes: Record<string, boolean>) =>
    request<{ status: string; modes: Record<string, boolean> }>("/api/detect-modes", {
      method: "PUT",
      body: JSON.stringify(modes),
    }),

  // ---- Вспомогательные URL ----
  /** URL одиночного JPEG-кадра для load-driven поллинга (см. CameraCard).
   *  Постоянный MJPEG (/video_feed) намеренно НЕ используем: он держит
   *  соединение+поток на камеру и забивает пулы браузера/Waitress. */
  getFrameUrl: (camId: string) => `/video_frame/${camId}?t=${Date.now()}`,
}
