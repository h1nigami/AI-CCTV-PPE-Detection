import { useState, useEffect, useCallback, useMemo } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"
import type { RecordingSegment } from "../types"

// ============================================================
// Архив NVR: выбор камеры + даты, таймлайн сегментов за сутки,
// плеер выбранного сегмента. Источник — /api/recordings.
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

export default function ArchivePage() {
  const { cameras } = useCamerasContext()
  const camList = cameras.map((c) => c.name)

  const [camId, setCamId] = useState("")
  const [date, setDate] = useState(todayStr())
  const [segments, setSegments] = useState<RecordingSegment[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<RecordingSegment | null>(null)

  // Камера по умолчанию — первая доступная.
  useEffect(() => {
    if (!camId && camList.length > 0) setCamId(camList[0])
  }, [camList, camId])

  const dayStart = useMemo(() => dayStartUnix(date), [date])
  const dayEnd = dayStart + DAY_SEC

  const fetchSegments = useCallback(async () => {
    if (!camId) return
    try {
      setLoading(true)
      const data = await api.getRecordings({
        camId, from: dayStart, to: dayEnd, limit: 1000,
      })
      setSegments(data.recordings)
    } catch {
      setSegments([])
    } finally {
      setLoading(false)
    }
  }, [camId, dayStart, dayEnd])

  useEffect(() => {
    fetchSegments()
  }, [fetchSegments])

  const totalDuration = segments.reduce((s, r) => s + r.duration, 0)
  const motionCount = segments.filter((r) => r.hasMotion).length

  return (
    <div style={styles.page}>
      {/* ── Header ── */}
      <div style={styles.header}>
        <h1 style={styles.title}>АРХИВ ЗАПИСЕЙ</h1>
        <span style={styles.count}>
          {segments.length} сегм. · {(totalDuration / 60).toFixed(0)} мин · {motionCount} с движением
        </span>
      </div>

      {/* ── Controls ── */}
      <div style={styles.controls}>
        <select style={styles.select} value={camId} onChange={(e) => { setCamId(e.target.value); setSelected(null) }}>
          {camList.length === 0 && <option value="">Нет камер</option>}
          {camList.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          type="date"
          style={styles.select}
          value={date}
          max={todayStr()}
          onChange={(e) => { setDate(e.target.value); setSelected(null) }}
        />
        <button style={styles.refreshBtn} onClick={fetchSegments}>Обновить</button>
      </div>

      {/* ── Player ── */}
      {selected && (
        <div style={styles.playerWrap}>
          <video key={selected.id} src={selected.playUrl} style={styles.video} controls autoPlay />
          <div style={styles.playerMeta}>
            <span>{fmtClock(selected.startTime)} – {fmtClock(selected.endTime)}</span>
            <span>{selected.duration.toFixed(0)} с</span>
            <span>{fmtSize(selected.sizeBytes)}</span>
            <span style={{ color: selected.hasMotion ? "#69f0ae" : "#888" }}>
              {selected.hasMotion ? "● движение" : "○ статика"}
            </span>
          </div>
        </div>
      )}

      {/* ── Timeline (24h) ── */}
      <div style={styles.timelineWrap}>
        <div style={styles.timelineBar}>
          {segments.map((r) => {
            const left = Math.max(0, ((r.startTime - dayStart) / DAY_SEC) * 100)
            const width = Math.max(0.25, (r.duration / DAY_SEC) * 100)
            const isSel = selected?.id === r.id
            return (
              <div
                key={r.id}
                title={`${fmtClock(r.startTime)} (${r.duration.toFixed(0)}с)`}
                onClick={() => setSelected(r)}
                style={{
                  ...styles.segment,
                  left: `${left}%`,
                  width: `${width}%`,
                  background: r.hasMotion ? "#00c853" : "#555",
                  outline: isSel ? "2px solid #00e676" : "none",
                  zIndex: isSel ? 2 : 1,
                }}
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
            style={{ ...styles.row, ...(selected?.id === r.id ? styles.rowActive : {}) }}
            onClick={() => setSelected(r)}
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
  playerWrap: { padding: "12px 24px", borderBottom: "1px solid #333" },
  video: { width: "100%", maxHeight: "45vh", background: "#000", borderRadius: "8px", display: "block" },
  playerMeta: { display: "flex", flexWrap: "wrap" as const, gap: "16px", padding: "8px 2px 0", fontFamily: "monospace", fontSize: "0.72rem", color: "#aaa" },
  timelineWrap: { padding: "16px 24px 8px", borderBottom: "1px solid #333" },
  timelineBar: { position: "relative" as const, height: "28px", background: "#111", borderRadius: "4px", overflow: "hidden", border: "1px solid #2a2a2a" },
  segment: { position: "absolute" as const, top: "2px", bottom: "2px", borderRadius: "2px", cursor: "pointer" },
  hourTicks: { position: "relative" as const, height: "16px", marginTop: "2px" },
  tick: { position: "absolute" as const, transform: "translateX(-50%)", fontFamily: "monospace", fontSize: "0.6rem", color: "#666" },
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
