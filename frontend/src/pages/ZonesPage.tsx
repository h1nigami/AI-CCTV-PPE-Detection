import { useState, useEffect, useCallback, useRef } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"
import type { Zone, ZoneType } from "../types"

// ============================================================
// Редактор зон: рисование полигонов поверх кадра камеры.
// Координаты вершин — нормализованные [0..1] (как хранит бэкенд).
// Клик по кадру добавляет точку в активную зону, вершины тянутся мышью.
// ============================================================

const TYPE_OPTS: { value: ZoneType; label: string; color: string }[] = [
  { value: "danger", label: "Опасная", color: "#ff5252" },
  { value: "restricted", label: "Ограниченная", color: "#ff9100" },
  { value: "mask", label: "Маска (исключить)", color: "#9e9e9e" },
]
const PPE_OPTS: { key: string; label: string }[] = [
  { key: "helmet", label: "Каска" },
  { key: "mask", label: "Маска" },
  { key: "vest", label: "Жилет" },
]

function typeColor(t: ZoneType): string {
  return TYPE_OPTS.find((o) => o.value === t)?.color ?? "#ff5252"
}

export default function ZonesPage() {
  const { cameras } = useCamerasContext()
  const camList = cameras.map((c) => c.name)

  const [camId, setCamId] = useState("")
  const [zones, setZones] = useState<Zone[]>([])
  const [activeIdx, setActiveIdx] = useState(-1)
  const [frameUrl, setFrameUrl] = useState("")
  const [status, setStatus] = useState("")
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<{ zi: number; pi: number } | null>(null)

  useEffect(() => { if (!camId && camList.length > 0) setCamId(camList[0]) }, [camList, camId])

  const refreshFrame = useCallback(() => {
    if (camId) setFrameUrl(api.getFrameUrl(camId))
  }, [camId])

  const loadZones = useCallback(async () => {
    if (!camId) return
    try {
      const data = await api.getZones(camId)
      setZones(data.zones)
      setActiveIdx(-1)
      setStatus("")
    } catch { setZones([]) }
  }, [camId])

  useEffect(() => { loadZones(); refreshFrame() }, [loadZones, refreshFrame])

  const active = activeIdx >= 0 ? zones[activeIdx] : null

  const patchActive = (patch: Partial<Zone>) => {
    if (activeIdx < 0) return
    setZones((zs) => zs.map((z, i) => (i === activeIdx ? { ...z, ...patch } : z)))
  }

  const addZone = () => {
    const z: Zone = { name: `Зона ${zones.length + 1}`, type: "danger", points: [], require_ppe: [] }
    setZones((zs) => [...zs, z])
    setActiveIdx(zones.length)
    setStatus("Кликайте по кадру, чтобы поставить вершины (минимум 3)")
  }

  const deleteZone = (idx: number) => {
    setZones((zs) => zs.filter((_, i) => i !== idx))
    setActiveIdx(-1)
  }

  // — координаты клика → нормализованные —
  const toNorm = (clientX: number, clientY: number): [number, number] => {
    const r = svgRef.current!.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (clientX - r.left) / r.width))
    const y = Math.min(1, Math.max(0, (clientY - r.top) / r.height))
    return [Number(x.toFixed(4)), Number(y.toFixed(4))]
  }

  const onSvgClick = (e: React.MouseEvent) => {
    if (activeIdx < 0 || dragRef.current) return
    const p = toNorm(e.clientX, e.clientY)
    setZones((zs) => zs.map((z, i) => (i === activeIdx ? { ...z, points: [...z.points, p] } : z)))
  }

  const onVertexDown = (e: React.PointerEvent, zi: number, pi: number) => {
    e.stopPropagation()
    dragRef.current = { zi, pi }
    setActiveIdx(zi)
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
  }
  const onSvgMove = (e: React.PointerEvent) => {
    const d = dragRef.current
    if (!d) return
    const p = toNorm(e.clientX, e.clientY)
    setZones((zs) => zs.map((z, i) =>
      i === d.zi ? { ...z, points: z.points.map((pt, j) => (j === d.pi ? p : pt)) } : z))
  }
  const onSvgUp = () => { dragRef.current = null }

  const removeLastPoint = () => {
    if (activeIdx < 0) return
    setZones((zs) => zs.map((z, i) => (i === activeIdx ? { ...z, points: z.points.slice(0, -1) } : z)))
  }

  const save = async () => {
    const bad = zones.find((z) => z.points.length < 3)
    if (bad) { setStatus(`Зона «${bad.name}» требует ≥3 точек`); return }
    try {
      await api.saveZones(camId, zones)
      setStatus("Сохранено ✓")
      loadZones()
    } catch (e) {
      setStatus(`Ошибка: ${(e as Error).message}`)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>РЕДАКТОР ЗОН</h1>
        <span style={styles.count}>{zones.length} зон</span>
      </div>

      <div style={styles.controls}>
        <select style={styles.select} value={camId} onChange={(e) => setCamId(e.target.value)}>
          {camList.length === 0 && <option value="">Нет камер</option>}
          {camList.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button style={styles.btn} onClick={refreshFrame}>Обновить кадр</button>
        <button style={styles.btnPrimary} onClick={addZone}>+ Новая зона</button>
        <button style={styles.btn} onClick={removeLastPoint} disabled={activeIdx < 0}>Удалить точку</button>
        <button style={styles.btnSave} onClick={save} disabled={!camId || zones.length === 0}>Сохранить</button>
        {status && <span style={styles.status}>{status}</span>}
      </div>

      <div style={styles.body}>
        {/* ── Холст ── */}
        <div style={styles.canvasWrap}>
          <div style={styles.canvasInner}>
            {frameUrl
              ? <img src={frameUrl} alt="" style={styles.frame} onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden" }} />
              : <div style={styles.noFrame}>Нет кадра (запустите детекцию)</div>}
            <svg
              ref={svgRef}
              viewBox="0 0 1 1"
              preserveAspectRatio="none"
              style={styles.svg}
              onClick={onSvgClick}
              onPointerMove={onSvgMove}
              onPointerUp={onSvgUp}
              onPointerLeave={onSvgUp}
            >
              {zones.map((z, zi) => {
                const col = typeColor(z.type)
                const isActive = zi === activeIdx
                const pointsStr = z.points.map((p) => `${p[0]},${p[1]}`).join(" ")
                return (
                  <g key={z.id || zi}>
                    {z.points.length >= 2 && (
                      <polygon
                        points={pointsStr}
                        fill={col} fillOpacity={isActive ? 0.22 : 0.12}
                        stroke={col} strokeWidth={isActive ? 0.004 : 0.0025}
                        onClick={(e) => { e.stopPropagation(); setActiveIdx(zi) }}
                        style={{ cursor: "pointer" }}
                      />
                    )}
                    {isActive && z.points.map((p, pi) => (
                      <circle
                        key={pi} cx={p[0]} cy={p[1]} r={0.008}
                        fill="#fff" stroke={col} strokeWidth={0.003}
                        style={{ cursor: "grab" }}
                        onPointerDown={(e) => onVertexDown(e, zi, pi)}
                      />
                    ))}
                  </g>
                )
              })}
            </svg>
          </div>
        </div>

        {/* ── Боковая панель ── */}
        <div style={styles.side}>
          <div style={styles.sideTitle}>Зоны камеры</div>
          {zones.length === 0 && <div style={styles.hint}>Нажмите «+ Новая зона» и поставьте точки на кадре.</div>}
          {zones.map((z, zi) => (
            <div
              key={z.id || zi}
              style={{ ...styles.zoneRow, ...(zi === activeIdx ? styles.zoneRowActive : {}) }}
              onClick={() => setActiveIdx(zi)}
            >
              <i style={{ ...styles.swatch, background: typeColor(z.type) }} />
              <span style={styles.zoneName}>{z.name}</span>
              <span style={styles.zonePts}>{z.points.length} тчк</span>
              <button style={styles.del} onClick={(e) => { e.stopPropagation(); deleteZone(zi) }}>✕</button>
            </div>
          ))}

          {active && (
            <div style={styles.editor}>
              <div style={styles.sideTitle}>Свойства зоны</div>
              <label style={styles.field}>
                <span>Название</span>
                <input style={styles.input} value={active.name}
                  onChange={(e) => patchActive({ name: e.target.value })} />
              </label>
              <label style={styles.field}>
                <span>Тип</span>
                <select style={styles.input} value={active.type}
                  onChange={(e) => patchActive({ type: e.target.value as ZoneType })}>
                  {TYPE_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              {active.type !== "mask" && (
                <div style={styles.field}>
                  <span>Требуемые СИЗ</span>
                  <div style={styles.ppeRow}>
                    {PPE_OPTS.map((o) => {
                      const on = active.require_ppe.includes(o.key)
                      return (
                        <button key={o.key}
                          style={{ ...styles.ppeBtn, ...(on ? styles.ppeOn : {}) }}
                          onClick={() => patchActive({
                            require_ppe: on
                              ? active.require_ppe.filter((k) => k !== o.key)
                              : [...active.require_ppe, o.key],
                          })}>
                          {o.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
              <div style={styles.hint}>
                Кликайте по кадру — добавляются вершины. Точки можно перетаскивать.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: "flex", flexDirection: "column", flex: 1, background: "#1a1a1a", color: "#eee", minHeight: 0, overflow: "hidden" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 24px", borderBottom: "1px solid #333" },
  title: { fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: "1rem", letterSpacing: "3px", color: "#00e676", textTransform: "uppercase", margin: 0 },
  count: { fontFamily: "monospace", fontSize: "0.7rem", color: "#888" },
  controls: { display: "flex", alignItems: "center", gap: "10px", padding: "10px 24px", borderBottom: "1px solid #333", flexWrap: "wrap" as const },
  select: { background: "#2a2a2a", color: "#eee", border: "1px solid #444", borderRadius: "6px", padding: "6px 12px", fontSize: "0.75rem", fontFamily: "monospace", outline: "none", cursor: "pointer" },
  btn: { background: "transparent", color: "#aaa", border: "1px solid #444", borderRadius: "6px", padding: "6px 12px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  btnPrimary: { background: "#00e67622", color: "#00e676", border: "1px solid #00e676", borderRadius: "6px", padding: "6px 12px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  btnSave: { background: "#00e676", color: "#062b16", border: "none", borderRadius: "6px", padding: "6px 16px", fontSize: "0.7rem", fontWeight: 700, fontFamily: "monospace", cursor: "pointer" },
  status: { fontFamily: "monospace", fontSize: "0.72rem", color: "#ffd54f" },
  body: { flex: 1, display: "flex", minHeight: 0 },
  canvasWrap: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "16px", minWidth: 0, background: "#111" },
  canvasInner: { position: "relative" as const, width: "100%", maxWidth: "960px", aspectRatio: "16 / 9", background: "#000", borderRadius: "8px", overflow: "hidden" },
  frame: { position: "absolute" as const, inset: 0, width: "100%", height: "100%", objectFit: "fill" as const, display: "block" },
  noFrame: { position: "absolute" as const, inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#555", fontFamily: "monospace", fontSize: "0.8rem" },
  svg: { position: "absolute" as const, inset: 0, width: "100%", height: "100%", touchAction: "none" },
  side: { width: "300px", borderLeft: "1px solid #333", padding: "12px 16px", overflowY: "auto" as const, display: "flex", flexDirection: "column", gap: "8px" },
  sideTitle: { fontFamily: "monospace", fontSize: "0.7rem", color: "#888", textTransform: "uppercase", letterSpacing: "1px", marginTop: "4px" },
  hint: { fontFamily: "monospace", fontSize: "0.68rem", color: "#666", lineHeight: 1.6 },
  zoneRow: { display: "flex", alignItems: "center", gap: "8px", background: "#222", border: "1px solid #2e2e2e", borderRadius: "6px", padding: "6px 10px", cursor: "pointer" },
  zoneRowActive: { borderColor: "#00e676", background: "#00e6760f" },
  swatch: { width: "12px", height: "12px", borderRadius: "3px", flexShrink: 0 },
  zoneName: { flex: 1, fontFamily: "'Inter', sans-serif", fontSize: "0.8rem", color: "#ddd", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const },
  zonePts: { fontFamily: "monospace", fontSize: "0.65rem", color: "#777" },
  del: { background: "transparent", border: "none", color: "#ff5252", cursor: "pointer", fontSize: "0.85rem" },
  editor: { borderTop: "1px solid #333", marginTop: "8px", paddingTop: "8px", display: "flex", flexDirection: "column", gap: "10px" },
  field: { display: "flex", flexDirection: "column", gap: "4px", fontFamily: "monospace", fontSize: "0.7rem", color: "#999" },
  input: { background: "#2a2a2a", color: "#eee", border: "1px solid #444", borderRadius: "6px", padding: "6px 10px", fontSize: "0.78rem", fontFamily: "monospace", outline: "none" },
  ppeRow: { display: "flex", gap: "6px" },
  ppeBtn: { flex: 1, background: "transparent", color: "#888", border: "1px solid #444", borderRadius: "6px", padding: "5px 0", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  ppeOn: { background: "#00e67622", color: "#00e676", borderColor: "#00e676" },
}
