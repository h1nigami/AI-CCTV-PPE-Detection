import { useState, useEffect, useRef } from "react"
import { api } from "../api/client"

interface CameraCellProps {
  name: string
  onClick: () => void
  isFullscreen?: boolean
}

export function CameraCell({ name, onClick, isFullscreen }: CameraCellProps) {
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
          <div style={styles.spinnerText}>{error ? "Нет сигнала" : "Подключение..."}</div>
        </div>
      )}

      <div style={styles.label}>{name.toUpperCase()}</div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  cell: {
    position: "relative",
    overflow: "hidden",
    background: "#050a10",
    cursor: "pointer",
    minHeight: 0,
  },
  cellFullscreen: {
    outline: "2px solid #00e5ff",
    outlineOffset: "-2px",
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
    background: "#050a10",
    gap: "8px",
    pointerEvents: "none",
  },
  spinnerRing: {
    width: "40px",
    height: "40px",
    border: "3px solid #1a3a5c",
    borderTopColor: "#00e5ff",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  spinnerText: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    color: "#4a6a8a",
    letterSpacing: "1px",
  },
  label: {
    position: "absolute",
    top: "6px",
    left: "6px",
    background: "#00000088",
    border: "1px solid #1a3a5c",
    borderRadius: "3px",
    padding: "2px 8px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    color: "#00e5ff",
    letterSpacing: "1px",
    pointerEvents: "none",
  },
}
