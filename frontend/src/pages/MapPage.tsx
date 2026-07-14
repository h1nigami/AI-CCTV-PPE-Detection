import { useState, useEffect, useCallback, useRef } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"
import type { MovementTrack, CameraMappingPoint } from "../types"

// ============================================================
// Карта помещения: кросс-камерный стич траекторий.
// - Живой режим: путь каждого человека (по global_id) рисуется ОДНОЙ линией
//   через все камеры (точки ног спроецированы гомографией в координаты карты).
// - Калибровка: на камеру ставятся ≥4 пары «точка в кадре ↔ точка на карте».
// Координаты всюду нормализованные [0..1].
// ============================================================

function personColor(gid: number): string {
  return `hsl(${(gid * 137) % 360}, 70%, 55%)`
}

function Grid() {
  const lines = [0.25, 0.5, 0.75]
  return (
    <>
      <rect x={0} y={0} width={1} height={1} fill="none" stroke="#333" strokeWidth={0.004} />
      {lines.map((p) => (
        <g key={p}>
          <line x1={p} y1={0} x2={p} y2={1} stroke="#2a2a2a" strokeWidth={0.002} />
          <line x1={0} y1={p} x2={1} y2={p} stroke="#2a2a2a" strokeWidth={0.002} />
        </g>
      ))}
    </>
  )
}

export default function MapPage() {
  const { cameras, isRunning } = useCamerasContext()
  const camList = cameras.map((c) => c.name)
  const [camId, setCamId] = useState("")
  const [mode, setMode] = useState<"live" | "calibrate">("live")

  // План здания (подложка). planVersion — cache-bust после загрузки/удаления;
  // planAspect берём из натуральных размеров плана, чтобы панель карты имела те
  // же пропорции и в калибровке, и в живом виде (нормализованные координаты
  // совпадали). hasPlan=false → рисуем сетку.
  const [planVersion, setPlanVersion] = useState(0)
  const [hasPlan, setHasPlan] = useState(false)
  const [planAspect, setPlanAspect] = useState(16 / 9)
  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      setHasPlan(true)
      if (img.naturalHeight > 0) setPlanAspect(img.naturalWidth / img.naturalHeight)
    }
    img.onerror = () => { setHasPlan(false); setPlanAspect(16 / 9) }
    img.src = api.getFloorplanUrl(planVersion)
  }, [planVersion])
  const onPlanChange = () => setPlanVersion((v) => v + 1)

  useEffect(() => { if (!camId && camList.length > 0) setCamId(camList[0]) }, [camList, camId])

  const plan = { hasPlan, planVersion, planAspect }
  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>КАРТА ПЕРЕМЕЩЕНИЙ</h1>
        <div style={styles.modeSwitch}>
          <button style={mode === "live" ? styles.modeOn : styles.modeOff} onClick={() => setMode("live")}>Живая карта</button>
          <button style={mode === "calibrate" ? styles.modeOn : styles.modeOff} onClick={() => setMode("calibrate")}>Калибровка</button>
        </div>
      </div>
      {mode === "live"
        ? <LiveMap isRunning={isRunning} {...plan} />
        : <Calibrator camId={camId} setCamId={setCamId} camList={camList} {...plan} onPlanChange={onPlanChange} />}
    </div>
  )
}

// Подложка плана здания в панели карты (за сеткой/треками). objectFit:fill +
// aspectRatio панели = пропорции плана → без искажений и с совпадением координат.
function FloorplanBg({ hasPlan, planVersion }: { hasPlan: boolean; planVersion: number }) {
  if (!hasPlan) return null
  return <img src={api.getFloorplanUrl(planVersion)} alt="" style={styles.planImg} />
}

interface PlanProps { hasPlan: boolean; planVersion: number; planAspect: number }

// ── Живая карта: сшитые траектории ──────────────────────────────────────────
function LiveMap({ isRunning, hasPlan, planVersion, planAspect }: { isRunning: boolean } & PlanProps) {
  const [tracks, setTracks] = useState<MovementTrack[]>([])
  useEffect(() => {
    if (!isRunning) { setTracks([]); return }
    let alive = true
    const fetchTracks = async () => {
      try {
        const data = await api.getMovementTracks()
        if (alive) setTracks(data.tracks)
      } catch { /* ignore */ }
    }
    fetchTracks()
    const id = setInterval(fetchTracks, 1000)
    return () => { alive = false; clearInterval(id) }
  }, [isRunning])

  return (
    <div style={styles.body}>
      <div style={styles.canvasWrap}>
        <div style={{ ...styles.mapInner, aspectRatio: planAspect }}>
          <FloorplanBg hasPlan={hasPlan} planVersion={planVersion} />
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" style={styles.svg}>
            {!hasPlan && <Grid />}
            {tracks.map((t) => {
              const col = personColor(t.global_id)
              const pointsStr = t.points.map((p) => `${p.x},${p.y}`).join(" ")
              const last = t.points[t.points.length - 1]
              return (
                <g key={t.global_id}>
                  {t.points.length >= 2 && (
                    <polyline points={pointsStr} fill="none" stroke={col}
                      strokeWidth={0.005} strokeLinejoin="round" strokeLinecap="round" opacity={0.85} />
                  )}
                  {t.points.map((p, i) => (
                    <circle key={i} cx={p.x} cy={p.y} r={0.004} fill={col} opacity={0.5} />
                  ))}
                  {last && <circle cx={last.x} cy={last.y} r={0.012} fill={col} stroke="#111" strokeWidth={0.003} />}
                </g>
              )
            })}
          </svg>
          {/* Подписи имён поверх SVG (текст в нормализованном SVG искажается) */}
          {tracks.map((t) => {
            const last = t.points[t.points.length - 1]
            if (!last) return null
            return (
              <div key={t.global_id} style={{
                position: "absolute", left: `${last.x * 100}%`, top: `${last.y * 100}%`,
                transform: "translate(8px, -50%)", color: personColor(t.global_id),
                fontFamily: "monospace", fontSize: "0.7rem", fontWeight: 700, whiteSpace: "nowrap",
                textShadow: "0 1px 3px #000", pointerEvents: "none",
              }}>
                {t.name || `#${t.global_id}`} · {t.last_cam}
              </div>
            )
          })}
        </div>
      </div>
      <div style={styles.side}>
        <div style={styles.sideTitle}>Люди на карте</div>
        {!isRunning && <div style={styles.hint}>Запустите детекцию, чтобы видеть перемещения.</div>}
        {isRunning && tracks.length === 0 && (
          <div style={styles.hint}>Нет данных. Нужна калибровка камер (вкладка «Калибровка») и опознанные лица.</div>
        )}
        {tracks.map((t) => (
          <div key={t.global_id} style={styles.personRow}>
            <i style={{ ...styles.swatch, background: personColor(t.global_id) }} />
            <span style={styles.personName}>{t.name || `#${t.global_id}`}</span>
            <span style={styles.personCam}>{t.last_cam}</span>
            <span style={styles.personPts}>{t.points.length} тчк</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Калибровка: 4+ пары «кадр ↔ карта» ──────────────────────────────────────
function Calibrator({ camId, setCamId, camList, hasPlan, planVersion, planAspect, onPlanChange }:
  { camId: string; setCamId: (v: string) => void; camList: string[]; onPlanChange: () => void } & PlanProps) {
  const [pairs, setPairs] = useState<CameraMappingPoint[]>([])
  const [frameUrl, setFrameUrl] = useState("")
  const [status, setStatus] = useState("")
  const imgSvg = useRef<SVGSVGElement>(null)
  const mapSvg = useRef<SVGSVGElement>(null)
  const planInput = useRef<HTMLInputElement>(null)
  const dragRef = useRef<{ which: "image" | "map"; idx: number } | null>(null)

  const onPlanFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""  // позволить повторно выбрать тот же файл
    if (!file) return
    try {
      await api.uploadFloorplan(file)
      setStatus("План загружен ✓")
      onPlanChange()
    } catch (err) { setStatus(`Ошибка загрузки: ${(err as Error).message}`) }
  }
  const removePlan = async () => {
    try { await api.deleteFloorplan(); setStatus("План удалён"); onPlanChange() }
    catch (err) { setStatus(`Ошибка: ${(err as Error).message}`) }
  }

  const refreshFrame = useCallback(() => { if (camId) setFrameUrl(api.getFrameUrl(camId)) }, [camId])
  const loadMapping = useCallback(async () => {
    if (!camId) return
    try {
      const data = await api.getCameraMapping(camId)
      setPairs(data.map_points || [])
      setStatus("")
    } catch { setPairs([]) }
  }, [camId])
  useEffect(() => { loadMapping(); refreshFrame() }, [loadMapping, refreshFrame])

  const toNorm = (ref: React.RefObject<SVGSVGElement | null>, cx: number, cy: number): [number, number] => {
    const r = ref.current!.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (cx - r.left) / r.width))
    const y = Math.min(1, Math.max(0, (cy - r.top) / r.height))
    return [Number(x.toFixed(4)), Number(y.toFixed(4))]
  }

  const addPair = () => {
    const n = pairs.length
    // Слегка разносим точки, чтобы не ложились друг на друга.
    const off = 0.1 + (n % 4) * 0.2
    setPairs((p) => [...p, { image: [off, off], map: [off, off] }])
  }
  const removeLast = () => setPairs((p) => p.slice(0, -1))

  const onDown = (e: React.PointerEvent, which: "image" | "map", idx: number) => {
    e.stopPropagation()
    dragRef.current = { which, idx }
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
  }
  const onMove = (ref: React.RefObject<SVGSVGElement | null>) => (e: React.PointerEvent) => {
    const d = dragRef.current
    if (!d || d.which !== whichOf(ref)) return
    const pt = toNorm(ref, e.clientX, e.clientY)
    setPairs((ps) => ps.map((p, i) => (i === d.idx ? { ...p, [d.which]: pt } : p)))
  }
  const whichOf = (ref: React.RefObject<SVGSVGElement | null>): "image" | "map" =>
    ref === imgSvg ? "image" : "map"
  const onUp = () => { dragRef.current = null }

  const save = async () => {
    if (pairs.length !== 0 && pairs.length < 4) { setStatus("Нужно ≥4 пар точек (или ноль, чтобы убрать калибровку)"); return }
    try {
      await api.saveCameraMapping(camId, pairs)
      setStatus("Сохранено ✓")
    } catch (e) { setStatus(`Ошибка: ${(e as Error).message}`) }
  }

  const markers = (which: "image" | "map", ref: React.RefObject<SVGSVGElement | null>) =>
    pairs.map((p, i) => {
      const [x, y] = p[which]
      return (
        <g key={i}>
          <circle cx={x} cy={y} r={0.02} fill={personColor(i + 1)} stroke="#fff" strokeWidth={0.004}
            style={{ cursor: "grab" }} onPointerDown={(e) => onDown(e, which, i)} />
          <text x={x} y={y} dy={0.007} textAnchor="middle" fill="#111" fontSize={0.03} fontWeight={700}
            style={{ pointerEvents: "none" }}>{i + 1}</text>
        </g>
      )
    })

  return (
    <div style={styles.body}>
      <div style={styles.calibWrap}>
        {/* Кадр камеры */}
        <div style={styles.calibCol}>
          <div style={styles.calibLabel}>Кадр камеры — точки на полу</div>
          <div style={styles.mapInner}>
            {frameUrl
              ? <img src={frameUrl} alt="" style={styles.frame} onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden" }} />
              : <div style={styles.noFrame}>Нет кадра (запустите детекцию)</div>}
            <svg ref={imgSvg} viewBox="0 0 1 1" preserveAspectRatio="none" style={styles.svg}
              onPointerMove={onMove(imgSvg)} onPointerUp={onUp} onPointerLeave={onUp}>
              {markers("image", imgSvg)}
            </svg>
          </div>
        </div>
        {/* Карта */}
        <div style={styles.calibCol}>
          <div style={styles.calibLabel}>План помещения — те же точки</div>
          <div style={{ ...styles.mapInner, aspectRatio: planAspect }}>
            <FloorplanBg hasPlan={hasPlan} planVersion={planVersion} />
            <svg ref={mapSvg} viewBox="0 0 1 1" preserveAspectRatio="none" style={styles.svg}
              onPointerMove={onMove(mapSvg)} onPointerUp={onUp} onPointerLeave={onUp}>
              {!hasPlan && <Grid />}
              {markers("map", mapSvg)}
            </svg>
          </div>
        </div>
      </div>
      <div style={styles.side}>
        <div style={styles.controlsCol}>
          <select style={styles.select} value={camId} onChange={(e) => setCamId(e.target.value)}>
            {camList.length === 0 && <option value="">Нет камер</option>}
            {camList.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button style={styles.btn} onClick={refreshFrame}>Обновить кадр</button>
          <button style={styles.btnPrimary} onClick={addPair}>+ Пара точек</button>
          <button style={styles.btn} onClick={removeLast} disabled={pairs.length === 0}>Удалить последнюю</button>
          <button style={styles.btnSave} onClick={save} disabled={!camId}>Сохранить</button>
          {status && <span style={styles.status}>{status}</span>}
        </div>
        <div style={styles.sideTitle}>План здания</div>
        <div style={styles.controlsCol}>
          <input ref={planInput} type="file" accept="image/png,image/jpeg,image/webp"
            onChange={onPlanFile} style={{ display: "none" }} />
          <button style={styles.btnPrimary} onClick={() => planInput.current?.click()}>
            {hasPlan ? "Заменить план (PNG/JPG)" : "Загрузить план (PNG/JPG)"}
          </button>
          {hasPlan && <button style={styles.btn} onClick={removePlan}>Удалить план</button>}
        </div>
        <div style={styles.hint}>
          Загрузите план здания — он станет подложкой карты. Затем поставьте ≥4
          пар: точку на полу в кадре и ТУ ЖЕ точку на плане. По ним строится
          проекция кадр→карта, и траектории с разных камер сшиваются в одну
          линию. Номера точек должны соответствовать друг другу.
        </div>
        <div style={styles.sideTitle}>Пары точек: {pairs.length}</div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: "flex", flexDirection: "column", flex: 1, background: "#1a1a1a", color: "#eee", minHeight: 0, overflow: "hidden" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 24px", borderBottom: "1px solid #333" },
  title: { fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: "1rem", letterSpacing: "3px", color: "#00e676", textTransform: "uppercase", margin: 0 },
  modeSwitch: { display: "flex", gap: "6px" },
  modeOn: { background: "#00e67622", color: "#00e676", border: "1px solid #00e676", borderRadius: "6px", padding: "6px 14px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  modeOff: { background: "transparent", color: "#888", border: "1px solid #444", borderRadius: "6px", padding: "6px 14px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  body: { flex: 1, display: "flex", minHeight: 0 },
  canvasWrap: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "16px", minWidth: 0, background: "#111" },
  calibWrap: { flex: 1, display: "flex", gap: "16px", padding: "16px", minWidth: 0, background: "#111", flexWrap: "wrap" as const },
  calibCol: { flex: 1, minWidth: "280px", display: "flex", flexDirection: "column", gap: "6px" },
  calibLabel: { fontFamily: "monospace", fontSize: "0.68rem", color: "#888", textTransform: "uppercase", letterSpacing: "1px" },
  mapInner: { position: "relative" as const, width: "100%", maxWidth: "760px", aspectRatio: "16 / 9", background: "#0a0a0a", borderRadius: "8px", overflow: "hidden", border: "1px solid #2a2a2a" },
  frame: { position: "absolute" as const, inset: 0, width: "100%", height: "100%", objectFit: "fill" as const, display: "block" },
  planImg: { position: "absolute" as const, inset: 0, width: "100%", height: "100%", objectFit: "fill" as const, display: "block", opacity: 0.75 },
  noFrame: { position: "absolute" as const, inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#555", fontFamily: "monospace", fontSize: "0.8rem" },
  svg: { position: "absolute" as const, inset: 0, width: "100%", height: "100%", touchAction: "none" },
  side: { width: "300px", borderLeft: "1px solid #333", padding: "12px 16px", overflowY: "auto" as const, display: "flex", flexDirection: "column", gap: "10px" },
  controlsCol: { display: "flex", flexDirection: "column", gap: "8px" },
  sideTitle: { fontFamily: "monospace", fontSize: "0.7rem", color: "#888", textTransform: "uppercase", letterSpacing: "1px", marginTop: "4px" },
  hint: { fontFamily: "monospace", fontSize: "0.68rem", color: "#666", lineHeight: 1.6 },
  select: { background: "#2a2a2a", color: "#eee", border: "1px solid #444", borderRadius: "6px", padding: "6px 12px", fontSize: "0.75rem", fontFamily: "monospace", outline: "none", cursor: "pointer" },
  btn: { background: "transparent", color: "#aaa", border: "1px solid #444", borderRadius: "6px", padding: "6px 12px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  btnPrimary: { background: "#00e67622", color: "#00e676", border: "1px solid #00e676", borderRadius: "6px", padding: "6px 12px", fontSize: "0.7rem", fontFamily: "monospace", cursor: "pointer" },
  btnSave: { background: "#00e676", color: "#062b16", border: "none", borderRadius: "6px", padding: "6px 16px", fontSize: "0.7rem", fontWeight: 700, fontFamily: "monospace", cursor: "pointer" },
  status: { fontFamily: "monospace", fontSize: "0.72rem", color: "#ffd54f" },
  personRow: { display: "flex", alignItems: "center", gap: "8px", background: "#222", border: "1px solid #2e2e2e", borderRadius: "6px", padding: "6px 10px" },
  swatch: { width: "12px", height: "12px", borderRadius: "50%", flexShrink: 0 },
  personName: { flex: 1, fontFamily: "'Inter', sans-serif", fontSize: "0.8rem", color: "#ddd", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const },
  personCam: { fontFamily: "monospace", fontSize: "0.62rem", color: "#00e676" },
  personPts: { fontFamily: "monospace", fontSize: "0.62rem", color: "#777" },
}
