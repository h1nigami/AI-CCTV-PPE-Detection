import { useState, useEffect, useCallback } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"
import type { TimelineEvent } from "../types"

const LABELS: { key: string; label: string }[] = [
  { key: "", label: "Все" },
  { key: "violation", label: "Нарушения" },
  { key: "approved", label: "Пропуски" },
  { key: "danger_zone", label: "Опасная зона" },
]

const SUB_LABEL_MAP: Record<string, string> = {
  no_helmet: "Нет каски",
  no_mask: "Нет маски",
  no_vest: "Нет жилета",
  danger_zone: "Опасная зона",
  ok_gesture: "Жест ОК",
  raised_hand: "Поднятая рука",
}

function fmtTime(ts: number) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function fmtDate(ts: number) {
  const d = new Date(ts * 1000)
  const today = new Date()
  const isToday = d.toDateString() === today.toDateString()
  return isToday
    ? "Сегодня"
    : d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
}

export default function EventsPage() {
  const { cameras } = useCamerasContext()
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filterCam, setFilterCam] = useState("")
  const [filterLabel, setFilterLabel] = useState("")
  const [playEvent, setPlayEvent] = useState<TimelineEvent | null>(null)

  const camList = cameras.map((c) => c.name)

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getEvents({
        camera: filterCam || undefined,
        label: filterLabel || undefined,
        limit: 50,
      })
      setEvents(data.events)
      setTotal(data.total)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [filterCam, filterLabel])

  useEffect(() => {
    fetchEvents()
    const iv = setInterval(fetchEvents, 5000)
    return () => clearInterval(iv)
  }, [fetchEvents])

  return (
    <div style={styles.page}>
      {/* ── Header ── */}
      <div style={styles.header}>
        <h1 style={styles.title}>ЛЕНТА СОБЫТИЙ</h1>
        <span style={styles.count}>{total} событий</span>
      </div>

      {/* ── Filters ── */}
      <div style={styles.filters}>
        <select
          style={styles.select}
          value={filterCam}
          onChange={(e) => setFilterCam(e.target.value)}
        >
          <option value="">Все камеры</option>
          {camList.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <div style={styles.labelTabs}>
          {LABELS.map((l) => (
            <button
              key={l.key}
              style={{
                ...styles.tab,
                ...(filterLabel === l.key ? styles.tabActive : {}),
              }}
              onClick={() => setFilterLabel(l.key)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Event list ── */}
      <div style={styles.list}>
        {loading && events.length === 0 && (
          <div style={styles.empty}>Загрузка...</div>
        )}
        {!loading && events.length === 0 && (
          <div style={styles.empty}>Нет событий</div>
        )}
        {events.map((ev) => (
          <EventCard
            key={ev.id}
            event={ev}
            onPlay={() => setPlayEvent(ev)}
          />
        ))}
      </div>

      {/* ── Video player modal ── */}
      {playEvent && (
        <div style={styles.overlay} onClick={() => setPlayEvent(null)}>
          <div style={styles.player} onClick={(e) => e.stopPropagation()}>
            <button style={styles.closeBtn} onClick={() => setPlayEvent(null)}>
              ✕
            </button>
            <div style={styles.playerHeader}>
              {playEvent.cameraName} — {fmtTime(playEvent.timestamp)}
              {playEvent.personName && <span> — {playEvent.personName}</span>}
            </div>
            {playEvent.hasClip && playEvent.clipUrl ? (
              <video
                key={playEvent.id}
                src={playEvent.clipUrl}
                style={styles.video}
                controls
                autoPlay
              />
            ) : (
              <div style={styles.noClip}>Видео недоступно</div>
            )}
            <div style={styles.playerMeta}>
              {playEvent.personName && (
                <span>Сотрудник: {playEvent.personName}</span>
              )}
              {playEvent.subLabel && (
                <span>
                  Тип: {SUB_LABEL_MAP[playEvent.subLabel] || playEvent.subLabel}
                </span>
              )}
              <span>
                СИЗ: {playEvent.ppeHelmet ? "✓" : "✗"} Каска{" "}
                {playEvent.ppeMask ? "✓" : "✗"} Маска{" "}
                {playEvent.ppeVest ? "✓" : "✗"} Жилет
              </span>
              {playEvent.endTime && (
                <span>
                  Длительность:{" "}
                  {(playEvent.endTime - playEvent.startTime).toFixed(1)}с
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EventCard({
  event: ev,
  onPlay,
}: {
  event: TimelineEvent
  onPlay: () => void
}) {
  const color =
    ev.label === "violation"
      ? "#ff5252"
      : ev.label === "approved"
        ? "#00e676"
        : ev.label === "danger_zone"
          ? "#ff9100"
          : "#888"

  return (
    <div style={styles.card} onClick={onPlay}>
      {/* Snapshot / placeholder */}
      <div style={styles.thumbWrap}>
        {ev.hasSnapshot && ev.snapshotUrl ? (
          <img src={ev.snapshotUrl} alt="" style={styles.thumb} />
        ) : (
          <div style={styles.thumbPlaceholder}>
            <span style={{ fontSize: "1.5rem" }}>
              {ev.label === "violation" ? "🚨" : ev.label === "approved" ? "✅" : "⚠️"}
            </span>
          </div>
        )}
        {ev.hasClip && (
          <div style={styles.playBadge}>
            ▶
          </div>
        )}
      </div>

      {/* Info */}
      <div style={styles.cardBody}>
        <div style={styles.cardRow}>
          <span style={{ ...styles.labelBadge, background: color }}>
            {ev.label === "violation"
              ? "Нарушение"
              : ev.label === "approved"
                ? "Пропуск"
                : ev.label === "danger_zone"
                  ? "Опасная зона"
                  : ev.label}
          </span>
          <span style={styles.camName}>{ev.cameraName}</span>
        </div>

        <div style={styles.cardRow}>
          <span style={styles.time}>{fmtTime(ev.timestamp)}</span>
          <span style={styles.date}>{fmtDate(ev.timestamp)}</span>
        </div>

        {ev.personName && (
          <div style={styles.cardRow}>
            <span style={styles.personName}>{ev.personName}</span>
          </div>
        )}

        <div style={styles.ppeRow}>
          <PPEIcon label="K" ok={ev.ppeHelmet} />
          <PPEIcon label="M" ok={ev.ppeMask} />
          <PPEIcon label="Ж" ok={ev.ppeVest} />
        </div>
      </div>
    </div>
  )
}

function PPEIcon({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      style={{
        ...styles.ppeIcon,
        background: ok ? "#1b5e20" : "#5c1010",
        color: ok ? "#69f0ae" : "#ff5252",
      }}
    >
      {label}
    </span>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#1a1a1a",
    color: "#eee",
    minHeight: 0,
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 24px",
    borderBottom: "1px solid #333",
  },
  title: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 700,
    fontSize: "1rem",
    letterSpacing: "3px",
    color: "#00e676",
    textTransform: "uppercase",
    margin: 0,
  },
  count: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
  },
  filters: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "10px 24px",
    borderBottom: "1px solid #333",
    flexWrap: "wrap" as const,
  },
  select: {
    background: "#2a2a2a",
    color: "#eee",
    border: "1px solid #444",
    borderRadius: "6px",
    padding: "6px 12px",
    fontSize: "0.75rem",
    fontFamily: "monospace",
    outline: "none",
    cursor: "pointer",
  },
  labelTabs: {
    display: "flex",
    gap: "4px",
  },
  tab: {
    background: "transparent",
    color: "#888",
    border: "1px solid #444",
    borderRadius: "6px",
    padding: "4px 12px",
    fontSize: "0.7rem",
    cursor: "pointer",
    fontFamily: "monospace",
    transition: "all 0.15s",
  },
  tabActive: {
    background: "#00e67622",
    color: "#00e676",
    borderColor: "#00e676",
  },
  list: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "12px 24px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  empty: {
    textAlign: "center" as const,
    color: "#666",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    padding: "40px 0",
  },
  card: {
    display: "flex",
    gap: "12px",
    background: "#222",
    borderRadius: "8px",
    padding: "10px",
    cursor: "pointer",
    transition: "background 0.15s",
    border: "1px solid #333",
  },
  thumbWrap: {
    position: "relative" as const,
    width: "120px",
    minHeight: "68px",
    borderRadius: "4px",
    overflow: "hidden",
    flexShrink: 0,
    background: "#1a1a1a",
  },
  thumb: {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    display: "block",
  },
  thumbPlaceholder: {
    width: "100%",
    height: "68px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#1a1a1a",
  },
  playBadge: {
    position: "absolute" as const,
    bottom: "4px",
    right: "4px",
    background: "rgba(0,0,0,0.7)",
    color: "#fff",
    borderRadius: "4px",
    padding: "1px 6px",
    fontSize: "0.65rem",
  },
  cardBody: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: 0,
  },
  cardRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  labelBadge: {
    fontFamily: "monospace",
    fontSize: "0.6rem",
    fontWeight: 700,
    color: "#fff",
    padding: "2px 8px",
    borderRadius: "4px",
    letterSpacing: "0.5px",
  },
  camName: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#aaa",
  },
  time: {
    fontFamily: "monospace",
    fontSize: "0.75rem",
    color: "#ccc",
  },
  date: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#666",
  },
  personName: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.8rem",
    color: "#69f0ae",
  },
  ppeRow: {
    display: "flex",
    gap: "4px",
    marginTop: "2px",
  },
  ppeIcon: {
    fontFamily: "monospace",
    fontSize: "0.55rem",
    fontWeight: 700,
    padding: "1px 6px",
    borderRadius: "3px",
  },
  overlay: {
    position: "fixed" as const,
    inset: 0,
    background: "rgba(0,0,0,0.85)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  player: {
    background: "#1a1a1a",
    borderRadius: "12px",
    overflow: "hidden",
    maxWidth: "90vw",
    maxHeight: "90vh",
    display: "flex",
    flexDirection: "column",
  },
  closeBtn: {
    position: "absolute" as const,
    top: "12px",
    right: "12px",
    background: "rgba(0,0,0,0.6)",
    color: "#fff",
    border: "none",
    borderRadius: "50%",
    width: "32px",
    height: "32px",
    fontSize: "1rem",
    cursor: "pointer",
    zIndex: 10,
  },
  playerHeader: {
    padding: "12px 16px",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    color: "#aaa",
    borderBottom: "1px solid #333",
  },
  video: {
    maxWidth: "90vw",
    maxHeight: "70vh",
    display: "block",
  },
  noClip: {
    padding: "60px 80px",
    color: "#666",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    textAlign: "center" as const,
  },
  playerMeta: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "12px",
    padding: "10px 16px",
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    borderTop: "1px solid #333",
  },
}
