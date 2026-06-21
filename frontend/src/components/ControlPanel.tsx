import { useMemo } from "react"
import type { LogEntry, PpeStatus, PersonSummary } from "../types"
import { useCamerasContext } from "../contexts/CameraContext"
import { parsePpeFromMessage, parsePersonsFromMessage, parsePeopleCount } from "../utils/ppeParse"

interface ControlPanelProps {
  variant?: "sidebar" | "sheet"
  isRunning: boolean
  selectedCam: string | null
  logs: LogEntry[]
  onStart: () => void
  onStop: () => void
  onShowGallery: () => void
  onShowCameraManager: () => void
}

export function ControlPanel({
  variant = "sidebar",
  isRunning,
  selectedCam,
  logs,
  onStart,
  onStop,
  onShowGallery,
  onShowCameraManager,
}: ControlPanelProps) {
  const isSidebar = variant === "sidebar"
  const { detectModes } = useCamerasContext()

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

    // Индикаторы «Статус проверки» — строго по выбранной/полноэкранной камере.
    // Пока камера не выбрана, статус неоднозначен (несколько камер) → «—»
    // (ожидание), а не данные случайной первой камеры.
    const src = selectedCam ? latestByCam[selectedCam] : undefined
    result.ppe = parsePpeFromMessage(src?.message)

    // Счётчики — по ТЕКУЩЕМУ кадру каждой камеры (последняя лог-строка), а не по
    // всему кольцевому буферу: «человек в кадре» и «нарушений» должны совпадать
    // с тем, что видно сейчас. Раньше «Нарушений» считалось по всему буферу логов.
    Object.values(latestByCam).forEach((log) => {
      result.counters.total += parsePeopleCount(log.message)
      const ps = parsePersonsFromMessage(log.message)
      ps.forEach((p) => {
        if (p.approved) result.counters.approved += 1
        if (p.violation) result.counters.violations += 1
      })
      result.persons.push(...ps)
    })

    return result
  }, [logs, selectedCam])

  // Уведомления о жесте ОК / нехватке СИЗ теперь приходят с сервера
  // (useServerNotifications в Dashboard, источник — /api/notifications),
  // а не парсятся из текста логов — это точнее и не зависит от дедупа логов.

  const personColor = (p: PersonSummary): string => {
    if (p.approved) return "#00e676"
    if (p.danger && p.violation) return "#f44336"
    if (p.danger) return "#ff9800"
    if (p.violation) return "#ffd600"
    return "#00b0ff"
  }

  // mode — режим детекции, к которому привязана строка (null = показывать всегда).
  // Отображаем только то, что реально запрошено детектить (как в DispatcherPanel):
  // при выключенном «СИЗ» скрываем каску/маску/жилет, при выключенных «Лицах» — жест.
  const ppeConfigAll: { key: keyof PpeStatus; icon: string; label: string; mode: string | null }[] = [
    { key: "helmet", icon: "⛑️", label: "СИЗ Каска", mode: "ppe" },
    { key: "mask", icon: "😷", label: "СИЗ Маска", mode: "ppe" },
    { key: "vest", icon: "🦺", label: "СИЗ Жилет", mode: "ppe" },
    { key: "gesture", icon: "👌", label: "Жест ОК", mode: "faces" },
    { key: "zone", icon: "⚠️", label: "Опасная зона", mode: null },
  ]
  const ppeConfig = detectModes
    ? ppeConfigAll.filter((i) => !i.mode || detectModes[i.mode] !== false)
    : ppeConfigAll

  const ppeSubs: Record<string, (val: boolean | null) => string> = {
    helmet: (v) => v === null ? "Ожидание" : v ? "Обнаружена" : "Не обнаружена",
    mask: (v) => v === null ? "Ожидание" : v ? "Обнаружена" : "Не обнаружена",
    vest: (v) => v === null ? "Ожидание" : v ? "Обнаружен" : "Не обнаружен",
    gesture: (v) => v === null ? "Ожидание" : v ? "Распознан" : "Не обнаружен",
    zone: (v) => v === null ? "Ожидание" : v ? "Не пересечена" : "Пересечена",
  }

  return (
    <div style={isSidebar ? styles.sidebar : styles.sheet}>
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
  sidebar: {
    background: "#1a1a1a",
    borderRight: "1px solid #333",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    padding: "16px",
    gap: 0,
  },
  sheet: {
    background: "#1a1a1a",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    padding: "12px",
    gap: 0,
  },
  panelCard: {
    background: "#222",
    borderRadius: "12px",
    padding: "16px",
    marginBottom: "12px",
  },
  cardTitle: {
    fontSize: "clamp(0.8rem, 2vw, 0.85rem)",
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
    fontSize: "clamp(0.8rem, 2vw, 0.85rem)",
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
    fontSize: "clamp(0.8rem, 2vw, 0.85rem)",
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
    fontSize: "clamp(0.65rem, 1.5vw, 0.72rem)",
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
    fontSize: "clamp(0.7rem, 1.8vw, 0.75rem)",
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
    fontSize: "clamp(1.1rem, 2.5vw, 1.3rem)",
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
    fontSize: "clamp(0.8rem, 2vw, 0.85rem)",
    fontWeight: 500,
    color: "#ffffff",
  },
  ppeSub: {
    fontSize: "clamp(0.7rem, 1.5vw, 0.75rem)",
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
    fontSize: "clamp(0.8rem, 2vw, 0.9rem)",
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
    fontSize: "clamp(3rem, 8vw, 4rem)",
    fontWeight: 700,
    color: "#00e676",
    lineHeight: 1,
    margin: "8px 0 4px",
  },
  counterSub: {
    fontSize: "clamp(0.75rem, 1.8vw, 0.8rem)",
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
    fontSize: "clamp(1.2rem, 3vw, 1.4rem)",
    fontWeight: 700,
    color: "#ffffff",
  },
  counterSmallLabel: {
    fontSize: "clamp(0.6rem, 1.5vw, 0.65rem)",
    color: "#888",
    marginTop: "2px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
  },
}
