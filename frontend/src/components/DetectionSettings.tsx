import { useEffect, useRef, useState } from "react"
import { api } from "../api/client"
import type { DetectionSettingSpec } from "../types"

// ============================================================
// Панель рантайм-настроек детекции и логики (Настройки → Детекция и логика).
// Рендерится ГЕНЕРАТИВНО по спеке с бэка (label/desc/min/max/step/unit/group):
// чтобы добавить новый параметр, на фронте ничего не меняется — достаточно
// дописать запись в DETECTION_SETTINGS_SPEC на сервере.
// Параметры применяются на лету (без перезапуска детекции), сохраняются на бэке.
// ============================================================

export function DetectionSettings() {
  const [spec, setSpec] = useState<DetectionSettingSpec[]>([])
  const [values, setValues] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Накопитель изменений + единый дебаунс-таймер: дёргаем слайдер часто, а PUT
  // шлём одним патчем спустя паузу (бэк зажмёт значения в допустимый диапазон).
  const pendingRef = useRef<Record<string, number>>({})
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    api
      .getDetectionSettings()
      .then((r) => {
        if (!alive) return
        setSpec(r.spec || [])
        setValues(r.settings || {})
      })
      .catch(() => {
        if (alive) setError("Не удалось загрузить настройки детекции")
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
      if (timerRef.current) window.clearTimeout(timerRef.current)
    }
  }, [])

  const flush = async () => {
    const patch = pendingRef.current
    pendingRef.current = {}
    if (!Object.keys(patch).length) return
    setSaving(true)
    setError(null)
    try {
      const res = await api.setDetectionSettings(patch)
      if (res.settings) setValues(res.settings) // бэк вернул зажатые значения
    } catch {
      setError("Не удалось сохранить — возвращаю актуальные значения с сервера")
      try {
        const r = await api.getDetectionSettings()
        setValues(r.settings || {})
      } catch {
        /* игнор */
      }
    } finally {
      setSaving(false)
    }
  }

  const commit = (key: string, value: number) => {
    setValues((v) => ({ ...v, [key]: value })) // оптимистично
    pendingRef.current[key] = value
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(flush, 400)
  }

  if (loading) return <div style={styles.hint}>Загрузка…</div>

  // Группировка с сохранением порядка появления групп в спеке.
  const groups: { name: string; items: DetectionSettingSpec[] }[] = []
  for (const s of spec) {
    let g = groups.find((x) => x.name === s.group)
    if (!g) {
      g = { name: s.group, items: [] }
      groups.push(g)
    }
    g.items.push(s)
  }

  const fmt = (v: number, s: DetectionSettingSpec) =>
    s.type === "int" ? String(Math.round(v)) : String(Math.round(v * 100) / 100)

  return (
    <div>
      <div style={styles.desc}>
        Параметры детекции и логики. Применяются <b>на лету</b> — перезапуск не
        нужен — и сохраняются на сервере. Значения автоматически зажимаются в
        допустимый диапазон. ↺ — сброс к значению по умолчанию.
      </div>

      {groups.map((g) => (
        <div key={g.name} style={styles.group}>
          <div style={styles.groupTitle}>{g.name}</div>
          {g.items.map((s) => {
            const val = values[s.key] ?? s.default
            const atDefault = Math.abs(val - s.default) < 1e-9
            const unit = s.unit ? ` ${s.unit}` : ""
            return (
              <div key={s.key} style={styles.row}>
                <div style={styles.rowHead}>
                  <span style={styles.label}>{s.label}</span>
                  <span style={styles.value}>
                    {fmt(val, s)}
                    {unit}
                  </span>
                </div>
                <div style={styles.controls}>
                  <input
                    type="range"
                    min={s.min}
                    max={s.max}
                    step={s.step}
                    value={val}
                    onChange={(e) => commit(s.key, Number(e.target.value))}
                    style={styles.range}
                  />
                  <input
                    type="number"
                    min={s.min}
                    max={s.max}
                    step={s.step}
                    value={val}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      if (!Number.isNaN(n))
                        commit(s.key, Math.min(s.max, Math.max(s.min, n)))
                    }}
                    style={styles.num}
                  />
                  <button
                    type="button"
                    onClick={() => commit(s.key, s.default)}
                    disabled={atDefault}
                    title={`По умолчанию: ${fmt(s.default, s)}${unit}`}
                    style={{ ...styles.reset, opacity: atDefault ? 0.35 : 1 }}
                  >
                    ↺
                  </button>
                </div>
                <div style={styles.itemDesc}>{s.desc}</div>
              </div>
            )
          })}
        </div>
      ))}

      <div style={styles.footer}>
        <span style={{ color: saving ? "#ffb300" : "#00e676" }}>
          {saving ? "Сохранение…" : "Изменения сохраняются автоматически"}
        </span>
      </div>
      {error && <div style={styles.error}>{error}</div>}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  desc: {
    fontSize: "0.78rem",
    color: "#aaa",
    lineHeight: 1.5,
    marginBottom: "16px",
  },
  group: {
    marginBottom: "18px",
  },
  groupTitle: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: "0.68rem",
    letterSpacing: "1.5px",
    color: "#00e676",
    textTransform: "uppercase",
    marginBottom: "10px",
    borderBottom: "1px solid #333",
    paddingBottom: "6px",
  },
  row: {
    background: "#2a2a2a",
    borderRadius: "8px",
    padding: "10px 12px",
    marginBottom: "8px",
  },
  rowHead: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: "10px",
    marginBottom: "8px",
  },
  label: {
    fontSize: "0.84rem",
    color: "#fff",
    fontWeight: 500,
  },
  value: {
    fontFamily: "monospace",
    fontSize: "0.85rem",
    color: "#00e676",
    fontWeight: 700,
    flexShrink: 0,
  },
  controls: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },
  range: {
    flex: 1,
    accentColor: "#00e676",
    cursor: "pointer",
    minWidth: 0,
  },
  num: {
    width: "80px",
    flexShrink: 0,
    background: "#1a1a1a",
    border: "1px solid #444",
    borderRadius: "6px",
    color: "#fff",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    padding: "5px 8px",
  },
  reset: {
    flexShrink: 0,
    width: "30px",
    height: "30px",
    background: "#1a1a1a",
    border: "1px solid #444",
    borderRadius: "6px",
    color: "#bbb",
    cursor: "pointer",
    fontSize: "0.95rem",
    lineHeight: 1,
  },
  itemDesc: {
    fontSize: "0.72rem",
    color: "#888",
    lineHeight: 1.45,
    marginTop: "8px",
  },
  footer: {
    fontSize: "0.72rem",
    fontFamily: "monospace",
    marginTop: "4px",
  },
  hint: {
    fontSize: "0.75rem",
    color: "#888",
    padding: "8px 0",
  },
  error: {
    marginTop: "10px",
    fontSize: "0.72rem",
    color: "#f44336",
  },
}
