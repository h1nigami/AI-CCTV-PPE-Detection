import { useState, useCallback, useEffect, useRef } from "react"
import { CameraGrid } from "../components/CameraGrid"
import { DispatcherPanel } from "../components/DispatcherPanel"
import { GalleryModal } from "../components/GalleryModal"
import { Notifications } from "../components/Notifications"
import { useCamerasContext } from "../contexts/CameraContext"
import { api } from "../api/client"

// ============================================================
// Главная страница дашборда.
// Левая часть — сетка камер, правая — диспетчерская панель.
// ============================================================

export default function DashboardPage() {
  const { cameras, dispatcher, openDispatcher, closeDispatcher } = useCamerasContext()
  const [isRunning, setIsRunning] = useState(false)
  const [fullscreenCam, setFullscreenCam] = useState<string | null>(null)
  const [notifications, setNotifications] = useState<
    { id: string; type: string; title: string; sub?: string; duration: number }[]
  >([])
  const [showGallery, setShowGallery] = useState(false)
  const notifIdRef = useRef(0)

  const addNotification = useCallback(
    (type: string, title: string, sub?: string, duration = 4500) => {
      const id = String(++notifIdRef.current)
      setNotifications((prev) => [...prev.slice(-4), { id, type, title, sub, duration }])
    },
    [],
  )

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  // Клик по камере — открываем диспетчерскую + полноэкран в сетке
  const handleCamClick = useCallback(
    (camName: string) => {
      if (dispatcher.open && dispatcher.cameraName === camName) {
        closeDispatcher()
        setFullscreenCam(null)
      } else {
        openDispatcher(camName)
        setFullscreenCam(camName)
      }
    },
    [dispatcher, openDispatcher, closeDispatcher],
  )

  // При закрытии диспетчерской — сбрасываем fullscreen
  const handleCloseDispatcher = useCallback(() => {
    closeDispatcher()
    setFullscreenCam(null)
  }, [closeDispatcher])

  // Запуск/остановка
  const handleStart = useCallback(async () => {
    try {
      await api.start()
      setIsRunning(true)
    } catch {
      addNotification("violation", "Ошибка запуска")
    }
  }, [addNotification])

  const handleStop = useCallback(async () => {
    try {
      await api.stop()
      setIsRunning(false)
    } catch {
      // игнорируем
    }
  }, [])

  // При монтировании проверяем, не запущена ли система на бэке
  useEffect(() => {
    api.getStatus().then((data) => {
      if (data.running) setIsRunning(true)
    }).catch(() => {
      // игнорируем — бэкенд мог быть не готов
    })
  }, [])

  // Escape для закрытия диспетчерской и полноэкранного режима
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (dispatcher.open) {
          handleCloseDispatcher()
        } else if (fullscreenCam) {
          setFullscreenCam(null)
        }
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [dispatcher.open, fullscreenCam, handleCloseDispatcher])

  return (
    <div style={styles.root}>
      {/* Уведомления */}
      <Notifications notifications={notifications} onRemove={removeNotification} />

      {/* Основной контент */}
      <div style={styles.content}>
        {/* Сетка камер — при открытой диспетчерской показываем выбранную камеру fullscreen */}
        <CameraGrid
          isRunning={isRunning}
          fullscreenCam={fullscreenCam}
          onCamClick={handleCamClick}
        />

        {/* Диспетчерская панель (справа) */}
        {dispatcher.open && <DispatcherPanel />}
      </div>

      {/* Галерея лиц */}
      <GalleryModal open={showGallery} onClose={() => setShowGallery(false)} />

      {/* Нижняя панель статуса */}
      <div style={styles.statusBar}>
        <div style={styles.statusLeft}>
          {/* Кнопки старт/стоп */}
          <button
            style={{ ...styles.statusBtn, ...(isRunning ? styles.btnActive : {}) }}
            onClick={handleStart}
            disabled={isRunning}
          >
            ▶ ЗАПУСТИТЬ
          </button>
          <button
            style={{ ...styles.statusBtn, ...(isRunning ? {} : styles.btnActive) }}
            onClick={handleStop}
            disabled={!isRunning}
          >
            ■ СТОП
          </button>
          <button
            style={{ ...styles.statusBtn }}
            onClick={() => setShowGallery(true)}
          >
            👤 ЛИЦА
          </button>
        </div>

        <div style={styles.statusCenter}>
          <div
            style={{
              ...styles.liveDot,
              background: isRunning ? "#00ff88" : "#ff3355",
              boxShadow: isRunning ? "0 0 6px #00ff88" : "0 0 6px #ff3355",
            }}
          />
          <span style={{ color: isRunning ? "#00ff88" : "#ff3355" }}>
            {isRunning ? "СИСТЕМА АКТИВНА" : "ОСТАНОВЛЕНА"}
          </span>
        </div>

        <div style={styles.statusRight}>
          <span style={styles.camCount}>
            {cameras.length} камера{cameras.length % 10 === 1 ? "" : cameras.length % 10 < 5 ? "ы" : ""}
          </span>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#080d14",
    color: "#c8dff0",
    fontFamily: "'Exo 2', sans-serif",
    overflow: "hidden",
    minHeight: 0,
  },
  content: {
    flex: 1,
    display: "flex",
    overflow: "hidden",
    minHeight: 0,
  },
  statusBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 16px",
    background: "#0d1520",
    borderTop: "1px solid #1a3a5c",
    flexShrink: 0,
    gap: "16px",
  },
  statusLeft: {
    display: "flex",
    gap: "6px",
  },
  statusBtn: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.65rem",
    letterSpacing: "1px",
    border: "1px solid #1a3a5c",
    borderRadius: "4px",
    padding: "4px 12px",
    cursor: "pointer",
    background: "transparent",
    color: "#4a6a8a",
    textTransform: "uppercase",
    transition: "all 0.2s",
  },
  btnActive: {
    borderColor: "#00e5ff44",
    color: "#00e5ff",
  },
  statusCenter: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    letterSpacing: "1px",
  },
  liveDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    animation: "blink 1.2s ease-in-out infinite",
  },
  statusRight: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.6rem",
    color: "#4a6a8a",
  },
  camCount: {},
}
