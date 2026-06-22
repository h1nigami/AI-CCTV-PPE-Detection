import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from "react"
import { api } from "../api/client"
import type { CameraInfo, DispatcherState, LogEntry } from "../types"

// ============================================================
// Контекст управления камерами, диспетчерской панелью, логами и
// режимами детекции. Единый источник поллинга логов/режимов на всё приложение.
// ============================================================

interface CameraContextType {
  /** Все камеры (сырые данные с бэка) */
  cameras: CameraInfo[]
  /** Загрузка */
  loading: boolean
  /** Обновить список камер */
  refresh: () => Promise<void>

  // ---- Диспетчерская панель ----
  /** Состояние панели */
  dispatcher: DispatcherState
  /** Открыть диспетчерскую для камеры */
  openDispatcher: (cameraName: string) => void
  /** Закрыть диспетчерскую */
  closeDispatcher: () => void

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
  /** Сохранить режимы детекции на бэк (оптимистично обновляет состояние) */
  updateDetectModes: (modes: Record<string, boolean>) => Promise<void>

  // ---- Обязательные СИЗ для пропуска (helmet/mask/vest) ----
  /** Какие СИЗ требуются для пропуска по жесту «ОК» (из настроек). null — ещё не загружено. */
  ppeRequired: string[] | null
  /** Перечитать обязательные СИЗ с бэка */
  refreshPpeRequired: () => Promise<void>
}

const CameraContext = createContext<CameraContextType | null>(null)

export function CameraProvider({ children }: { children: ReactNode }) {
  const [cameras, setCameras] = useState<CameraInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [dispatcher, setDispatcher] = useState<DispatcherState>({ open: false, cameraName: null })
  const [isRunning, setDetectionRunning] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [detectModes, setDetectModes] = useState<Record<string, boolean> | null>(null)
  const [ppeRequired, setPpeRequired] = useState<string[] | null>(null)

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

  // Сохранение режимов на бэк через контекст — единый источник истины, чтобы
  // все потребители (Header, ControlPanel, DispatcherPanel) обновлялись сразу,
  // а не ждали фонового поллинга (раньше Header держал своё локальное состояние).
  const updateDetectModes = useCallback(async (next: Record<string, boolean>) => {
    setDetectModes(next) // оптимистично
    try {
      const data = await api.setDetectModes(next)
      if (data.modes) setDetectModes(data.modes)
    } catch {
      refreshDetectModes() // откат к актуальному состоянию бэка
    }
  }, [refreshDetectModes])

  const refreshPpeRequired = useCallback(async () => {
    try {
      const data = await api.getPpeRequired()
      setPpeRequired(data.required || [])
    } catch {
      // ignore
    }
  }, [])

  // Первичная загрузка detectModes/ppeRequired и фоновый поллинг при isRunning
  // (настройка обязательных СИЗ может меняться на странице настроек).
  useEffect(() => {
    refreshDetectModes()
    refreshPpeRequired()
    if (!isRunning) return
    const id = setInterval(() => {
      refreshDetectModes()
      refreshPpeRequired()
    }, 10000)
    return () => clearInterval(id)
  }, [isRunning, refreshDetectModes, refreshPpeRequired])

  // Получаем статус детекции при монтировании провайдера (один раз)
  useEffect(() => {
    api.getStatus().then((data) => {
      if (data.running) setDetectionRunning(true)
    }).catch(() => {})
  }, [])

  // ---- Диспетчерская панель ----
  const openDispatcher = useCallback((cameraName: string) => {
    setDispatcher({ open: true, cameraName })
  }, [])

  const closeDispatcher = useCallback(() => {
    setDispatcher({ open: false, cameraName: null })
  }, [])

  return (
    <CameraContext.Provider
      value={{
        cameras,
        loading,
        refresh,
        dispatcher,
        openDispatcher,
        closeDispatcher,
        isRunning,
        setDetectionRunning,
        logs,
        detectModes,
        refreshDetectModes,
        updateDetectModes,
        ppeRequired,
        refreshPpeRequired,
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
