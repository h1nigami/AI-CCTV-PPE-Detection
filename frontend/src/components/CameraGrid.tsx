import { CameraCell } from "./CameraCell"
import type { CameraInfo } from "../types"

interface CameraGridProps {
  cameras: CameraInfo[]
  isRunning: boolean
  fullscreenCam: string | null
  onCamClick: (camId: string) => void
}

export function CameraGrid({ cameras, isRunning, fullscreenCam, onCamClick }: CameraGridProps) {
  const count = Math.min(cameras.length, 9)

  if (!isRunning || cameras.length === 0) {
    return (
      <div style={styles.centerPanel}>
        <div style={styles.videoArea}>
          <div style={styles.feedPlaceholder}>
            <div style={{ fontSize: "3rem", marginBottom: "12px", opacity: 0.3 }}>📷</div>
            Запустите детекцию для отображения видео
          </div>
        </div>
      </div>
    )
  }

  const visibleCams = fullscreenCam
    ? cameras.filter((c) => c.name === fullscreenCam)
    : cameras

  const cols = fullscreenCam ? 1 : count <= 1 ? 1 : count <= 4 ? 2 : 3

  return (
    <div style={styles.centerPanel}>
      <div style={styles.videoArea}>
        <div
          style={{
            ...styles.grid,
            gridTemplateColumns: `repeat(${cols}, 1fr)`,
          }}
        >
          {visibleCams.map((cam) => (
            <CameraCell
              key={cam.name}
              name={cam.name}
              onClick={() => onCamClick(cam.name)}
              isFullscreen={fullscreenCam === cam.name}
            />
          ))}
        </div>
        {fullscreenCam && (
          <div style={styles.exitHint}>Нажмите на камеру для выхода из полноэкранного режима</div>
        )}
      </div>

      <div style={styles.bottomBar}>
        <div style={styles.camCount}>
          {cameras.length} камера{cameras.length % 10 === 1 ? "" : cameras.length % 10 < 5 ? "ы" : ""} в сети
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  centerPanel: {
    display: "flex",
    flexDirection: "column",
    background: "#080d14",
    flex: 1,
    minWidth: 0,
  },
  videoArea: {
    flex: 1,
    position: "relative",
    background: "#050a10",
    borderBottom: "1px solid #1a3a5c",
    overflow: "hidden",
  },
  grid: {
    display: "grid",
    width: "100%",
    height: "100%",
    gap: "2px",
    background: "#000",
  },
  feedPlaceholder: {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    color: "#4a6a8a",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.8rem",
    letterSpacing: "1px",
  },
  bottomBar: {
    padding: "10px 16px",
    background: "#0d1520",
    borderTop: "1px solid #1a3a5c",
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  camCount: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.72rem",
    color: "#4a6a8a",
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
    fontSize: "0.65rem",
    color: "#4a6a8a",
    letterSpacing: "1px",
    pointerEvents: "none",
    zIndex: 10,
  },
}
