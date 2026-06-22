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

  const { ppe, counters, persons, personsByCam } = useMemo(() => {
    const result: {
      ppe: PpeStatus
      counters: { total: number; approved: number; violations: number; logCount: number }
      persons: PersonSummary[]
      personsByCam: { cam: string; persons: PersonSummary[] }[]
    } = {
      ppe: { helmet: null, mask: null, vest: null, zone: null, gesture: null },
      counters: { total: 0, approved: 0, violations: 0, logCount: logs.length },
      persons: [],
      personsByCam: [],
    }

    if (logs.length === 0) return result

    const latestByCam: Record<string, LogEntry> = {}
    logs.forEach((l) => {
      if (!latestByCam[l.cam_id]) latestByCam[l.cam_id] = l
    })

    // Индикаторы «Статус проверки СИЗ»: по выбранной/полноэкранной камере, а
    // если ни одна не выбрана (обычный вид сетки) — не зависаем на «Ожидании»:
    // при единственной камере берём её, при нескольких — агрегируем по всем
    // (любое нарушение на любой камере → «не обнаружено»). Иначе панель вечно
    // показывала «Ожидание», пока оператор не развернёт камеру.
    const camIds = Object.keys(latestByCam)
    const ppeMessage = selectedCam
      ? latestByCam[selectedCam]?.message
      : camIds.length === 1
        ? latestByCam[camIds[0]]?.message
        : camIds.map((c) => latestByCam[c]?.message).filter(Boolean).join(" | ")
    result.ppe = parsePpeFromMessage(ppeMessage)

    // Счётчики и покамерный список — по ТЕКУЩЕМУ кадру каждой камеры (последняя
    // лог-строка), а не по всему кольцевому буферу.
    Object.entries(latestByCam).forEach(([cam, log]) => {
      result.counters.total += parsePeopleCount(log.message)
      const ps = parsePersonsFromMessage(log.message)
      ps.forEach((p) => {
        if (p.approved) result.counters.approved += 1
        if (p.violation) result.counters.violations += 1
      })
      result.persons.push(...ps)
      if (ps.length) result.personsByCam.push({ cam, persons: ps })
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

  // Панель адаптируется под выбранные режимы детекции:
  //  • только «Люди» → лишь счётчик людей;
  //  • + «СИЗ» → плавно появляется блок проверки СИЗ (каска/маска/жилет/зона);
  //  • + «Лица» → плавно появляется покамерный список «кто на какой камере».
  // detectModes === null (ещё не загружено) → считаем всё включённым.
  const peopleOn = detectModes ? detectModes.people !== false : true
  const ppeOn = detectModes ? detectModes.ppe !== false : true
  const facesOn = detectModes ? detectModes.faces !== false : true

  const ppeRows: { key: keyof PpeStatus; icon: string; label: string }[] = [
    { key: "helmet", icon: "⛑️", label: "СИЗ Каска" },
    { key: "mask", icon: "😷", label: "СИЗ Маска" },
    { key: "vest", icon: "🦺", label: "СИЗ Жилет" },
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
    <div style={isSidebar ? styles.sidebar : styles.sheet}>
      <style>{`@keyframes cardReveal{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}`}</style>
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

      {/* «Люди» — базовый режим: счётчик людей в кадре. */}
      {peopleOn && (
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

          {/* «Допущено/Нарушений» осмысленны только когда есть проверка СИЗ или лиц. */}
          {(ppeOn || facesOn) && (
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
          )}
        </div>
      )}

      {/* «СИЗ» — плавно появляющийся блок проверки средств защиты. */}
      {ppeOn && (
        <div style={{ ...styles.panelCard, animation: "cardReveal 0.35s cubic-bezier(0.4,0,0.2,1) both" }}>
          <div style={styles.cardTitle}>Статус проверки СИЗ</div>
          {ppeRows.map(({ key, icon, label }) => {
            const val = ppe[key]
            const ok = val === true
            const fail = val === false

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
                <div style={{ ...styles.ppeIconWrap, ...wrapClass }}>{icon}</div>
                <div style={styles.ppeInfo}>
                  <div style={styles.ppeName}>{label}</div>
                  <div style={styles.ppeSub}>{ppeSubs[key](val)}</div>
                </div>
                <div style={{ ...styles.ppeCheck, ...checkClass }}>{checkText}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* «Лица» — плавно появляющийся покамерный список: кто на какой камере. */}
      {facesOn && (
        <div style={{ ...styles.panelCard, animation: "cardReveal 0.35s cubic-bezier(0.4,0,0.2,1) both" }}>
          <div style={styles.cardTitle}>Люди по камерам</div>
          {/* Легенда маркеров статуса. */}
          <div style={styles.legend}>
            <span style={{ color: "#00e676" }}>✓ Пропуск</span>
            <span style={{ color: "#ffd600" }}>✗ Нарушение</span>
            <span style={{ color: "#ff9800" }}>⚠ Зона</span>
            <span style={{ color: "#00b0ff" }}>• Обычный</span>
          </div>
          {(() => {
            // Если выбрана/открыта камера — показываем только её, иначе все.
            const visibleByCam = selectedCam
              ? personsByCam.filter((g) => g.cam === selectedCam)
              : personsByCam
            if (visibleByCam.length === 0) {
              return <div style={styles.empty}>Никого не распознано</div>
            }
            return visibleByCam.map(({ cam, persons: camPersons }) => (
              <div key={cam} style={styles.camGroup}>
                <div style={styles.camHeader}>
                  <span style={styles.camDot} />
                  {cam.toUpperCase()}
                  <span style={styles.camCount}>{camPersons.length}</span>
                </div>
                {camPersons.map((p, i) => (
                  <div key={i} style={styles.personRow}>
                    <span style={{ ...styles.personDot, background: personColor(p) }} />
                    <span style={styles.personName}>{p.name}</span>
                    {p.ppe && <span style={styles.personPpe}>{p.ppe}</span>}
                    <span style={{ color: personColor(p), fontFamily: "monospace", fontSize: "0.7rem" }}>
                      {p.approved ? "✓" : p.violation ? "✗" : p.danger ? "⚠" : "•"}
                    </span>
                  </div>
                ))}
              </div>
            ))
          })()}
        </div>
      )}
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
  empty: {
    fontSize: "clamp(0.7rem, 1.5vw, 0.78rem)",
    color: "#888",
    textAlign: "center" as const,
    padding: "12px 0",
  },
  legend: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "6px 12px",
    fontFamily: "monospace",
    fontSize: "0.6rem",
    marginBottom: "10px",
    paddingBottom: "8px",
    borderBottom: "1px solid #333",
  },
  camGroup: {
    marginBottom: "10px",
  },
  camHeader: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "0.62rem",
    fontWeight: 700,
    letterSpacing: "1.5px",
    color: "#888",
    textTransform: "uppercase" as const,
    marginBottom: "6px",
  },
  camDot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "#00e676",
    flexShrink: 0,
  },
  camCount: {
    marginLeft: "auto",
    fontFamily: "monospace",
    fontSize: "0.6rem",
    color: "#666",
    background: "#1a1a1a",
    border: "1px solid #333",
    borderRadius: "4px",
    padding: "0 5px",
  },
  personRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "6px 8px",
    marginBottom: "4px",
    background: "#2a2a2a",
    borderRadius: "6px",
  },
  personDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    flexShrink: 0,
  },
  personName: {
    fontSize: "0.75rem",
    color: "#ffffff",
    fontFamily: "'Inter', sans-serif",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  personPpe: {
    marginLeft: "auto",
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#888",
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
