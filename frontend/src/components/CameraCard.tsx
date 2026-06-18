import { useState, useEffect, useRef } from "react"
import { api } from "../api/client"
import type { CameraStatus } from "../types"

// ============================================================
// Карточка камеры — основной элемент сетки.
// Стрим реализован через load-driven HTTP-поллинг одиночных JPEG
// (/video_frame): следующий кадр запрашивается только ПОСЛЕ загрузки
// предыдущего, поэтому в полёте всегда одно короткое соединение.
// Это сознательный отказ от постоянного MJPEG (/video_feed): тот держал
// по соединению+потоку на камеру и при нескольких камерах забивал пулы
// браузера (~6 соединений) и Waitress (4 потока) → лаги и зависание /stop
// (POST не мог уйти, пока стримы держат соединения).
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
  isLandscape?: boolean
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
  isLandscape = false,
}: CameraCardProps) {
  // src — URL уже ЗАГРУЖЕННОГО кадра (меняется только после успешной
  // фоновой загрузки), поэтому в DOM-картинке нет «битых» кадров и мигания.
  const [src, setSrc] = useState("")
  const [hasFrame, setHasFrame] = useState(false)
  const [streamError, setStreamError] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const errCountRef = useRef(0)
  const mountedRef = useRef(true)

  // Очистка при размонтировании
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  // Цикл опроса: одно фоновое изображение грузится за раз, следующий кадр
  // запрашивается из onload/onerror предыдущего. Никаких setInterval —
  // запросы не наслаиваются даже при медленной сети/бэке.
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)

    if (!isRunning) {
      setHasFrame(false)
      setStreamError(false)
      errCountRef.current = 0
      return
    }

    errCountRef.current = 0
    const okDelay = detectEnabled ? 100 : 1000
    // Флаг этого прогона: гасит колбэки уже летящего кадра после стопа/смены
    // камеры, иначе его onload перезапустил бы цикл опроса.
    let cancelled = false

    const schedule = (delay: number) => {
      if (cancelled) return
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(loadNext, delay)
    }

    const loadNext = () => {
      if (cancelled || !mountedRef.current) return
      const img = new Image()
      img.onload = () => {
        if (cancelled || !mountedRef.current) return
        errCountRef.current = 0
        setSrc(img.src)
        setHasFrame(true)
        setStreamError(false)
        schedule(okDelay)
      }
      img.onerror = () => {
        if (cancelled || !mountedRef.current) return
        errCountRef.current += 1
        // Не пугаем пользователя на старте: «NO SIGNAL» только после серии ошибок.
        if (errCountRef.current >= 5) setStreamError(true)
        // Бэкофф: чем дольше нет кадров, тем реже долбим бэк (макс. 2с).
        schedule(Math.min(2000, 300 * errCountRef.current))
      }
      img.src = api.getFrameUrl(name)
    }

    loadNext()

    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [isRunning, name, detectEnabled])

  // Цвет рамки статуса
  const statusColors: Record<CameraStatus, string> = {
    online: "#00e676",
    offline: "#f44336",
    error: "#ff9800",
  }

  const frameSrc = src

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
          {hasFrame && (
            <img
              src={frameSrc}
              alt={name}
              style={{ ...styles.img, objectFit: isLandscape ? 'cover' : 'contain' }}
            />
          )}

          {(!hasFrame || streamError) && (
            <div style={styles.spinner}>
              <div style={styles.spinnerRing} />
              <div style={styles.spinnerText}>{streamError ? "NO SIGNAL" : "CONNECTING..."}</div>
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
    background: "#111",
    cursor: "pointer",
    minHeight: 0,
    outline: "1px solid #333",
    outlineOffset: "-1px",
    transition: "outline-color 0.3s, box-shadow 0.3s",
    display: "flex",
    flexDirection: "column",
  },
  cardFullscreen: {
    outlineWidth: "2px",
    outlineColor: "#00e676",
    boxShadow: "inset 0 0 40px rgba(0, 230, 118, 0.06)",
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
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.6rem",
    color: "#ccc",
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
    background: "#111",
    minHeight: 0,
  },
  stoppedText: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.7rem",
    color: "#888",
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
    background: "#111",
    gap: "8px",
    pointerEvents: "none",
  },
  spinnerRing: {
    width: "32px",
    height: "32px",
    border: "2px solid #333",
    borderTopColor: "#00e676",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  spinnerText: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.55rem",
    color: "#888",
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
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.55rem",
    color: "#f44336",
    letterSpacing: "1px",
    background: "rgba(42,26,26,0.8)",
    border: "1px solid #f44336",
    borderRadius: "2px",
    padding: "1px 5px",
  },
  badge: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.55rem",
    letterSpacing: "0.5px",
    borderRadius: "3px",
    padding: "1px 6px",
    marginLeft: "auto",
  },
  badgeInfo: {
    color: "#00b0ff",
    background: "rgba(0,176,255,0.15)",
    border: "1px solid rgba(0,176,255,0.3)",
  },
  badgeViolation: {
    color: "#f44336",
    background: "rgba(244,67,54,0.15)",
    border: "1px solid rgba(244,67,54,0.3)",
    animation: "blink 1.2s ease-in-out infinite",
  },
  liveTag: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.5rem",
    color: "#00e676",
    letterSpacing: "1px",
    background: "rgba(0,230,118,0.12)",
    border: "1px solid rgba(0,230,118,0.3)",
    borderRadius: "2px",
    padding: "1px 4px",
  },
}
