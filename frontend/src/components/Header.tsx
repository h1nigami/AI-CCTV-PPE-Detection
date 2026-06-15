import { useClock } from "../hooks/useClock"

interface HeaderProps {
  isRunning: boolean
}

export function Header({ isRunning }: HeaderProps) {
  const now = useClock()

  const timeStr = now.toLocaleTimeString("ru-RU")
  const dateStr = now.toLocaleDateString("ru-RU")

  return (
    <header style={styles.header}>
      <div style={styles.logo}>
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect x="2" y="2" width="24" height="24" rx="4" stroke="#00e5ff" strokeWidth="1.5" />
          <circle cx="14" cy="12" r="5" stroke="#00e5ff" strokeWidth="1.5" />
          <path d="M6 22c0-4 3.6-7 8-7s8 3 8 7" stroke="#00e5ff" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        KONTROLER AI
      </div>

      <div style={styles.headerTitle}>Видеоаналитика в реальном времени</div>

      <div style={styles.headerRight}>
        <div style={styles.liveBadge}>
          <div style={{ ...styles.liveDot, background: isRunning ? "#00ff88" : "#ff3355", boxShadow: isRunning ? "0 0 6px #00ff88" : "0 0 6px #ff3355" }} />
          <span style={{ color: isRunning ? "#00ff88" : "#ff3355" }}>{isRunning ? "LIVE" : "OFFLINE"}</span>
        </div>
        <div style={styles.clock}>
          <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "#00e5ff", letterSpacing: "1px" }}>{timeStr}</div>
          <div style={{ fontSize: "0.65rem", color: "#4a6a8a" }}>{dateStr}</div>
        </div>
      </div>
    </header>
  )
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 24px",
    background: "#0d1520",
    borderBottom: "1px solid #1a3a5c",
    flexShrink: 0,
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "1.15rem",
    letterSpacing: "2px",
    color: "#00e5ff",
  },
  headerTitle: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.95rem",
    letterSpacing: "3px",
    color: "#4a6a8a",
    textTransform: "uppercase" as const,
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "20px",
  },
  liveBadge: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.75rem",
    letterSpacing: "1px",
  },
  liveDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    animation: "blink 1.2s ease-in-out infinite",
  },
  clock: {
    textAlign: "right" as const,
    lineHeight: "1.4",
  },
}
