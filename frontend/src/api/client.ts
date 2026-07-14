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
  RecordingSegment,
  Zone,
  ServerNotification,
  DetectionSettingSpec,
  MovementPerson,
  MovementTrack,
  CameraMappingPoint,
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

  // ---- Реальные метрики (CPU/RAM/FPS) ----
  getStats: () =>
    request<{
      uptime_seconds: number
      cameras: Record<string, { fps: number; latency_ms: number; frames_processed: number; frames_skipped: number }>
      system: { cpu_percent?: number; memory_percent?: number; memory_used_mb?: number }
    }>("/api/stats"),

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
  discoverCameras: (add = false) =>
    request<{
      found: {
        ip: string
        rtsp_url: string | null
        name: string
        status: string // new | added | exists | locked
        requires_auth?: boolean
        port?: number
        added_as?: string
      }[]
      added: string[]
    }>("/api/cameras/discover", { method: "POST", body: JSON.stringify({ add }) }),
  // Добавить запароленную камеру: бэк подберёт рабочий RTSP-URL по логину/паролю.
  discoverAuth: (params: {
    ip: string
    username: string
    password: string
    port?: number
    name?: string
  }) =>
    request<{ ok: boolean; rtsp_url?: string; added_as?: string; error?: string }>(
      "/api/cameras/discover/auth",
      { method: "POST", body: JSON.stringify(params) },
    ),
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
  grantReidPass: (id: number) =>
    request<ApiStatus>(`/api/reid/persons/${id}/approve`, { method: "POST" }),
  revokeReidPass: (id: number) =>
    request<ApiStatus>(`/api/reid/persons/${id}/revoke`, { method: "POST" }),
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

  // ---- NVR-архив (непрерывная запись) ----
  getRecordings: (opts?: { camId?: string; from?: number; to?: number; limit?: number; offset?: number }) => {
    const params = new URLSearchParams()
    if (opts?.camId) params.set("cam_id", opts.camId)
    if (opts?.from) params.set("from", String(opts.from))
    if (opts?.to) params.set("to", String(opts.to))
    if (opts?.limit) params.set("limit", String(opts.limit))
    if (opts?.offset) params.set("offset", String(opts.offset))
    const qs = params.toString()
    return request<{ recordings: RecordingSegment[]; total: number; offset: number; limit: number }>(
      `/api/recordings${qs ? `?${qs}` : ""}`
    )
  },
  getRecordingPlayUrl: (id: string) => `/api/recordings/${id}/play`,

  // ---- Зоны (редактор зон) ----
  getZones: (camId: string) =>
    request<{ zones: Zone[] }>(`/api/cameras/${camId}/zones`),
  saveZones: (camId: string, zones: Zone[]) =>
    request<{ status: string; zones: Zone[] }>(`/api/cameras/${camId}/zones`, {
      method: "PUT",
      body: JSON.stringify({ zones }),
    }),
  deleteZone: (camId: string, zoneId: string) =>
    request<{ status: string; id: string }>(`/api/cameras/${camId}/zones/${zoneId}`, {
      method: "DELETE",
    }),

  // ---- Режимы детекции ----
  getDetectModes: () =>
    request<{ modes: Record<string, boolean> }>("/api/detect-modes"),
  setDetectModes: (modes: Record<string, boolean>) =>
    request<{ status: string; modes: Record<string, boolean> }>("/api/detect-modes", {
      method: "PUT",
      body: JSON.stringify(modes),
    }),

  // ---- Обязательные СИЗ для пропуска по жесту «ОК» ----
  getPpeRequired: () =>
    request<{ required: string[] }>("/api/ppe-required"),
  setPpeRequired: (required: string[]) =>
    request<{ status: string; required: string[] }>("/api/ppe-required", {
      method: "PUT",
      body: JSON.stringify({ required }),
    }),

  // ---- Рантайм-настройки детекции (Настройки → Детекция и логика) ----
  // Бэк отдаёт И текущие значения, И спеку (label/desc/min/max/step/unit/group)
  // — панель рендерится по спеке. PUT принимает частичный патч {settings:{...}}.
  getDetectionSettings: () =>
    request<{ settings: Record<string, number>; spec: DetectionSettingSpec[] }>(
      "/api/detection-settings",
    ),
  setDetectionSettings: (settings: Record<string, number>) =>
    request<{ status: string; settings: Record<string, number> }>(
      "/api/detection-settings",
      { method: "PUT", body: JSON.stringify({ settings }) },
    ),

  // ---- Голосовые предупреждения ----
  // Курсорная модель: ?after=<seq> отдаёт все алерты новее курсора (не извлекая
  // их из общей очереди), без after — только текущий курсор. Несколько вкладок и
  // камер обслуживаются независимо (раньше pop «съедал» алерт у других клиентов).
  getVoiceAlerts: (after?: number) =>
    request<{
      alerts: { id: string; seq: number; cam_id: string; text: string; timestamp: number }[]
      cursor: number
    }>(`/api/voice_alert${after === undefined ? "" : `?after=${after}`}`),
  /** URL готового WAV с синтезированной на бэке (Piper) речью. 503 → фронт
   *  откатывается на Web Speech. Тот же origin (nginx/vite-proxy) → без CORS. */
  getVoiceAlertAudioUrl: (text: string) =>
    `${BASE}/api/voice_alert_audio?text=${encodeURIComponent(text)}`,

  // ---- UI-уведомления (жест ОК / нехватка СИЗ) ----
  getNotifications: () =>
    request<{ notifications: ServerNotification[] }>("/api/notifications"),

  // ---- Перемещения (кто сидит на месте / кто встал и идёт) ----
  // ?cam_id=<id> — по одной камере. Данные эфемерные (последний кадр камеры).
  getMovement: (camId?: string) => {
    const params = camId ? `?cam_id=${camId}` : ""
    return request<{ movement: Record<string, MovementPerson[]> }>(`/api/movement${params}`)
  },
  // Кросс-камерные треки на карте: по личности — единая линия через все камеры.
  getMovementTracks: () =>
    request<{ tracks: MovementTrack[] }>("/api/movement/tracks"),

  // ---- Калибровка карты (гомография кадр→карта) ----
  getCameraMapping: (camId: string) =>
    request<{ map_points: CameraMappingPoint[] }>(`/api/cameras/${camId}/mapping`),
  saveCameraMapping: (camId: string, mapPoints: CameraMappingPoint[]) =>
    request<{ status: string; map_points: CameraMappingPoint[] }>(
      `/api/cameras/${camId}/mapping`,
      { method: "PUT", body: JSON.stringify({ map_points: mapPoints }) },
    ),

  // ---- Вспомогательные URL ----
  /** URL одиночного JPEG-кадра для load-driven поллинга (см. CameraCard).
   *  Постоянный MJPEG (/video_feed) намеренно НЕ используем: он держит
   *  соединение+поток на камеру и забивает пулы браузера/Waitress. */
  getFrameUrl: (camId: string) => `/video_frame/${camId}?t=${Date.now()}`,
}
