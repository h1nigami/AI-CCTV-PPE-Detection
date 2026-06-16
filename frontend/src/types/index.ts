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
