import { useState, useEffect, useRef, useCallback } from "react"
import { api } from "../api/client"
import type { CameraStatus } from "../types"

// ============================================================
// Карточка камеры — основной элемент сетки.
// Когда система запущена — использует MJPEG-поток для макс. FPS,
// при ошибке MJPEG падает на HTTP polling.
// Когда система остановлена — показывает "СИСТЕМА ОСТАНОВЛЕНА".
// Клик открывает диспетчерскую панель.
// ============================================================

interface CameraCardProps {
  name: string
  detectEnabled: boolean
  status: CameraStatus
  /** Запущена ли детекция глобально */
  isRunning: boolean
  eventCount?: number
  hasViolation?: boolean
  onClick: () => void
  isFullscreen?: boolean
}

export function CameraCard({
  name,
  detectEnabled,
  status,
  isRunning,
  eventCount = 0,
  hasViolation = false,
  onClick,
  isFullscreen = false,
}: CameraCardProps) {
  const [streamError, setStreamError] = useState(false)
  const [hasFrame, setHasFrame] = useState(false)
  const [pollSrc, setPollSrc] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  // При старте даём браузеру время переподключиться
  const [showRunning, setShowRunning] = useState(isRunning)
  useEffect(() => {
    if (isRunning) {
      setShowRunning(true)
    } else {
      // При остановке — сразу сбрасываем флаг, чтобы показать заглушку
      setShowRunning(false)
      setStreamError(false)
      setHasFrame(false)
    }
  }, [isRunning])

  // MJPEG URL
  const mjpegUrl = api.getFrameUrlMJPEG(name)

  // Сброс стрима при старте/смене камеры
  useEffect(() => {
    if (isRunning) {
      setStreamError(false)
      setHasFrame(false)
    }
  }, [isRunning, name])

  // HTTP polling (fallback для MJPEG или при !isRunning)
  const setupPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (!mountedRef.current) return

    const refresh = () => {
      if (!mountedRef.current || !isRunning) return
      setPollSrc(api.getFrameUrl(name))
    }
    refresh()
    const interval = detectEnabled ? 100 : 2000
    pollRef.current = setInterval(refresh, interval)
  }, [name, detectEnabled, isRunning])

  // Очистка при размонтировании
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Ставим polling когда:
  // - MJPEG упал с ошибкой, или
  // - система остановлена (пока не запустится) — не поллим, просто ждём
  useEffect(() => {
    if (!isRunning) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    if (streamError) {
      setupPolling()
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [isRunning, streamError, setupPolling])

  // Цвет рамки статуса
  const statusColors: Record<CameraStatus, string> = {
    online: "#00ff88",
    offline: "#ff3355",
    error: "#ff6d00",
  }

  const frameSrc = streamError ? pollSrc : mjpegUrl

  return (
    <div
      style={{
        ...styles.card,
        ...(isFullscreen ? styles.cardFullscreen : {}),
        outlineColor: isFullscreen ? "#00e5ff" : statusColors[status],
      }}
      onClick={onClick}
      title={`${name} — ${status === "online" ? "в сети" : status === "offline" ? "нет сигнала" : "ошибка"}`}
    >
      {/* Верхняя панель: имя + статус */}
      <div style={styles.topBar}>
        <div style={styles.camName}>{name.toUpperCase()}</div>
        <div
          style={{
            ...styles.statusDot,
            background: !isRunning ? "#4a6a8a" : statusColors[status],
            boxShadow: !isRunning ? "none" : `0 0 6px ${statusColors[status]}`,
          }}
        />
      </div>

      {/* Видео / заглушка */}
      {!isRunning ? (
        <div style={styles.stoppedOverlay}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" opacity="0.3">
            <rect x="6" y="6" width="12" height="12" rx="2" stroke="#4a6a8a" strokeWidth="1.5" />
            <path d="M9 9l6 6M15 9l-6 6" stroke="#4a6a8a" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <div style={styles.stoppedText}>СИСТЕМА ОСТАНОВЛЕНА</div>
        </div>
      ) : (
        <>
          <img
            key={name + String(isRunning)}
            src={frameSrc}
            alt={name}
            style={styles.img}
            onLoad={() => {
              setHasFrame(true)
              setStreamError(false)
            }}
            onError={() => {
              if (!streamError) {
                setStreamError(true) // переключаемся на polling
              }
              if (!hasFrame) {
                // Первый кадр ещё не пришёл — оставляем спиннер
              }
            }}
          />

          {!hasFrame && (
            <div style={styles.spinner}>
              <div style={styles.spinnerRing} />
              <div style={styles.spinnerText}>CONNECTING...</div>
            </div>
          )}
        </>
      )}

      {/* Нижняя панель */}
      <div style={styles.bottomBar}>
        {!detectEnabled && <div style={styles.detectOff}>DETECT OFF</div>}
        {eventCount > 0 && (
          <div style={{ ...styles.badge, ...(hasViolation ? styles.badgeViolation : styles.badgeInfo) }}>
            {hasViolation ? "⚠" : "●"} {eventCount}
          </div>
        )}
        {detectEnabled && isRunning && status === "online" && <div style={styles.liveTag}>LIVE</div>}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    position: "relative",
    overflow: "hidden",
    background: "#050a10",
    cursor: "pointer",
    minHeight: 0,
    outline: "1px solid #1a3a5c",
    outlineOffset: "-1px",
    transition: "outline-color 0.3s, box-shadow 0.3s",
    display: "flex",
    flexDirection: "column",
  },
  cardFullscreen: {
    outlineWidth: "2px",
    boxShadow: "inset 0 0 40px rgba(0, 229, 255, 0.06)",
  },
  topBar: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 3,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "5px 8px",
    background: "linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 70%, transparent 100%)",
    pointerEvents: "none",
  },
  camName: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.6rem",
    color: "#c8dff0",
    letterSpacing: "1px",
    textShadow: "0 1px 4px rgba(0,0,0,0.8)",
  },
  statusDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    flexShrink: 0,
  },
  img: {
    width: "100%",
    flex: 1,
    objectFit: "contain",
    display: "block",
    background: "#000",
    minHeight: 0,
  },
  stoppedOverlay: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "10px",
    background: "#080d14",
    minHeight: 0,
  },
  stoppedText: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
    color: "#4a6a8a",
    letterSpacing: "2px",
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
    width: "32px",
    height: "32px",
    border: "2px solid #1a3a5c",
    borderTopColor: "#00e5ff",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  spinnerText: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.55rem",
    color: "#4a6a8a",
    letterSpacing: "1px",
  },
  bottomBar: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    zIndex: 3,
    display: "flex",
    alignItems: "center",
    gap: "4px",
    padding: "4px 6px",
    background: "linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 70%, transparent 100%)",
    pointerEvents: "none",
  },
  detectOff: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.55rem",
    color: "#ff5566",
    letterSpacing: "1px",
    background: "rgba(42,26,26,0.8)",
    border: "1px solid #ff5566",
    borderRadius: "2px",
    padding: "1px 5px",
  },
  badge: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.55rem",
    letterSpacing: "0.5px",
    borderRadius: "3px",
    padding: "1px 6px",
    marginLeft: "auto",
  },
  badgeInfo: {
    color: "#00e5ff",
    background: "rgba(0,229,255,0.15)",
    border: "1px solid rgba(0,229,255,0.3)",
  },
  badgeViolation: {
    color: "#ff3355",
    background: "rgba(255,51,85,0.15)",
    border: "1px solid rgba(255,51,85,0.3)",
    animation: "blink 1.2s ease-in-out infinite",
  },
  liveTag: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.5rem",
    color: "#00ff88",
    letterSpacing: "1px",
    background: "rgba(0,255,136,0.12)",
    border: "1px solid rgba(0,255,136,0.3)",
    borderRadius: "2px",
    padding: "1px 4px",
  },
}
