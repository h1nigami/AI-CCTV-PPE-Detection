import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"
import type { RecordingSegment, TimelineEvent } from "../types"

// ============================================================
// Архив NVR: выбор камеры + даты, таймлайн сегментов за сутки с
// наложенными метками событий, плеер. Источники — /api/recordings
// и /api/events. Клик по метке события → переход к моменту в записи.
// ============================================================

const DAY_SEC = 86400

/** Начало локальных суток (unix-секунды) для строки YYYY-MM-DD. */
function dayStartUnix(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number)
  return new Date(y, m - 1, d, 0, 0, 0, 0).getTime() / 1000
}

function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function fmtClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("ru-RU", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  })
}

function fmtSize(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} ГБ`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} МБ`
  return `${(bytes / 1e3).toFixed(0)} КБ`
}

function eventColor(label: string): string {
  return label === "violation" ? "#ff5252"
    : label === "approved" ? "#00e676"
      : label === "danger_zone" ? "#ff9100" : "#42a5f5"
}

function eventLabelRu(label: string): string {
  return label === "violation" ? "Нарушение"
    : label === "approved" ? "Пропуск"
      : label === "danger_zone" ? "Опасная зона" : label
}

/** Что играем в плеере: архивный сегмент или event-клип, с опц. перемоткой. */
interface PlayerState {
  src: string
  title: string
  seekOffset: number  // секунды от начала файла, куда перемотать
  segId?: string
}

export default function ArchivePage() {
  const { cameras } = useCamerasContext()
  const camList = cameras.map((c) => c.name)

  const [camId, setCamId] = useState("")
  const [date, setDate] = useState(todayStr())
  const [segments, setSegments] = useState<RecordingSegment[]>([])
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [showEvents, setShowEvents] = useState(true)
  const [loading, setLoading] = useState(false)
  const [player, setPlayer] = useState<PlayerState | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  // Камера по умолчанию — первая доступная.
  useEffect(() => {
    if (!camId && camList.length > 0) setCamId(camList[0])
  }, [camList, camId])

  const dayStart = useMemo(() => dayStartUnix(date), [date])
  const dayEnd = dayStart + DAY_SEC

  const fetchData = useCallback(async () => {
    if (!camId) return
    try {
      setLoading(true)
      const [recs, evs] = await Promise.all([
        api.getRecordings({ camId, from: dayStart, to: dayEnd, limit: 1000 }),
        api.getEvents({ camera: camId, limit: 1000 }),
      ])
      setSegments(recs.recordings)
      // У /api/events нет фильтра по времени — режем по суткам на клиенте.
      setEvents(evs.events.filter((e) => e.timestamp >= dayStart && e.timestamp < dayEnd))
    } catch {
      setSegments([])
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [camId, dayStart, dayEnd])

  useEffect(() => { fetchData() }, [fetchData])

  /** Найти сегмент архива, покрывающий момент времени. */
  const segmentAt = useCallback(
    (ts: number) => segments.find((r) => r.startTime <= ts && r.endTime >= ts),
    [segments]
  )

  /** Клик по событию: открыть покрывающий сегмент с перемоткой к моменту,
   *  иначе — собственный event-клип (если есть). */
  const openEvent = useCallback((ev: TimelineEvent) => {
    const seg = segmentAt(ev.timestamp)
    if (seg) {
      setPlayer({
        src: seg.playUrl, segId: seg.id,
        seekOffset: Math.max(0, ev.timestamp - seg.startTime),
        title: `${eventLabelRu(ev.label)} · ${fmtClock(ev.timestamp)}${ev.personName ? " · " + ev.personName : ""}`,
      })
    } else if (ev.hasClip && ev.clipUrl) {
      setPlayer({
        src: ev.clipUrl, seekOffset: 0,
        title: `${eventLabelRu(ev.label)} · ${fmtClock(ev.timestamp)} (event-клип)`,
      })
    }
  }, [segmentAt])

  const openSegment = useCallback((seg: RecordingSegment) => {
    setPlayer({ src: seg.playUrl, segId: seg.id, seekOffset: 0,
      title: `${fmtClock(seg.startTime)} – ${fmtClock(seg.endTime)}` })
  }, [])

  // Перемотка к моменту события после загрузки метаданных видео.
  const handleLoadedMeta = useCallback(() => {
    if (videoRef.current && player && player.seekOffset > 0) {
      try { videoRef.current.currentTime = player.seekOffset } catch { /* ignore */ }
    }
  }, [player])

  const totalDuration = segments.reduce((s, r) => s + r.duration, 0)
  const motionCount = segments.filter((r) => r.hasMotion).length

  return (
    <div style={styles.page}>
      {/* ── Header ── */}
      <div style={styles.header}>
        <h1 style={styles.title}>АРХИВ ЗАПИСЕЙ</h1>
        <span style={styles.count}>
          {segments.length} сегм. · {(totalDuration / 60).toFixed(0)} мин · {events.length} событий
        </span>
      </div>

      {/* ── Controls ── */}
      <div style={styles.controls}>
        <select style={styles.select} value={camId} onChange={(e) => { setCamId(e.target.value); setPlayer(null) }}>
          {camList.length === 0 && <option value="">Нет камер</option>}
          {camList.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          type="date" style={styles.select} value={date} max={todayStr()}
          onChange={(e) => { setDate(e.target.value); setPlayer(null) }}
        />
        <button style={styles.refreshBtn} onClick={fetchData}>Обновить</button>
        <label style={styles.checkLabel}>
          <input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} />
          События
        </label>
      </div>

      {/* ── Player ── */}
      {player && (
        <div style={styles.playerWrap}>
          <video
            ref={videoRef}
            key={player.src + player.seekOffset}
            src={player.src}
            style={styles.video}
            controls autoPlay
            onLoadedMetadata={handleLoadedMeta}
          />
          <div style={styles.playerMeta}>{player.title}</div>
        </div>
      )}

      {/* ── Timeline (24h) ── */}
      <div style={styles.timelineWrap}>
        <div style={styles.timelineBar}>
          {/* сегменты записи */}
          {segments.map((r) => {
            const left = Math.max(0, ((r.startTime - dayStart) / DAY_SEC) * 100)
            const width = Math.max(0.25, (r.duration / DAY_SEC) * 100)
            return (
              <div
                key={r.id}
                title={`${fmtClock(r.startTime)} (${r.duration.toFixed(0)}с)`}
                onClick={() => openSegment(r)}
                style={{
                  ...styles.segment, left: `${left}%`, width: `${width}%`,
                  background: r.hasMotion ? "#00c853" : "#555",
                  outline: player?.segId === r.id ? "2px solid #00e676" : "none",
                  zIndex: player?.segId === r.id ? 2 : 1,
                }}
              />
            )
          })}
          {/* метки событий */}
          {showEvents && events.map((ev) => {
            const left = ((ev.timestamp - dayStart) / DAY_SEC) * 100
            return (
              <div
                key={ev.id}
                title={`${eventLabelRu(ev.label)} · ${fmtClock(ev.timestamp)}${ev.personName ? " · " + ev.personName : ""}`}
                onClick={(e) => { e.stopPropagation(); openEvent(ev) }}
                style={{ ...styles.eventMark, left: `${left}%`, background: eventColor(ev.label) }}
              />
            )
          })}
        </div>
        <div style={styles.hourTicks}>
          {Array.from({ length: 25 }).map((_, h) => (
            <span key={h} style={{ ...styles.tick, left: `${(h / 24) * 100}%` }}>
              {h % 3 === 0 ? `${String(h).padStart(2, "0")}` : ""}
            </span>
          ))}
        </div>
        {/* легенда */}
        <div style={styles.legend}>
          <span style={styles.legendItem}><i style={{ ...styles.swatch, background: "#00c853" }} />запись с движением</span>
          <span style={styles.legendItem}><i style={{ ...styles.swatch, background: "#555" }} />статика</span>
          <span style={styles.legendItem}><i style={{ ...styles.swatch, background: "#ff5252" }} />нарушение</span>
          <span style={styles.legendItem}><i style={{ ...styles.swatch, background: "#00e676" }} />пропуск</span>
        </div>
      </div>

      {/* ── Segment list ── */}
      <div style={styles.list}>
        {loading && segments.length === 0 && <div style={styles.empty}>Загрузка…</div>}
        {!loading && segments.length === 0 && (
          <div style={styles.empty}>
            Нет записей за выбранные сутки.<br />
            <span style={{ fontSize: "0.7rem" }}>
              Запись включается переменной RECORD_ENABLED на бэкенде.
            </span>
          </div>
        )}
        {segments.map((r) => (
          <div
            key={r.id}
            style={{ ...styles.row, ...(player?.segId === r.id ? styles.rowActive : {}) }}
            onClick={() => openSegment(r)}
          >
            <span style={styles.rowTime}>{fmtClock(r.startTime)}</span>
            <span style={styles.rowDur}>{r.duration.toFixed(0)} с</span>
            <span style={styles.rowSize}>{fmtSize(r.sizeBytes)}</span>
            <span style={{ ...styles.motionDot, color: r.hasMotion ? "#69f0ae" : "#555" }}>
              {r.hasMotion ? "● движение" : "○ статика"}
            </span>
            <span style={styles.playLink}>▶</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: "flex", flexDirection: "column", flex: 1, background: "#1a1a1a", color: "#eee", minHeight: 0, overflow: "hidden" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 24px", borderBottom: "1px solid #333" },
  title: { fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: "1rem", letterSpacing: "3px", color: "#00e676", textTransform: "uppercase", margin: 0 },
  count: { fontFamily: "monospace", fontSize: "0.7rem", color: "#888" },
  controls: { display: "flex", alignItems: "center", gap: "12px", padding: "10px 24px", borderBottom: "1px solid #333", flexWrap: "wrap" as const },
  select: { background: "#2a2a2a", color: "#eee", border: "1px solid #444", borderRadius: "6px", padding: "6px 12px", fontSize: "0.75rem", fontFamily: "monospace", outline: "none", cursor: "pointer" },
  refreshBtn: { background: "#00e67622", color: "#00e676", border: "1px solid #00e676", borderRadius: "6px", padding: "6px 14px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  checkLabel: { display: "flex", alignItems: "center", gap: "6px", fontFamily: "monospace", fontSize: "0.72rem", color: "#aaa", cursor: "pointer" },
  playerWrap: { padding: "12px 24px", borderBottom: "1px solid #333" },
  video: { width: "100%", maxHeight: "45vh", background: "#000", borderRadius: "8px", display: "block" },
  playerMeta: { padding: "8px 2px 0", fontFamily: "monospace", fontSize: "0.72rem", color: "#aaa" },
  timelineWrap: { padding: "16px 24px 8px", borderBottom: "1px solid #333" },
  timelineBar: { position: "relative" as const, height: "32px", background: "#111", borderRadius: "4px", overflow: "hidden", border: "1px solid #2a2a2a" },
  segment: { position: "absolute" as const, top: "8px", bottom: "2px", borderRadius: "2px", cursor: "pointer" },
  eventMark: { position: "absolute" as const, top: "0px", height: "8px", width: "3px", transform: "translateX(-1px)", borderRadius: "1px", cursor: "pointer", zIndex: 3 },
  hourTicks: { position: "relative" as const, height: "16px", marginTop: "2px" },
  tick: { position: "absolute" as const, transform: "translateX(-50%)", fontFamily: "monospace", fontSize: "0.6rem", color: "#666" },
  legend: { display: "flex", gap: "16px", flexWrap: "wrap" as const, marginTop: "4px", fontFamily: "monospace", fontSize: "0.62rem", color: "#888" },
  legendItem: { display: "flex", alignItems: "center", gap: "5px" },
  swatch: { width: "10px", height: "10px", borderRadius: "2px", display: "inline-block" },
  list: { flex: 1, overflowY: "auto" as const, padding: "8px 24px 16px", display: "flex", flexDirection: "column", gap: "4px" },
  empty: { textAlign: "center" as const, color: "#666", fontFamily: "monospace", fontSize: "0.8rem", padding: "40px 0", lineHeight: 1.8 },
  row: { display: "flex", alignItems: "center", gap: "16px", background: "#222", borderRadius: "6px", padding: "8px 12px", cursor: "pointer", border: "1px solid #2e2e2e", fontFamily: "monospace", fontSize: "0.75rem" },
  rowActive: { borderColor: "#00e676", background: "#00e6760f" },
  rowTime: { color: "#ccc", width: "80px" },
  rowDur: { color: "#888", width: "50px" },
  rowSize: { color: "#888", width: "70px" },
  motionDot: { flex: 1, fontSize: "0.7rem" },
  playLink: { color: "#00e676" },
}
