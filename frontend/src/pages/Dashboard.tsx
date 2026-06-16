import { useState, useCallback, useEffect, useRef } from "react"
import { CameraGrid } from "../components/CameraGrid"
import { DispatcherPanel } from "../components/DispatcherPanel"
import { GalleryModal } from "../components/GalleryModal"
import { CameraManagerModal } from "../components/CameraManagerModal"
import { Notifications } from "../components/Notifications"
import { LeftPanel } from "../components/LeftPanel"
import { RightPanel } from "../components/RightPanel"
import { useCamerasContext } from "../contexts/CameraContext"
import { api } from "../api/client"
import type { LogEntry } from "../types"

export default function DashboardPage() {
  const { cameras, dispatcher, openDispatcher, closeDispatcher } = useCamerasContext()
  const [isRunning, setIsRunning] = useState(false)
  const [fullscreenCam, setFullscreenCam] = useState<string | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [notifications, setNotifications] = useState<
    { id: string; type: string; title: string; sub?: string; duration: number }[]
  >([])
  const [showGallery, setShowGallery] = useState(false)
  const [showCameraManager, setShowCameraManager] = useState(false)
  const notifIdRef = useRef(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastLogIdsRef = useRef<Record<string, string>>({})

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

  const handleCloseDispatcher = useCallback(() => {
    closeDispatcher()
    setFullscreenCam(null)
  }, [closeDispatcher])

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
      setLogs([])
    } catch {
      // ignore
    }
  }, [])

  const selectedCam = dispatcher.open ? dispatcher.cameraName : fullscreenCam

  const filteredLogs = selectedCam ? logs.filter((l) => l.cam_id === selectedCam) : logs

  // Poll logs
  useEffect(() => {
    if (!isRunning) return
    const fetchLogs = async () => {
      try {
        const data = await api.getLogs()
        setLogs(data.logs)
      } catch {
        // ignore
      }
    }
    fetchLogs()
    pollRef.current = setInterval(fetchLogs, 1500)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [isRunning])

  useEffect(() => {
    api.getStatus().then((data) => {
      if (data.running) setIsRunning(true)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (dispatcher.open) handleCloseDispatcher()
        else if (fullscreenCam) setFullscreenCam(null)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [dispatcher.open, fullscreenCam, handleCloseDispatcher])

  return (
    <div style={styles.root}>
      <Notifications notifications={notifications} onRemove={removeNotification} />

      <div style={styles.main}>
        <LeftPanel
          isRunning={isRunning}
          selectedCam={selectedCam}
          logs={logs}
          lastLogIdsRef={lastLogIdsRef}
          addNotification={addNotification}
          onStart={handleStart}
          onStop={handleStop}
          onShowGallery={() => setShowGallery(true)}
          onShowCameraManager={() => setShowCameraManager(true)}
        />

        <div style={styles.center}>
          <div style={styles.videoArea}>
            <CameraGrid
              isRunning={isRunning}
              fullscreenCam={fullscreenCam}
              onCamClick={handleCamClick}
            />
          </div>

          <div style={styles.hintBar} id="hintBar">
            <span id="hintText" style={{ color: "var(--text-mid)", fontSize: "1.05rem", fontWeight: 500 }}>
              {isRunning ? "Система активна" : "Запустите детекцию"}
            </span>
          </div>

          <div style={styles.uploadBar}>
            <form
              style={styles.uploadForm}
              onSubmit={(e) => {
                e.preventDefault()
                const input = (e.target as HTMLFormElement).querySelector("input[type=file]") as HTMLInputElement
                if (!input?.files?.[0]) return
                const fd = new FormData()
                fd.append("file", input.files[0])
                fetch("/upload", { method: "POST", body: fd })
                  .then((r) => r.blob())
                  .then((blob) => {
                    const url = URL.createObjectURL(blob)
                    window.open(url, "_blank")
                  })
                  .catch(() => {})
              }}
            >
              <input type="file" name="file" accept="image/*,video/*" style={styles.fileInput} />
              <button type="submit" className="btn-upload" style={styles.uploadBtn}>
                Обработать файл
              </button>
            </form>
          </div>
        </div>

        <RightPanel
          logs={selectedCam ? logs.filter((l) => l.cam_id === selectedCam) : logs}
        />
      </div>

      {dispatcher.open && (
        <div style={styles.overlay} onClick={handleCloseDispatcher}>
          <div style={styles.overlayPanel} onClick={(e) => e.stopPropagation()}>
            <DispatcherPanel />
          </div>
        </div>
      )}

      <GalleryModal open={showGallery} onClose={() => setShowGallery(false)} />
      <CameraManagerModal
        open={showCameraManager}
        cameraList={cameras}
        isRunning={isRunning}
        onClose={() => setShowCameraManager(false)}
        onRefresh={() => {}}
      />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#1a1a1a",
    color: "#ffffff",
    fontFamily: "'Inter', sans-serif",
    overflow: "hidden",
    minHeight: 0,
    position: "relative",
  },
  main: {
    flex: 1,
    display: "grid",
    gridTemplateColumns: "260px 1fr 260px",
    overflow: "hidden",
    minHeight: 0,
  },
  center: {
    display: "flex",
    flexDirection: "column",
    background: "#1a1a1a",
    overflow: "hidden",
    minHeight: 0,
  },
  videoArea: {
    flex: 1,
    display: "flex",
    minHeight: 0,
    overflow: "hidden",
    position: "relative" as const,
  },
  hintBar: {
    height: "60px",
    background: "#222222",
    borderTop: "1px solid #333333",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "10px",
    flexShrink: 0,
  },
  uploadBar: {
    height: "46px",
    background: "#1a1a1a",
    borderTop: "1px solid #333333",
    display: "flex",
    alignItems: "center",
    padding: "0 16px",
    flexShrink: 0,
  },
  uploadForm: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flex: 1,
  },
  fileInput: {
    flex: 1,
    fontSize: "0.75rem",
    color: "#888888",
    background: "#2a2a2a",
    border: "1px solid #333333",
    borderRadius: "6px",
    padding: "4px 10px",
  },
  uploadBtn: {
    background: "transparent",
    border: "1px solid #333333",
    color: "#888888",
    borderRadius: "6px",
    padding: "5px 14px",
    fontSize: "0.78rem",
    cursor: "pointer",
    whiteSpace: "nowrap" as const,
    fontFamily: "'Inter', sans-serif",
    transition: "all .2s",
  },
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 500,
    background: "#00000099",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  overlayPanel: {
    maxWidth: "90vw",
    maxHeight: "90vh",
    overflow: "auto",
    borderRadius: "12px",
  },
}
