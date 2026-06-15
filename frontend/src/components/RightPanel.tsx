import type { LogEntry } from "../types"

interface RightPanelProps {
  logs: LogEntry[]
}

export function RightPanel({ logs }: RightPanelProps) {
  const categoryClass = (cat: string) => {
    if (cat === "нарушение" || cat === "violation") return styles.logViolation
    if (cat === "внимание") return styles.logWarning
    return styles.logNormal
  }

  return (
    <div style={styles.rightPanel}>
      <div style={styles.eventsHeader}>
        <div style={styles.sectionLabel}>События</div>
        <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: ".65rem", color: "#4a6a8a" }}>
          {logs.length} записей
        </span>
      </div>

      <div style={styles.logBox}>
        {logs.length === 0 ? (
          <div style={styles.emptyState}>Ожидание событий...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} style={{ ...styles.logEntry, ...categoryClass(log.category) }}>
              <span style={styles.logTime}>
                {log.timestamp}
                {log.cam_id ? ` · ${log.cam_id.toUpperCase()}` : ""}
              </span>
              <span style={styles.logMsg}>{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  rightPanel: {
    background: "#0d1520",
    borderLeft: "1px solid #1a3a5c",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  eventsHeader: {
    padding: "14px 16px 10px",
    borderBottom: "1px solid #1a3a5c",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sectionLabel: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.65rem",
    letterSpacing: "3px",
    color: "#4a6a8a",
    textTransform: "uppercase",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  logBox: {
    flex: 1,
    overflowY: "auto",
    padding: "8px",
  },
  logEntry: {
    padding: "9px 10px",
    marginBottom: "6px",
    borderRadius: "5px",
    borderLeft: "3px solid",
    background: "#111c2b",
  },
  logNormal: {
    borderColor: "#00ff88",
    background: "#00ff8810",
  },
  logWarning: {
    borderColor: "#ffd600",
    background: "#ffd60010",
  },
  logViolation: {
    borderColor: "#ff3355",
    background: "#ff335510",
  },
  logTime: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.68rem",
    color: "#4a6a8a",
    display: "block",
    marginBottom: "3px",
  },
  logMsg: {
    fontSize: "0.78rem",
    lineHeight: "1.4",
    color: "#c8dff0",
  },
  emptyState: {
    textAlign: "center",
    padding: "40px 20px",
    color: "#4a6a8a",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.75rem",
    letterSpacing: "1px",
  },
}
