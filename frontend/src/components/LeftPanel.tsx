import { useMemo, useRef, useEffect } from "react"
import type { LogEntry, PpeStatus, PersonSummary } from "../types"
import { api } from "../api/client"

interface LeftPanelProps {
  isRunning: boolean
  selectedCam: string | null
  logs: LogEntry[]
  lastLogIdsRef: React.MutableRefObject<Record<string, string>>
  addNotification: (type: string, title: string, sub?: string, duration?: number) => void
  onStart: () => void
  onStop: () => void
  onShowGallery: () => void
  onShowCameraManager: () => void
}

export function LeftPanel({
  isRunning,
  selectedCam,
  logs,
  lastLogIdsRef,
  addNotification,
  onStart,
  onStop,
  onShowGallery,
  onShowCameraManager,
}: LeftPanelProps) {
  const prevLogIdsRef = useRef<Record<string, string>>({})

  const { ppe, counters, persons } = useMemo(() => {
    const result: {
      ppe: PpeStatus
      counters: { total: number; approved: number; violations: number; logCount: number }
      persons: PersonSummary[]
    } = {
      ppe: { helmet: null, mask: null, vest: null, zone: null, gesture: null },
      counters: { total: 0, approved: 0, violations: 0, logCount: logs.length },
      persons: [],
    }

    if (logs.length === 0) return result

    const latestByCam: Record<string, LogEntry> = {}
    logs.forEach((l) => {
      if (!latestByCam[l.cam_id]) latestByCam[l.cam_id] = l
    })

    const src = selectedCam ? latestByCam[selectedCam] : Object.values(latestByCam)[0]

    if (src?.message) {
      const m = src.message
      if (!m.includes("Людей:")) {
        result.ppe = { helmet: null, mask: null, vest: null, zone: null, gesture: null }
      } else {
        const personParts = m.split(" | ").filter((p) => /^[^[]+?\[.*?\]:/.test(p))
        let helmetOk = true, maskOk = true, vestOk = true
        let inDanger = false
        let hasPass = false
        for (const part of personParts) {
          const ppeMatch = part.match(/\[(.*?)\]/)
          if (ppeMatch) {
            const ppe = ppeMatch[1]
            if (ppe.includes("!К")) helmetOk = false
            if (ppe.includes("!М")) maskOk = false
            if (ppe.includes("!Ж")) vestOk = false
          }
          if (part.includes("ОПАСНАЯ ЗОНА")) inDanger = true
          if (part.includes("ПРОПУСК")) hasPass = true
        }
        result.ppe = {
          helmet: helmetOk,
          mask: maskOk,
          vest: vestOk,
          zone: !inDanger,
          gesture: hasPass,
        }
      }
    }

    Object.entries(latestByCam).forEach(([camId, log]) => {
      const parts = (log.message || "").split(" | ")
      const people = parts.filter((p) => /^[^[]+?\[.*?\]:/.test(p)).length
      result.counters.total += people
      const a = (log.message || "").match(/ПРОПУСК/g)
      if (a) result.counters.approved += a.length

      const personParts = parts.filter((p) => /^[^[]+?\[.*?\]:/.test(p))
      personParts.forEach((part, idx) => {
        const ppeMatch = part.match(/\[(.*?)\]/)
        const ppeStr = ppeMatch ? ppeMatch[1] + " " : ""
        const nameMatch = part.match(/^([^[]+?)\s*\[/)
        const name = nameMatch ? nameMatch[1].trim() : `Чел.${idx + 1}`

        result.persons.push({
          name,
          ppe: ppeStr,
          approved: part.includes("ПРОПУСК"),
          danger: part.includes("ОПАСНАЯ"),
          violation: ppeStr.includes("!К") || ppeStr.includes("!М") || ppeStr.includes("!Ж"),
          index: idx,
        })
      })
    })

    result.counters.violations = logs.filter(
      (l) => l.category === "нарушение" || l.category === "violation",
    ).length

    return result
  }, [logs, selectedCam])

  // Notifications for new OK gestures
  useEffect(() => {
    if (logs.length === 0) return
    const latestByCam: Record<string, LogEntry> = {}
    logs.forEach((l) => {
      if (!latestByCam[l.cam_id]) latestByCam[l.cam_id] = l
    })

    Object.values(latestByCam).forEach((log) => {
      const camId = log.cam_id
      if (log.id === prevLogIdsRef.current[camId]) return
      prevLogIdsRef.current[camId] = log.id

      const m = log.message
      if (!m.includes("ЖЕСТ-ОК")) return

      const hasPass = m.includes("ПРОПУСК")
      const parts = m.split(" | ")
      let pName = "Работник"
      for (const part of parts) {
        const match = part.match(/^([^[]+?)\s*(?:\[.*?\])?\s*:\s*(ПРОПУСК|ОПАСНАЯ ЗОНА|Вне зоны|ЖЕСТ-ОК)/)
        if (match) {
          pName = match[1].trim()
          break
        }
      }

      if (hasPass) {
        addNotification("granted", "✅ ЖЕСТ «ОК» РАСПОЗНАН", `${pName} — доступ разрешён!`, 5000)
      } else {
        const missing: string[] = []
        if (!m.includes("К ") || m.includes("!К")) missing.push("Каска")
        if (!m.includes("М ") || m.includes("!М")) missing.push("Маска")
        if (!m.includes("Ж") || m.includes("!Ж")) missing.push("Жилет")
        addNotification("missing", "⚠️ НЕ ХВАТАЕТ СИЗ", `${pName}: ${missing.join(" · ")}`, 4000)
      }
    })
  }, [logs, addNotification])

  const personColor = (p: PersonSummary): string => {
    if (p.approved) return "#00ff88"
    if (p.danger && p.violation) return "#ff3355"
    if (p.danger) return "#ff6d00"
    if (p.violation) return "#ffd600"
    return "#00e5ff"
  }

  return (
    <div style={styles.leftPanel}>
      {/* Controls */}
      <div style={styles.panelSection}>
        <div style={styles.sectionLabel}>Управление</div>
        <button style={styles.btnStart} onClick={onStart} disabled={isRunning}>
          ▶ Запустить
        </button>
        <button style={styles.btnStop} onClick={onStop} disabled={!isRunning}>
          ■ Остановить
        </button>
        <div style={{ ...styles.statusPill, ...(isRunning ? styles.statusActive : styles.statusInactive) }}>
          <div style={styles.pillDot} />
          <span>{isRunning ? "Детекция активна" : "Система готова"}</span>
        </div>
        <button style={styles.galleryBtn} onClick={onShowGallery}>
          👤 Управление лицами
        </button>
        <button style={{ ...styles.galleryBtn, marginTop: 4 }} onClick={onShowCameraManager}>
          📷 Управление камерами
        </button>
      </div>

      {/* PPE Status */}
      <div style={styles.panelSection}>
        <div style={styles.sectionLabel}>Статус проверки</div>
        {(["helmet", "mask", "vest", "zone", "gesture"] as const).map((key) => {
          const labels: Record<string, { icon: string; name: string }> = {
            helmet: { icon: "⛑️", name: "Каска" },
            mask: { icon: "😷", name: "Маска" },
            vest: { icon: "🦺", name: "Жилет" },
            zone: { icon: "⚠️", name: "Опасная зона" },
            gesture: { icon: "👌", name: "Жест «ОК»" },
          }
          const subs: Record<string, string> = {
            helmet: ppe.helmet === null ? "ожидание" : ppe.helmet ? "обнаружена" : "не обнаружена",
            mask: ppe.mask === null ? "ожидание" : ppe.mask ? "обнаружена" : "не обнаружена",
            vest: ppe.vest === null ? "ожидание" : ppe.vest ? "обнаружен" : "не обнаружен",
            zone: ppe.zone === null ? "ожидание" : ppe.zone ? "не пересечена" : "пересечена",
            gesture: ppe.gesture === null ? "ожидание" : ppe.gesture ? "распознан" : "ожидание",
          }
          const val = ppe[key]
          const ok = val === true
          const borderColor = val === null ? "#1a3a5c" : ok ? "#00ff8844" : "#ff335544"
          const icon = val === null ? "—" : ok ? "✅" : "❌"

          return (
            <div key={key} style={{ ...styles.ppeItem, borderColor }}>
              <div style={styles.ppeLeft}>
                <div style={{ fontSize: "1.3rem" }}>{labels[key].icon}</div>
                <div>
                  <div style={styles.ppeName}>{labels[key].name}</div>
                  <div style={styles.ppeSub}>{subs[key]}</div>
                </div>
              </div>
              <div style={{ fontSize: "1.1rem" }}>{icon}</div>
            </div>
          )
        })}
      </div>

      {/* Counters */}
      <div style={styles.panelSection}>
        <div style={styles.sectionLabel}>Счётчик людей</div>
        <div style={styles.counterGrid}>
          <div style={styles.counterItem}>
            <div style={styles.counterNum}>{counters.total}</div>
            <div style={styles.counterLabel}>Всего</div>
          </div>
          <div style={styles.counterItem}>
            <div style={{ ...styles.counterNum, color: "#00ff88" }}>{counters.approved}</div>
            <div style={styles.counterLabel}>Допущено</div>
          </div>
        </div>

        <div style={styles.peopleIcons}>
          {persons.length === 0 ? (
            <span style={{ color: "#4a6a8a", fontFamily: "'Share Tech Mono', monospace", fontSize: ".7rem" }}>
              нет людей
            </span>
          ) : (
            persons.map((p, i) => (
              <div key={i} style={styles.personIcon} title={`${p.name}: ${p.approved ? "Допущен" : p.danger && p.violation ? "Зона + нарушение" : p.danger ? "В опасной зоне" : p.violation ? "Нет СИЗ" : "OK"}`}>
                <svg width="26" height="26" viewBox="0 0 28 28" fill="none">
                  <circle cx="14" cy="9" r="5" fill={personColor(p)} opacity=".9" />
                  <path d="M4 24c0-5.5 4.5-9 10-9s10 3.5 10 9" stroke={personColor(p)} strokeWidth="2" strokeLinecap="round" fill="none" opacity=".9" />
                </svg>
                <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: ".6rem", color: personColor(p) }}>{i + 1}</span>
              </div>
            ))
          )}
        </div>

        <div style={{ ...styles.counterGrid, marginTop: 8, marginBottom: 0 }}>
          <div style={styles.counterItem}>
            <div style={{ ...styles.counterNum, color: "#ff3355" }}>{counters.violations}</div>
            <div style={styles.counterLabel}>Нарушений</div>
          </div>
          <div style={styles.counterItem}>
            <div style={styles.counterNum}>{counters.logCount}</div>
            <div style={{ ...styles.counterLabel }}>Записей</div>
          </div>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  leftPanel: {
    background: "#0d1520",
    borderRight: "1px solid #1a3a5c",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
  },
  panelSection: {
    borderBottom: "1px solid #1a3a5c",
    padding: "16px",
  },
  sectionLabel: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.65rem",
    letterSpacing: "3px",
    color: "#4a6a8a",
    textTransform: "uppercase",
    marginBottom: "12px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  btnStart: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.85rem",
    letterSpacing: "1px",
    border: "1px solid #00e5ff",
    borderRadius: "5px",
    padding: "9px 16px",
    cursor: "pointer",
    textTransform: "uppercase",
    width: "100%",
    marginBottom: "8px",
    background: "#00e5ff22",
    color: "#00e5ff",
    transition: "all .2s",
  },
  btnStop: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.85rem",
    letterSpacing: "1px",
    border: "1px solid #ff3355",
    borderRadius: "5px",
    padding: "9px 16px",
    cursor: "pointer",
    textTransform: "uppercase",
    width: "100%",
    marginBottom: "8px",
    background: "#ff335522",
    color: "#ff3355",
    transition: "all .2s",
  },
  statusPill: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    padding: "6px 12px",
    borderRadius: "4px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.72rem",
    letterSpacing: "1px",
    marginTop: "8px",
    border: "1px solid #1a3a5c",
    color: "#4a6a8a",
    transition: "all .3s",
  },
  statusActive: {
    borderColor: "#00ff88",
    color: "#00ff88",
    background: "#00ff8811",
  },
  statusInactive: {
    borderColor: "#ff3355",
    color: "#ff3355",
    background: "#ff335511",
  },
  pillDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "currentColor",
  },
  galleryBtn: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.75rem",
    letterSpacing: "1px",
    background: "transparent",
    border: "1px solid #1a3a5c",
    color: "#4a6a8a",
    borderRadius: "4px",
    padding: "6px 12px",
    cursor: "pointer",
    textTransform: "uppercase",
    width: "100%",
    transition: "all .2s",
  },
  ppeItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px",
    marginBottom: "8px",
    background: "#111c2b",
    border: "1px solid #1a3a5c",
    borderRadius: "6px",
    transition: "border-color .3s",
  },
  ppeLeft: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  ppeName: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.9rem",
    lineHeight: "1",
  },
  ppeSub: {
    fontSize: "0.7rem",
    color: "#4a6a8a",
    fontFamily: "'Share Tech Mono', monospace",
    marginTop: "2px",
  },
  counterGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "8px",
    marginBottom: "10px",
  },
  counterItem: {
    background: "#111c2b",
    border: "1px solid #1a3a5c",
    borderRadius: "6px",
    padding: "12px 10px",
    textAlign: "center" as const,
  },
  counterNum: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "2rem",
    color: "#00e5ff",
    lineHeight: "1",
  },
  counterLabel: {
    fontSize: "0.65rem",
    letterSpacing: "1px",
    color: "#4a6a8a",
    textTransform: "uppercase",
    marginTop: "4px",
    fontFamily: "'Rajdhani', sans-serif",
  },
  peopleIcons: {
    padding: "10px",
    background: "#111c2b",
    border: "1px solid #1a3a5c",
    borderRadius: "6px",
    minHeight: "52px",
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    alignItems: "center",
  },
  personIcon: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "2px",
    cursor: "default",
  },
}
