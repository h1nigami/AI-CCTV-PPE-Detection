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

        if (personParts.length === 0) {
          result.ppe = { helmet: null, mask: null, vest: null, zone: null, gesture: null }
        } else {
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
    }

    Object.entries(latestByCam).forEach(([camId, log]) => {
      const parts = (log.message || "").split(" | ")
      const peopleMatch = log.message.match(/Людей:\s*(\d+)/)
      const people = peopleMatch ? parseInt(peopleMatch[1]) : 0
      result.counters.total += people
      const a = (log.message || "").match(/ПРОПУСК/g)
      if (a) result.counters.approved += a.length

      const personParts = parts.filter((p) => {
        if (p.startsWith("Людей:") || p.startsWith("Нет СИЗ")) return false
        return /^[^\[\:]+(?:\[.*?\])?\s*:\s/.test(p)
      })
      personParts.forEach((part, idx) => {
        const ppeMatch = part.match(/\[(.*?)\]/)
        const ppeStr = ppeMatch ? ppeMatch[1] + " " : ""
        const nameMatch = part.match(/^([^[]+?)\s*\[/)
        const name = nameMatch ? nameMatch[1].trim() : part.split(":")[0].trim()

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
    if (p.approved) return "#00e676"
    if (p.danger && p.violation) return "#f44336"
    if (p.danger) return "#ff9800"
    if (p.violation) return "#ffd600"
    return "#00b0ff"
  }

  const ppeConfig: { key: keyof PpeStatus; icon: string; label: string }[] = [
    { key: "helmet", icon: "⛑️", label: "СИЗ Каска" },
    { key: "mask", icon: "😷", label: "СИЗ Маска" },
    { key: "vest", icon: "🦺", label: "СИЗ Жилет" },
    { key: "gesture", icon: "🤙", label: "Жест ОК" },
    { key: "zone", icon: "⚠️", label: "Опасная зона" },
  ]

  const ppeSubs: Record<string, (val: boolean | null) => string> = {
    helmet: (v) => v === null ? "Ожидание" : v ? "Обнаружена" : "Не обнаружена",
    mask: (v) => v === null ? "Ожидание" : v ? "Обнаружена" : "Не обнаружена",
    vest: (v) => v === null ? "Ожидание" : v ? "Обнаружен" : "Не обнаружен",
    gesture: (v) => v === null ? "Ожидание" : v ? "Распознан" : "Не обнаружен",
    zone: (v) => v === null ? "Ожидание" : v ? "Не пересечена" : "Пересечена",
  }

  return (
    <div style={styles.leftPanel}>
      {/* Controls */}
      <div style={styles.panelCard}>
        <div style={styles.cardTitle}>Управление</div>
        <button style={styles.btnStart} onClick={onStart} disabled={isRunning}>
          ▶ Запустить
        </button>
        <button style={styles.btnStop} onClick={onStop} disabled={!isRunning}>
          ■ Остановить
        </button>
        <div
          style={{
            ...styles.statusPill,
            ...(isRunning ? styles.statusActive : styles.statusInactive),
          }}
        >
          <div style={styles.pillDot} />
          <span>{isRunning ? "Детекция активна" : "Система готова"}</span>
        </div>
        <button style={styles.ctrlBtn} onClick={onShowGallery}>
          👤 Управление лицами
        </button>
        <button style={{ ...styles.ctrlBtn, marginTop: 4 }} onClick={onShowCameraManager}>
          📷 Управление камерами
        </button>
      </div>

      {/* PPE Status */}
      <div style={styles.panelCard}>
        <div style={styles.cardTitle}>Статус проверки</div>
        {ppeConfig.map(({ key, icon, label }) => {
          const val = ppe[key]
          const ok = val === true
          const fail = val === false
          const neutral = val === null

          let wrapClass = styles.ppeIconNeutral
          let checkClass = styles.ppeCheckNeutral
          let checkText = "—"

          if (ok) {
            wrapClass = styles.ppeIconOk
            checkClass = styles.ppeCheckOk
            checkText = "✓"
          } else if (fail) {
            wrapClass = styles.ppeIconFail
            checkClass = styles.ppeCheckFail
            checkText = "✕"
          }

          return (
            <div key={key} style={styles.ppeItem}>
              <div style={{ ...styles.ppeIconWrap, ...wrapClass }}>
                {icon}
              </div>
              <div style={styles.ppeInfo}>
                <div style={styles.ppeName}>{label}</div>
                <div style={styles.ppeSub}>{ppeSubs[key](val)}</div>
              </div>
              <div style={{ ...styles.ppeCheck, ...checkClass }}>
                {checkText}
              </div>
            </div>
          )
        })}
      </div>

      {/* Counter */}
      <div style={styles.panelCard}>
        <div style={styles.cardTitle}>Счётчик людей</div>
        <div style={styles.counterBig}>{counters.total}</div>
        <div style={styles.counterSub}>человек в кадре</div>

        <div style={styles.peopleRow}>
          {persons.length === 0 ? (
            <span style={{ fontSize: ".75rem", color: "#888" }}>нет людей</span>
          ) : (
            persons.map((p, i) => (
              <div
                key={i}
                style={styles.personIcon}
                title={`${p.name}: ${p.approved ? "Допущен" : p.danger && p.violation ? "Зона + нарушение" : p.danger ? "В опасной зоне" : p.violation ? "Нет СИЗ" : "OK"}`}
              >
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <circle cx="14" cy="9" r="5" fill={personColor(p)} opacity=".9" />
                  <path d="M4 24c0-5.5 4.5-9 10-9s10 3.5 10 9" stroke={personColor(p)} strokeWidth="2" strokeLinecap="round" fill="none" opacity=".9" />
                </svg>
                <span style={{ fontSize: ".6rem", color: personColor(p), fontFamily: "monospace" }}>{i + 1}</span>
              </div>
            ))
          )}
        </div>

        <div style={styles.counterRow}>
          <div style={styles.counterSmall}>
            <div style={styles.counterSmallNum}>{counters.approved}</div>
            <div style={styles.counterSmallLabel}>Допущено</div>
          </div>
          <div style={styles.counterSmall}>
            <div style={{ ...styles.counterSmallNum, color: "#f44336" }}>{counters.violations}</div>
            <div style={styles.counterSmallLabel}>Нарушений</div>
          </div>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  leftPanel: {
    background: "#1a1a1a",
    borderRight: "1px solid #333",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    padding: "16px",
    gap: 0,
  },
  panelCard: {
    background: "#222",
    borderRadius: "12px",
    padding: "16px",
    marginBottom: "12px",
  },
  cardTitle: {
    fontSize: "0.85rem",
    fontWeight: 600,
    color: "#ffffff",
    marginBottom: "14px",
  },
  btnStart: {
    width: "100%",
    padding: "11px",
    border: "1px solid #00e67650",
    borderRadius: "8px",
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.85rem",
    fontWeight: 600,
    cursor: "pointer",
    marginBottom: "8px",
    letterSpacing: "0.3px",
    background: "#00e67615",
    color: "#00e676",
    transition: "all .2s",
  },
  btnStop: {
    width: "100%",
    padding: "11px",
    border: "1px solid #f4433650",
    borderRadius: "8px",
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.85rem",
    fontWeight: 600,
    cursor: "pointer",
    marginBottom: "8px",
    letterSpacing: "0.3px",
    background: "#f4433615",
    color: "#f44336",
    transition: "all .2s",
  },
  statusPill: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    padding: "6px 10px",
    borderRadius: "6px",
    fontSize: "0.72rem",
    fontWeight: 500,
    border: "1px solid #333",
    color: "#888",
    transition: "all .3s",
    marginTop: "4px",
  },
  statusActive: {
    borderColor: "#00e67650",
    color: "#00e676",
    background: "#00e67610",
  },
  statusInactive: {
    borderColor: "#f4433650",
    color: "#f44336",
    background: "#f4433610",
  },
  pillDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "currentColor",
  },
  ctrlBtn: {
    width: "100%",
    padding: "7px",
    borderRadius: "8px",
    background: "transparent",
    border: "1px solid #333",
    color: "#888",
    fontSize: "0.75rem",
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    transition: "all .2s",
  },
  ppeItem: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "10px 0",
    borderBottom: "1px solid #333",
  },
  ppeIconWrap: {
    width: "42px",
    height: "42px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "1.3rem",
    flexShrink: 0,
  },
  ppeIconOk: {
    background: "#00e67620",
    border: "1px solid #00e67640",
  },
  ppeIconFail: {
    background: "#f4433620",
    border: "1px solid #f4433640",
  },
  ppeIconNeutral: {
    background: "#33333380",
    border: "1px solid #333",
  },
  ppeInfo: {
    flex: 1,
  },
  ppeName: {
    fontSize: "0.85rem",
    fontWeight: 500,
    color: "#ffffff",
  },
  ppeSub: {
    fontSize: "0.75rem",
    color: "#888",
    marginTop: "2px",
  },
  ppeCheck: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "0.9rem",
    flexShrink: 0,
  },
  ppeCheckOk: {
    background: "#00e67620",
    border: "2px solid #00e676",
    color: "#00e676",
  },
  ppeCheckFail: {
    background: "#f4433620",
    border: "2px solid #f44336",
    color: "#f44336",
  },
  ppeCheckNeutral: {
    background: "transparent",
    border: "2px solid #333",
    color: "#888",
  },
  counterBig: {
    fontSize: "4rem",
    fontWeight: 700,
    color: "#00e676",
    lineHeight: 1,
    margin: "8px 0 4px",
  },
  counterSub: {
    fontSize: "0.8rem",
    color: "#888",
  },
  peopleRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
    marginTop: "12px",
    minHeight: "40px",
  },
  personIcon: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "2px",
    cursor: "default",
  },
  counterRow: {
    display: "flex",
    gap: "10px",
    marginTop: "12px",
  },
  counterSmall: {
    flex: 1,
    background: "#2a2a2a",
    borderRadius: "8px",
    padding: "10px",
    textAlign: "center" as const,
  },
  counterSmallNum: {
    fontSize: "1.4rem",
    fontWeight: 700,
    color: "#ffffff",
  },
  counterSmallLabel: {
    fontSize: "0.65rem",
    color: "#888",
    marginTop: "2px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
  },
}
