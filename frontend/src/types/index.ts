// ===== Существующие типы (без изменений) =====

export interface LogEntry {
  id: string
  timestamp: string
  message: string
  category: string
  cam_id: string
  global_id: number
}

export interface CameraConfig {
  source: string | number
  detect_enabled: boolean
}

export interface Cameras {
  [name: string]: CameraConfig
}

export interface CameraInfo {
  name: string
  source: string | number
  detect_enabled: boolean
}

export interface ReidPerson {
  global_id: number
  name: string
  last_seen: number
  cameras: string[]
  embedding_count: number
}

export interface ReidStats {
  total_persons: number
  total_approved: number
}

export interface ApiStatus {
  status: string
}

export interface ApiError {
  error: string
}

export interface PpeStatus {
  helmet: boolean | null
  mask: boolean | null
  vest: boolean | null
  zone: boolean | null
  gesture: boolean | null
}

export interface PersonSummary {
  name: string
  ppe: string
  approved: boolean
  danger: boolean
  violation: boolean
  index: number
}

export interface User {
  id: number
  username: string
  email?: string
  role: "admin" | "operator" | "viewer" | "api"
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: User
}

// ===== Новые типы для диспетчерского интерфейса =====

/** Режим стрима камеры — статичный (кадр раз в N сек) или живой (FPS) */
export type StreamMode = "static" | "live" | "offline"

/** Статус соединения камеры */
export type CameraStatus = "online" | "offline" | "error"

/** Группа камер для фильтрации на дашборде */
export interface CameraGroup {
  id: string
  name: string
  /** Имена камер в группе */
  cameraNames: string[]
}

/** Событие для таймлайна / списка в диспетчерской */
export interface TimelineEvent {
  id: string
  cameraName: string
  timestamp: number
  label: string
  subLabel: string | null
  personName: string | null
  personId: number | null
  hasClip: boolean
  hasSnapshot: boolean
  clipUrl: string | null
  snapshotUrl: string | null
  score: number | null
  ppeHelmet: boolean
  ppeMask: boolean
  ppeVest: boolean
  startTime: number
  endTime: number | null
  boxX: number | null
  boxY: number | null
  boxW: number | null
  boxH: number | null
}

/** Серверное UI-уведомление (показывается сверху) */
export interface ServerNotification {
  id: string
  type: string
  title: string
  sub?: string
  timestamp: number
}

/** Пользовательская полигональная зона (редактор зон) */
export type ZoneType = "danger" | "restricted" | "mask"
export interface Zone {
  id?: string
  name: string
  type: ZoneType
  /** Вершины в нормализованных координатах [0..1] относительно кадра */
  points: [number, number][]
  require_ppe: string[]
}

/** Сегмент непрерывной записи (NVR-архив) */
export interface RecordingSegment {
  id: string
  cameraId: string
  startTime: number
  endTime: number
  duration: number
  sizeBytes: number
  hasMotion: boolean
  playUrl: string
}

/** Состояние диспетчерской панели */
export interface DispatcherState {
  /** Открыта ли панель */
  open: boolean
  /** Выбранная камера */
  cameraName: string | null
}

/** Расширенная информация о камере для отображения в сетке */
export interface CameraCardInfo {
  name: string
  source: string | number
  detectEnabled: boolean
  status: CameraStatus
  streamMode: StreamMode
}
