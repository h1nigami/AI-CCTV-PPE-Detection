import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from "react"
import { api } from "../api/client"
import type { CameraInfo, CameraGroup, DispatcherState, TimelineEvent, CameraStatus, CameraCardInfo, StreamMode, LogEntry } from "../types"

// ============================================================
// Контекст управления камерами, группами и диспетчерской панелью
// ============================================================

interface CameraContextType {
  /** Все камеры (сырые данные с бэка) */
  cameras: CameraInfo[]
  /** Загрузка */
  loading: boolean
  /** Обновить список камер */
  refresh: () => Promise<void>

  // ---- Группы ----
  /** Список групп */
  groups: CameraGroup[]
  /** Активная группа (null = "Все") */
  activeGroupId: string | null
  /** Выбрать группу */
  setActiveGroup: (id: string | null) => void
  /** Отфильтрованные по группе камеры */
  filteredCameras: CameraInfo[]

  // ---- Диспетчерская панель ----
  /** Состояние панели */
  dispatcher: DispatcherState
  /** Открыть диспетчерскую для камеры */
  openDispatcher: (cameraName: string) => void
  /** Закрыть диспетчерскую */
  closeDispatcher: () => void

  // ---- События (заглушка для фронта) ----
  /** События для выбранной камеры */
  getEventsForCamera: (cameraName: string) => TimelineEvent[]
  /** Все последние события */
  recentEvents: TimelineEvent[]

  // ---- Статус камер ----
  /** Получить расширенную инфу для карточки */
  getCardInfo: (cam: CameraInfo) => CameraCardInfo

  // ---- Детекция ----
  /** Запущена ли детекция на бэке */
  isRunning: boolean
  /** Установить флаг детекции (вызывается после api.start/api.stop) */
  setDetectionRunning: (running: boolean) => void

  // ---- Логи (единый источник поллинга на всё приложение) ----
  /** Последние логи детекции (по всем камерам) */
  logs: LogEntry[]

  // ---- Режимы детекции ----
  /** Текущие режимы детекции (people / ppe / faces) */
  detectModes: Record<string, boolean> | null
  /** Обновить режимы детекции с бэка */
  refreshDetectModes: () => Promise<void>
}

const CameraContext = createContext<CameraContextType | null>(null)

// Захардкоженные группы — в реальном приложении придут с бэка
const DEFAULT_GROUPS: CameraGroup[] = [
  { id: "all", name: "Все камеры", cameraNames: [] },
  { id: "entrance", name: "Вход", cameraNames: [] },
  { id: "perimeter", name: "Периметр", cameraNames: [] },
  { id: "workshop", name: "Цех", cameraNames: [] },
]

export function CameraProvider({ children }: { children: ReactNode }) {
  const [cameras, setCameras] = useState<CameraInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [activeGroupId, setActiveGroupId] = useState<string | null>("all")
  const [dispatcher, setDispatcher] = useState<DispatcherState>({ open: false, cameraName: null })
  const [groups] = useState<CameraGroup[]>(DEFAULT_GROUPS)
  const [isRunning, setDetectionRunning] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [detectModes, setDetectModes] = useState<Record<string, boolean> | null>(null)

  // Храним последние события для каждой камеры (симуляция)
  const eventsByCamera = useRef<Record<string, TimelineEvent[]>>({})

  // Единый поллинг логов на всё приложение (Dashboard и DispatcherPanel читают
  // их отсюда, чтобы не плодить параллельные интервалы на /detection_log).
  useEffect(() => {
    if (!isRunning) {
      setLogs([])
      return
    }
    let alive = true
    const fetchLogs = async () => {
      try {
        const data = await api.getLogs()
        if (alive) setLogs(data.logs)
      } catch {
        // ignore
      }
    }
    fetchLogs()
    const id = setInterval(fetchLogs, 1500)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [isRunning])

  // Получаем камеры с бэка
  const refresh = useCallback(async () => {
    try {
      const data = await api.getCameras()
      const list: CameraInfo[] = Object.entries(data.cameras).map(([name, cfg]) => ({
        name,
        source: typeof cfg === "object" && cfg !== null ? cfg.source : cfg,
        detect_enabled: typeof cfg === "object" && cfg !== null ? cfg.detect_enabled : true,
      }))
      setCameras(list)
    } catch {
      // При ошибке оставляем предыдущее состояние
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const refreshDetectModes = useCallback(async () => {
    try {
      const data = await api.getDetectModes()
      setDetectModes(data.modes)
    } catch {
      // ignore
    }
  }, [])

  // Первичная загрузка detectModes и фоновый поллинг при isRunning
  useEffect(() => {
    refreshDetectModes()
    if (!isRunning) return
    const id = setInterval(refreshDetectModes, 10000)
    return () => clearInterval(id)
  }, [isRunning, refreshDetectModes])

  // Получаем статус детекции при монтировании провайдера (один раз)
  useEffect(() => {
    api.getStatus().then((data) => {
      if (data.running) setDetectionRunning(true)
    }).catch(() => {})
  }, [])

  // ---- Логика групп ----
  const setActiveGroup = useCallback((id: string | null) => {
    setActiveGroupId(id)
  }, [])

  // Фильтруем камеры по активной группе
  const filteredCameras = cameras.filter((cam) => {
    if (!activeGroupId || activeGroupId === "all") return true
    const group = groups.find((g) => g.id === activeGroupId)
    if (!group) return true
    return group.cameraNames.includes(cam.name)
  })

  // ---- Диспетчерская панель ----
  const openDispatcher = useCallback((cameraName: string) => {
    setDispatcher({ open: true, cameraName })
  }, [])

  const closeDispatcher = useCallback(() => {
    setDispatcher({ open: false, cameraName: null })
  }, [])

  // ---- Генерация тестовых событий (заглушка) ----
  const getEventsForCamera = useCallback((cameraName: string): TimelineEvent[] => {
    return eventsByCamera.current[cameraName] || []
  }, [])

  const recentEvents = Object.values(eventsByCamera.current).flat().slice(0, 50)

  // ---- Расширенная информация для карточки ----
  const getCardInfo = useCallback(
    (cam: CameraInfo): CameraCardInfo => {
      return {
        name: cam.name,
        source: cam.source,
        detectEnabled: cam.detect_enabled,
        status: "online",
        streamMode: "live",
      }
    },
    [],
  )

  return (
    <CameraContext.Provider
      value={{
        cameras,
        loading,
        refresh,
        groups,
        activeGroupId,
        setActiveGroup,
        filteredCameras,
        dispatcher,
        openDispatcher,
        closeDispatcher,
        getEventsForCamera,
        recentEvents,
        getCardInfo,
        isRunning,
        setDetectionRunning,
        logs,
        detectModes,
        refreshDetectModes,
      }}
    >
      {children}
    </CameraContext.Provider>
  )
}

export function useCamerasContext() {
  const ctx = useContext(CameraContext)
  if (!ctx) throw new Error("useCamerasContext должен использоваться внутри CameraProvider")
  return ctx
}
