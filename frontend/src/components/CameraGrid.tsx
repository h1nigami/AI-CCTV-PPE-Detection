import { useMemo } from "react"
import { CameraCard } from "./CameraCard"
import { useCamerasContext } from "../contexts/CameraContext"
import type { CameraInfo } from "../types"

// ============================================================
// Сетка камер — основное поле дашборда.
// Отображает камеры, отфильтрованные по группе.
// При клике на камеру открывается диспетчерская панель.
// ============================================================

interface CameraGridProps {
  /** Если задана — показываем только эту камеру (полноэкран) */
  fullscreenCam?: string | null
  onCamClick?: (camName: string) => void
  /** Запущена ли детекция глобально */
  isRunning: boolean
}

export function CameraGrid({ fullscreenCam, onCamClick, isRunning }: CameraGridProps) {
  const { filteredCameras, openDispatcher } = useCamerasContext()

  // Если полноэкран — показываем только выбранную камеру
  const visibleCams: CameraInfo[] = fullscreenCam
    ? filteredCameras.filter((c) => c.name === fullscreenCam)
    : filteredCameras

  // Определяем количество колонок
  const cols = useMemo(() => {
    const count = visibleCams.length
    if (fullscreenCam) return 1
    if (count <= 1) return 1
    if (count <= 4) return 2
    return 3
  }, [visibleCams.length, fullscreenCam])

  const handleClick = (camName: string) => {
    if (onCamClick) {
      onCamClick(camName)
    } else {
      openDispatcher(camName)
    }
  }

  // Если камер нет — показываем заглушку
  if (visibleCams.length === 0) {
    return (
      <div style={styles.container}>
        <div style={styles.placeholder}>
          <div style={styles.placeholderIcon}>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.15">
              <rect x="4" y="8" width="40" height="28" rx="4" stroke="#4a6a8a" strokeWidth="2" />
              <circle cx="24" cy="22" r="8" stroke="#4a6a8a" strokeWidth="2" />
              <path d="M8 40c0-8 7-14 16-14s16 6 16 14" stroke="#4a6a8a" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <div style={styles.placeholderText}>Нет камер в этой группе</div>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div
        style={{
          ...styles.grid,
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gridTemplateRows: fullscreenCam ? "1fr" : undefined,
        }}
      >
        {visibleCams.map((cam) => (
          <CameraCard
            key={cam.name}
            name={cam.name}
            detectEnabled={cam.detect_enabled}
            status="online"
            isRunning={isRunning}
            onClick={() => handleClick(cam.name)}
            isFullscreen={fullscreenCam === cam.name}
          />
        ))}
      </div>

      {/* Подсказка при полноэкранном режиме */}
      {fullscreenCam && (
        <div style={styles.exitHint}>
          Нажмите Esc или кликните ещё раз для выхода
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    background: "#080d14",
    minWidth: 0,
    overflow: "hidden",
    position: "relative",
  },
  grid: {
    display: "grid",
    width: "100%",
    height: "100%",
    gap: "2px",
    background: "#000",
    flex: 1,
    minHeight: 0,
  },
  placeholder: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    gap: "12px",
  },
  placeholderIcon: {
    width: "48px",
    height: "48px",
  },
  placeholderText: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.75rem",
    color: "#4a6a8a",
    letterSpacing: "1px",
  },
  exitHint: {
    position: "absolute",
    bottom: "12px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "#00000088",
    border: "1px solid #1a3a5c",
    borderRadius: "4px",
    padding: "4px 12px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.6rem",
    color: "#4a6a8a",
    letterSpacing: "1px",
    pointerEvents: "none",
    zIndex: 10,
  },
}
