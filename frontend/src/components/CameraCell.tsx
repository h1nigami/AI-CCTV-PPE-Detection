import { useState, useEffect, useRef } from "react"
import { api } from "../api/client"

interface CameraCellProps {
  name: string
  detectEnabled: boolean
  onClick: () => void
  isFullscreen?: boolean
}

export function CameraCell({ name, detectEnabled, onClick, isFullscreen }: CameraCellProps) {
  const [src, setSrc] = useState("")
  const [error, setError] = useState(false)
  const [hasFrame, setHasFrame] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const refresh = () => {
      setSrc(api.getFrameUrl(name))
      setError(false)
    }
    refresh()
    intervalRef.current = setInterval(refresh, 150)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [name])

  return (
    <div style={{ ...styles.cell, ...(isFullscreen ? styles.cellFullscreen : {}) }} onClick={onClick}>
      {!detectEnabled && (
        <div style={styles.overlay}>
          <div style={styles.overlayText}>DETECT OFF</div>
        </div>
      )}
      <img
        src={src}
        alt={name}
        style={styles.img}
        onLoad={() => {
          setHasFrame(true)
          setError(false)
        }}
        onError={() => {
          if (!hasFrame) setError(true)
        }}
      />

      {(!hasFrame || error) && (
        <div style={styles.spinner}>
          <div style={styles.spinnerRing} />
          <div style={styles.spinnerText}>{error ? "NO SIGNAL" : "CONNECTING..."}</div>
        </div>
      )}

      <div style={styles.label}>
        {name.toUpperCase()}
        {!detectEnabled && <span style={{ color: "#ff5566", marginLeft: "6px" }}>DETECT OFF</span>}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  cell: {
    position: "relative",
    overflow: "hidden",
    background: "#111",
    cursor: "pointer",
    minHeight: 0,
  },
  cellFullscreen: {
    outline: "2px solid #00e676",
    outlineOffset: "-2px",
  },
  overlay: {
    position: "absolute",
    inset: 0,
    zIndex: 3,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(0,0,0,0.6)",
    pointerEvents: "none",
  },
  overlayText: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "1.2rem",
    color: "#f44336",
    letterSpacing: "3px",
    border: "2px solid #f44336",
    padding: "8px 20px",
    borderRadius: "8px",
    background: "rgba(42,26,26,0.8)",
  },
  img: {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    display: "block",
    background: "#000",
  },
  spinner: {
    position: "absolute",
    inset: 0,
    zIndex: 2,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    background: "#111",
    gap: "8px",
    pointerEvents: "none",
  },
  spinnerRing: {
    width: "40px",
    height: "40px",
    border: "3px solid #333",
    borderTopColor: "#00e676",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  spinnerText: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.65rem",
    color: "#888",
    letterSpacing: "1px",
  },
  label: {
    position: "absolute",
    top: "6px",
    left: "6px",
    background: "#00000088",
    border: "1px solid #333",
    borderRadius: "6px",
    padding: "2px 8px",
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.65rem",
    color: "#00e676",
    letterSpacing: "1px",
    pointerEvents: "none",
  },
}
