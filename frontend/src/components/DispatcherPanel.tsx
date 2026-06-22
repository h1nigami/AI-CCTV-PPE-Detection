import { useMemo } from "react"
import { useCamerasContext } from "../contexts/CameraContext"
import type { PpeStatus, PersonSummary } from "../types"
import { parsePpeFromMessage, parsePersonsFromMessage } from "../utils/ppeParse"

export function DispatcherPanel() {
  const { dispatcher, closeDispatcher, cameras, logs: allLogs, detectModes, ppeRequired } = useCamerasContext()
  const { cameraName } = dispatcher

  const camera = useMemo(
    () => cameras.find((c) => c.name === cameraName) || null,
    [cameras, cameraName],
  )

  // Единый источник логов — из контекста (поллинг там), фильтруем по камере.
  const logs = useMemo(
    () => (cameraName ? allLogs.filter((l) => l.cam_id === cameraName) : []),
    [allLogs, cameraName],
  )

  const { ppe, persons } = useMemo((): { ppe: PpeStatus; persons: PersonSummary[] } => {
    const message = logs[0]?.message
    return {
      ppe: parsePpeFromMessage(message),
      persons: parsePersonsFromMessage(message),
    }
  }, [logs])

  if (!dispatcher.open || !cameraName) return null

  return (
    <div style={styles.panel}>
      <style>{`@keyframes ppeFadeIn{from{opacity:0;transform:translateY(-8px) scale(0.97)}to{opacity:1;transform:translateY(0) scale(1)}}`}</style>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={styles.camIcon}>
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <rect x="2" y="6" width="24" height="16" rx="3" stroke="#00e676" strokeWidth="1.5" />
              <circle cx="14" cy="14" r="5" stroke="#00e676" strokeWidth="1.5" />
              <path d="M22 6l4-3v18l-4-3" stroke="#00e676" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div style={styles.camTitle}>{cameraName.toUpperCase()}</div>
            <div style={styles.camSource}>{String(camera?.source || "")}</div>
          </div>
        </div>
        <button style={styles.closeBtn} onClick={closeDispatcher} title="Закрыть">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M4 4l10 10M14 4l-10 10" stroke="#888" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>СТАТУС СИЗ</div>
        <div style={styles.ppeGrid}>
          {(() => {
            const allItems = [
              { key: "helmet" as const, icon: "⛑", label: "Каска", mode: "ppe" },
              { key: "mask" as const, icon: "😷", label: "Маска", mode: "ppe" },
              { key: "vest" as const, icon: "🦺", label: "Жилет", mode: "ppe" },
              { key: "zone" as const, icon: "⚠", label: "Зона", mode: null },
              { key: "gesture" as const, icon: "👌", label: "Жест", mode: "faces" },
            ]
            // Видимость строки: (1) режим детекции включён; (2) для СИЗ
            // (helmet/mask/vest) — средство требуется в настройках (ppeRequired).
            // «Зона»/«Жест» (mode null/faces) фильтром СИЗ не затрагиваются.
            const ppeKeys = ["helmet", "mask", "vest"]
            const visible = allItems.filter((i) => {
              if (detectModes && i.mode && detectModes[i.mode] === false) return false
              if (ppeKeys.includes(i.key) && ppeRequired !== null && !ppeRequired.includes(i.key))
                return false
              return true
            })
            return visible.map(({ key, icon, label }) => {
              const val = ppe[key]
              const ok = val === true
              const color = val === null ? "#888" : ok ? "#00e676" : "#f44336"
              return (
                <div
                  key={key}
                  style={{
                    ...styles.ppeItem,
                    borderColor: color + "44",
                    animation: "ppeFadeIn 0.35s cubic-bezier(0.4, 0, 0.2, 1) both",
                  }}
                >
                  <div style={styles.ppeIcon}>{icon}</div>
                  <div style={styles.ppeLabel}>{label}</div>
                  <div style={{ ...styles.ppeValue, color }}>
                    {val === null ? "—" : ok ? "OK" : "!"}
                  </div>
                </div>
              )
            })
          })()}
        </div>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>
          ЛЮДИ
          <span style={styles.sectionCount}>{persons.length}</span>
        </div>
        {persons.length === 0 ? (
          <div style={styles.empty}>Нет данных</div>
        ) : (
          <div style={styles.personList}>
            {persons.map((p, i) => (
              <div key={i} style={styles.personRow}>
                <div style={styles.personName}>{p.name}</div>
                <div style={styles.personPpe}>{p.ppe}</div>
                <div style={{ color: p.approved ? "#00e676" : p.violation ? "#f44336" : "#ffd600" }}>
                  {p.approved ? "✓" : p.violation ? "✗" : "?"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>
          СОБЫТИЯ
          <span style={styles.sectionCount}>{logs.length}</span>
        </div>
        <div style={styles.eventList}>
          {logs.length === 0 && (
            <div style={styles.empty}>Ожидание событий</div>
          )}
          {logs
              .slice(-20)
              .reverse()
              .map((log) => {
                const isViolation = log.category === "нарушение" || log.category === "violation"
                const isWarning = log.category === "внимание"
                return (
                  <div
                    key={log.id}
                    style={{
                      ...styles.eventRow,
                      borderLeftColor: isViolation ? "#f44336" : isWarning ? "#ffd600" : "#00e676",
                    }}
                  >
                    <div style={styles.eventTime}>{log.timestamp}</div>
                    <div style={styles.eventMsg}>{log.message}</div>
                  </div>
                )
              })}
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    width: "420px",
    background: "#222",
    border: "1px solid #333",
    borderRadius: "12px",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 16px 64px rgba(0,0,0,0.6)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid #333",
    flexShrink: 0,
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    minWidth: 0,
  },
  camIcon: {
    flexShrink: 0,
  },
  camTitle: {
    fontWeight: 700,
    fontSize: "0.85rem",
    color: "#ffffff",
    letterSpacing: "1px",
    lineHeight: "1.2",
    fontFamily: "'Inter', sans-serif",
  },
  camSource: {
    fontFamily: "monospace",
    fontSize: "0.55rem",
    color: "#888",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "200px",
  },
  closeBtn: {
    background: "none",
    border: "1px solid #333",
    borderRadius: "6px",
    padding: "4px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#888",
    flexShrink: 0,
    transition: "all 0.2s",
  },
  section: {
    borderBottom: "1px solid #333",
    padding: "12px 16px",
    flexShrink: 0,
  },
  sectionTitle: {
    fontWeight: 700,
    fontSize: "0.6rem",
    letterSpacing: "3px",
    color: "#888",
    textTransform: "uppercase",
    marginBottom: "10px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontFamily: "'Inter', sans-serif",
  },
  sectionCount: {
    fontFamily: "monospace",
    fontSize: "0.6rem",
    color: "#333",
    background: "#1a1a1a",
    border: "1px solid #333",
    borderRadius: "4px",
    padding: "0 5px",
    lineHeight: "16px",
  },
  ppeGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "6px",
  },
  ppeItem: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 10px",
    background: "#2a2a2a",
    border: "1px solid #333",
    borderRadius: "8px",
    transition: "border-color 0.3s",
  },
  ppeIcon: {
    fontSize: "1rem",
    flexShrink: 0,
  },
  ppeLabel: {
    fontWeight: 600,
    fontSize: "0.75rem",
    color: "#ffffff",
    flex: 1,
    fontFamily: "'Inter', sans-serif",
  },
  ppeValue: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    fontWeight: 700,
  },
  personList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  personRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "6px 8px",
    background: "#2a2a2a",
    borderRadius: "6px",
    fontFamily: "monospace",
    fontSize: "0.65rem",
  },
  personName: {
    color: "#ffffff",
    minWidth: "80px",
  },
  personPpe: {
    color: "#888",
    flex: 1,
  },
  eventList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    maxHeight: "200px",
    overflowY: "auto",
  },
  eventRow: {
    padding: "6px 8px",
    background: "#2a2a2a",
    borderLeft: "2px solid",
    borderRadius: "4px",
  },
  eventTime: {
    fontFamily: "monospace",
    fontSize: "0.55rem",
    color: "#888",
    marginBottom: "2px",
  },
  eventMsg: {
    fontSize: "0.7rem",
    color: "#ccc",
    lineHeight: "1.3",
  },
  empty: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#888",
    textAlign: "center",
    padding: "12px",
  },
}
