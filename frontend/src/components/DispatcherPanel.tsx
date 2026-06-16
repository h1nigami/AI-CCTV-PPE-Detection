import { useState, useEffect, useMemo, useCallback, useRef } from "react"
import { useCamerasContext } from "../contexts/CameraContext"
import { api } from "../api/client"
import type { LogEntry, PpeStatus, PersonSummary } from "../types"

// ============================================================
// Диспетчерская панель — открывается по клику на камеру.
// Содержит: крупный видеопоток, ленту событий, статус СИЗ,
// список людей, кнопку управления аналитикой.
// Разметку можно менять — это базовая структура.
// ============================================================

export function DispatcherPanel() {
  const { dispatcher, closeDispatcher, cameras } = useCamerasContext()
  const { cameraName } = dispatcher

  // Информация о выбранной камере
  const camera = useMemo(
    () => cameras.find((c) => c.name === cameraName) || null,
    [cameras, cameraName],
  )

  // Состояние детекции (локальный toggle)
  const [detectEnabled, setDetectEnabled] = useState(camera?.detect_enabled ?? true)

  // Логи для выбранной камеры
  const [logs, setLogs] = useState<LogEntry[]>([])

  // Флаг загрузки
  const [loading, setLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Подгружаем события для камеры с polling'ом (каждую секунду)
  useEffect(() => {
    if (!cameraName) return

    const fetchLogs = async () => {
      try {
        const data = await api.getLogs(cameraName)
        setLogs(data.logs)
      } catch {
        // игнорируем ошибки при polling'е
      }
    }

    setLoading(true)
    fetchLogs().finally(() => setLoading(false))

    // Опрашиваем раз в секунду для обновления статусов СИЗ
    pollRef.current = setInterval(fetchLogs, 1000)

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [cameraName])

  // Синхронизируем detectEnabled при смене камеры
  useEffect(() => {
    setDetectEnabled(camera?.detect_enabled ?? true)
  }, [camera])

  // Переключение аналитики
  const toggleAnalytics = useCallback(async () => {
    if (!cameraName) return
    const next = !detectEnabled
    try {
      await api.toggleAnalytics(cameraName, next)
      setDetectEnabled(next)
    } catch {
      // Ошибка — возвращаем предыдущее состояние
    }
  }, [cameraName, detectEnabled])

  // Парсим СИЗ и людей из логов (взято из LeftPanel)
  const { ppe, persons } = useMemo(() => {
    const result: {
      ppe: PpeStatus
      persons: PersonSummary[]
    } = {
      ppe: { helmet: null, mask: null, vest: null, zone: null, gesture: null },
      persons: [],
    }

    if (logs.length === 0) return result

    // Берём самую свежую запись (API возвращает reversed — первая = новая)
    const latest = logs[0]
    if (!latest?.message) return result

    const m = latest.message
    if (!m.includes("Людей:")) return result

    const personParts = m.split(" | ").filter((p) => /^[^[]+?\[.*?\]:/.test(p))
    let helmetOk = true
    let maskOk = true
    let vestOk = true
    let inDanger = false
    let hasPass = false

    for (const part of personParts) {
      const ppeMatch = part.match(/\[(.*?)\]/)
      if (ppeMatch) {
        const ppeStr = ppeMatch[1]
        if (ppeStr.includes("!К")) helmetOk = false
        if (ppeStr.includes("!М")) maskOk = false
        if (ppeStr.includes("!Ж")) vestOk = false
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

    return result
  }, [logs])

  // Если панель закрыта — не рендерим
  if (!dispatcher.open || !cameraName) return null

  return (
    <div style={styles.panel}>
      {/* Шапка панели */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={styles.camIcon}>
            <svg width="18" height="18" viewBox="0 0 28 28" fill="none">
              <rect x="2" y="6" width="24" height="16" rx="3" stroke="#00e5ff" strokeWidth="1.5" />
              <circle cx="14" cy="14" r="5" stroke="#00e5ff" strokeWidth="1.5" />
              <path d="M22 6l4-3v18l-4-3" stroke="#00e5ff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div style={styles.camTitle}>{cameraName.toUpperCase()}</div>
            <div style={styles.camSource}>{String(camera?.source || "")}</div>
          </div>
        </div>

        {/* Кнопка закрытия */}
        <button style={styles.closeBtn} onClick={closeDispatcher} title="Закрыть панель">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M4 4l10 10M14 4l-10 10" stroke="#4a6a8a" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Управление аналитикой */}
      <div style={styles.controls}>
        <button
          style={{
            ...styles.analyticsBtn,
            ...(detectEnabled ? styles.analyticsOn : styles.analyticsOff),
          }}
          onClick={toggleAnalytics}
        >
          <div
            style={{
              ...styles.toggleDot,
              background: detectEnabled ? "#00ff88" : "#ff3355",
            }}
          />
          АНАЛИТИКА: {detectEnabled ? "ВКЛ" : "ВЫКЛ"}
        </button>
      </div>

      {/* Секция: статус СИЗ */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>СТАТУС СИЗ</div>
        <div style={styles.ppeGrid}>
          {([
            { key: "helmet" as const, icon: "⛑", label: "Каска" },
            { key: "mask" as const, icon: "😷", label: "Маска" },
            { key: "vest" as const, icon: "🦺", label: "Жилет" },
            { key: "zone" as const, icon: "⚠", label: "Зона" },
            { key: "gesture" as const, icon: "👌", label: "Жест" },
          ]).map(({ key, icon, label }) => {
            const val = ppe[key]
            const ok = val === true
            const color =
              val === null ? "#4a6a8a" : ok ? "#00ff88" : "#ff3355"
            return (
              <div key={key} style={{ ...styles.ppeItem, borderColor: color + "44" }}>
                <div style={styles.ppeIcon}>{icon}</div>
                <div style={styles.ppeLabel}>{label}</div>
                <div style={{ ...styles.ppeValue, color }}>
                  {val === null ? "—" : ok ? "OK" : "!"}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Секция: люди */}
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
                <div style={{ color: p.approved ? "#00ff88" : p.violation ? "#ff3355" : "#ffd600" }}>
                  {p.approved ? "✓" : p.violation ? "✗" : "?"}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Секция: последние события */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>
          СОБЫТИЯ
          <span style={styles.sectionCount}>{logs.length}</span>
        </div>
        <div style={styles.eventList}>
          {loading && <div style={styles.empty}>Загрузка...</div>}
          {!loading && logs.length === 0 && (
            <div style={styles.empty}>Ожидание событий</div>
          )}
          {!loading &&
            logs
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
                      borderLeftColor: isViolation
                        ? "#ff3355"
                        : isWarning
                          ? "#ffd600"
                          : "#00ff88",
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
    width: "380px",
    minWidth: "380px",
    background: "#0d1520",
    borderLeft: "1px solid #1a3a5c",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    animation: "slideIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid #1a3a5c",
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
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.85rem",
    color: "#c8dff0",
    letterSpacing: "1px",
    lineHeight: "1.2",
  },
  camSource: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.55rem",
    color: "#4a6a8a",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "200px",
  },
  closeBtn: {
    background: "none",
    border: "1px solid #1a3a5c",
    borderRadius: "4px",
    padding: "4px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#4a6a8a",
    flexShrink: 0,
    transition: "all 0.2s",
  },
  controls: {
    padding: "10px 16px",
    borderBottom: "1px solid #1a3a5c",
    flexShrink: 0,
  },
  analyticsBtn: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.75rem",
    letterSpacing: "1px",
    border: "1px solid #1a3a5c",
    borderRadius: "5px",
    padding: "6px 14px",
    cursor: "pointer",
    textTransform: "uppercase",
    width: "100%",
    background: "transparent",
    transition: "all 0.2s",
  },
  analyticsOn: {
    borderColor: "#00ff8844",
    color: "#00ff88",
  },
  analyticsOff: {
    borderColor: "#ff335544",
    color: "#ff3355",
  },
  toggleDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    flexShrink: 0,
  },
  section: {
    borderBottom: "1px solid #1a3a5c",
    padding: "12px 16px",
    flexShrink: 0,
  },
  sectionTitle: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.6rem",
    letterSpacing: "3px",
    color: "#4a6a8a",
    textTransform: "uppercase",
    marginBottom: "10px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  sectionCount: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.6rem",
    color: "#1a3a5c",
    background: "#080d14",
    border: "1px solid #1a3a5c",
    borderRadius: "3px",
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
    background: "#111c2b",
    border: "1px solid #1a3a5c",
    borderRadius: "5px",
    transition: "border-color 0.3s",
  },
  ppeIcon: {
    fontSize: "1rem",
    flexShrink: 0,
  },
  ppeLabel: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.75rem",
    color: "#c8dff0",
    flex: 1,
  },
  ppeValue: {
    fontFamily: "'Share Tech Mono', monospace",
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
    background: "#111c2b",
    borderRadius: "4px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
  },
  personName: {
    color: "#c8dff0",
    minWidth: "80px",
  },
  personPpe: {
    color: "#4a6a8a",
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
    background: "#111c2b",
    borderLeft: "2px solid",
    borderRadius: "3px",
  },
  eventTime: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.55rem",
    color: "#4a6a8a",
    marginBottom: "2px",
  },
  eventMsg: {
    fontSize: "0.7rem",
    color: "#c8dff0",
    lineHeight: "1.3",
  },
  empty: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    color: "#4a6a8a",
    textAlign: "center",
    padding: "12px",
  },
}
