import { useState, useCallback, useRef, useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider, useAuth } from "./contexts/AuthContext"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import { Header } from "./components/Header"
import { CameraGrid } from "./components/CameraGrid"
import { LeftPanel } from "./components/LeftPanel"
import { RightPanel } from "./components/RightPanel"
import { Notifications } from "./components/Notifications"
import { GalleryModal } from "./components/GalleryModal"
import { CameraManagerModal } from "./components/CameraManagerModal"
import { useLogs } from "./hooks/useLogs"
import { useCameras } from "./hooks/useCameras"
import { api } from "./api/client"
import type { LogEntry } from "./types"

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuth, loading } = useAuth()
  if (loading) return null
  if (!isAuth) return <Navigate to="/login" replace />
  return <>{children}</>
}

function Dashboard() {
  const [isRunning, setIsRunning] = useState(false)
  const [selectedCam, setSelectedCam] = useState<string | null>(null)
  const [fullscreenCam, setFullscreenCam] = useState<string | null>(null)
  const [showGallery, setShowGallery] = useState(false)
  const [showCameraManager, setShowCameraManager] = useState(false)

  const { cameraList, refresh: refreshCameras } = useCameras()
  const logs = useLogs(isRunning, selectedCam)

  const lastLogIdsRef = useRef<Record<string, string>>({})
  const [notifications, setNotifications] = useState<
    { id: string; type: string; title: string; sub?: string; duration: number }[]
  >([])
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
      setSelectedCam(null)
      setFullscreenCam(null)
    } catch {
      // ignore
    }
  }, [])

  const exitFullscreen = useCallback(() => {
    setFullscreenCam(null)
    setSelectedCam(null)
  }, [])

  const handleCamClick = useCallback(
    (camId: string) => {
      if (fullscreenCam === camId) {
        exitFullscreen()
      } else {
        setFullscreenCam(camId)
        setSelectedCam(camId)
      }
    },
    [fullscreenCam, exitFullscreen],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && fullscreenCam) exitFullscreen()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [fullscreenCam, exitFullscreen])

  return (
    <div style={styles.root}>
      <Notifications notifications={notifications} onRemove={removeNotification} />

      <Header isRunning={isRunning} />

      <div style={styles.dashboard}>
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

        <CameraGrid
          cameras={cameraList}
          isRunning={isRunning}
          fullscreenCam={fullscreenCam}
          onCamClick={handleCamClick}
        />

        <RightPanel logs={logs} />
      </div>

      <GalleryModal open={showGallery} onClose={() => setShowGallery(false)} />

      <CameraManagerModal
        open={showCameraManager}
        cameraList={cameraList}
        isRunning={isRunning}
        onClose={() => setShowCameraManager(false)}
        onRefresh={refreshCameras}
      />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    background: "#080d14",
    color: "#c8dff0",
    fontFamily: "'Exo 2', sans-serif",
    overflow: "hidden",
  },
  dashboard: {
    flex: 1,
    display: "grid",
    gridTemplateColumns: "240px 1fr 280px",
    overflow: "hidden",
  },
}
