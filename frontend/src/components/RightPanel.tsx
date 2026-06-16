import { useState, useEffect, useRef } from "react"
import type { LogEntry } from "../types"

interface RightPanelProps {
  logs: LogEntry[]
}

const LOG_ICONS: Record<string, string> = {
  норма: "⛑️",
  внимание: "⚠️",
  нарушение: "🚨",
  normal: "⛑️",
  violation: "🚨",
}

export function RightPanel({ logs }: RightPanelProps) {
  const [cpu, setCpu] = useState(0)
  const [ram, setRam] = useState(0)
  const [fps, setFps] = useState(0)
  const logBoxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const update = () => {
      setCpu(30 + Math.random() * 40)
      setRam(50 + Math.random() * 20)
      setFps(20 + Math.random() * 10)
    }
    update()
    const id = setInterval(update, 2000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = 0
    }
  }, [logs])

  const handleClear = () => {
    if (logBoxRef.current) {
      logBoxRef.current.innerHTML = ""
    }
  }

  const handleExport = () => {
    const text = logs
      .map((l) => `[${l.timestamp}] [${l.category.toUpperCase()}] ${l.cam_id ? l.cam_id.toUpperCase() + " " : ""}${l.message}`)
      .join("\n")
    const blob = new Blob([text], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "events.txt"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={styles.rightPanel}>
      <div style={styles.eventsTitle}>
        События
        <span style={styles.eventsCount}>{logs.length} записей</span>
      </div>

      <div style={styles.logBox} ref={logBoxRef}>
        {logs.length === 0 ? (
          <div style={styles.emptyState}>Ожидание событий...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} style={styles.logItem}>
              <div
                style={{
                  ...styles.logIcon,
                  background:
                    log.category === "нарушение" || log.category === "violation"
                      ? "#f4433615"
                      : log.category === "внимание"
                        ? "#ff980015"
                        : "#00e67615",
                }}
              >
                {LOG_ICONS[log.category] || "📋"}
              </div>
              <div style={styles.logBody}>
                <div style={styles.logTime}>
                  {log.timestamp}
                  {log.cam_id ? ` · ${log.cam_id.toUpperCase()}` : ""}
                </div>
                <div style={styles.logMsg}>{log.message}</div>
              </div>
            </div>
          ))
        )}
      </div>

      <div style={styles.logActions}>
        <button style={styles.btnSm} onClick={handleClear}>
          Очистить
        </button>
        <button style={styles.btnSm} onClick={handleExport}>
          Экспорт
        </button>
      </div>

      <div style={styles.infoCard}>
        <div style={styles.infoCardTitle}>СИСТЕМА</div>
        <div style={styles.metricRow}>
          <div style={styles.metricName}>CPU</div>
          <div style={styles.metricBarWrap}>
            <div
              style={{
                ...styles.metricBar,
                width: `${Math.min(cpu, 100)}%`,
              }}
            />
          </div>
          <div style={styles.metricVal}>{Math.round(cpu)}%</div>
        </div>
        <div style={styles.metricRow}>
          <div style={styles.metricName}>RAM</div>
          <div style={styles.metricBarWrap}>
            <div
              style={{
                ...styles.metricBar,
                width: `${Math.min(ram, 100)}%`,
                background: "#00b0ff",
              }}
            />
          </div>
          <div style={styles.metricVal}>{Math.round(ram)}%</div>
        </div>
        <div style={styles.metricRow}>
          <div style={styles.metricName}>FPS</div>
          <div style={styles.metricBarWrap}>
            <div
              style={{
                ...styles.metricBar,
                width: `${Math.min((fps / 30) * 100, 100)}%`,
                background: "#ffd600",
              }}
            />
          </div>
          <div style={styles.metricVal}>{Math.round(fps)}</div>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  rightPanel: {
    background: "#1a1a1a",
    borderLeft: "1px solid #333",
    display: "flex",
    flexDirection: "column",
    padding: "16px",
    overflow: "hidden",
  },
  eventsTitle: {
    fontSize: "0.85rem",
    fontWeight: 600,
    color: "#ffffff",
    marginBottom: "12px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  eventsCount: {
    fontSize: "0.72rem",
    color: "#888",
  },
  logBox: {
    flex: 1,
    overflowY: "auto",
    scrollbarWidth: "thin" as const,
    scrollbarColor: "#333 transparent",
  },
  logItem: {
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
    padding: "10px 0",
    borderBottom: "1px solid #333",
    animation: "fadeIn .25s ease",
  },
  logIcon: {
    width: "36px",
    height: "36px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "1rem",
    flexShrink: 0,
    marginTop: "2px",
  },
  logBody: {
    flex: 1,
    minWidth: 0,
  },
  logTime: {
    fontSize: "0.68rem",
    color: "#888",
    marginBottom: "2px",
  },
  logMsg: {
    fontSize: "0.78rem",
    color: "#ccc",
    lineHeight: "1.4",
    wordBreak: "break-word" as const,
  },
  emptyState: {
    textAlign: "center",
    padding: "40px 10px",
    color: "#888",
    fontSize: "0.8rem",
  },
  logActions: {
    display: "flex",
    gap: "8px",
    marginTop: "10px",
    flexShrink: 0,
  },
  btnSm: {
    flex: 1,
    padding: "7px",
    borderRadius: "6px",
    background: "#2a2a2a",
    border: "1px solid #333",
    color: "#888",
    fontSize: "0.75rem",
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    transition: "all .2s",
  },
  infoCard: {
    background: "#222",
    borderRadius: "12px",
    padding: "14px",
    marginTop: "12px",
    flexShrink: 0,
  },
  infoCardTitle: {
    fontSize: "0.75rem",
    color: "#888",
    marginBottom: "8px",
  },
  metricRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "8px",
  },
  metricName: {
    fontSize: "0.72rem",
    color: "#888",
    width: "35px",
  },
  metricBarWrap: {
    flex: 1,
    height: "4px",
    background: "#333",
    borderRadius: "2px",
    overflow: "hidden",
  },
  metricBar: {
    height: "100%",
    borderRadius: "2px",
    background: "#00e676",
    transition: "width .8s",
  },
  metricVal: {
    fontSize: "0.72rem",
    color: "#ffffff",
    width: "30px",
    textAlign: "right" as const,
    fontFamily: "monospace",
  },
}
