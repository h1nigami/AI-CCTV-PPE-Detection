import { useState, useEffect } from "react"
import { api } from "../api/client"

// ============================================================
// Настройка обязательных СИЗ для выдачи пропуска по жесту «ОК».
// Жест «ОК» допускает человека, только если у него есть ВСЕ отмеченные
// здесь средства защиты. Пустой набор → пропуск выдаётся без требования СИЗ.
// Соответствует PPE_REQUIRED_DEFAULT на бэке (персистится в ppe_required.json).
// ============================================================

type PpeKey = "helmet" | "mask" | "vest"

const ITEMS: { key: PpeKey; icon: string; label: string }[] = [
  { key: "helmet", icon: "⛑️", label: "Каска" },
  { key: "mask", icon: "😷", label: "Маска" },
  { key: "vest", icon: "🦺", label: "Жилет" },
]

export function PpeRequiredSettings() {
  const [required, setRequired] = useState<PpeKey[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .getPpeRequired()
      .then((r) => {
        if (alive) setRequired((r.required || []) as PpeKey[])
      })
      .catch(() => {
        if (alive) setError("Не удалось загрузить настройку")
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const toggle = async (key: PpeKey) => {
    const next = required.includes(key)
      ? required.filter((k) => k !== key)
      : [...required, key]
    // Сохраняем порядок helmet/mask/vest для стабильности.
    const ordered = ITEMS.map((i) => i.key).filter((k) => next.includes(k))
    setRequired(ordered)
    setSaving(true)
    setError(null)
    try {
      const res = await api.setPpeRequired(ordered)
      setRequired((res.required || []) as PpeKey[])
    } catch {
      setError("Не удалось сохранить — изменения не применены")
      // Откатываем оптимистичное изменение.
      try {
        const r = await api.getPpeRequired()
        setRequired((r.required || []) as PpeKey[])
      } catch {
        /* игнор */
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div style={styles.hint}>Загрузка…</div>
  }

  return (
    <div>
      <div style={styles.desc}>
        Жест «ОК» выдаёт пропуск, только если у человека есть все отмеченные СИЗ.
        Если ничего не отмечено — пропуск выдаётся без требования средств защиты.
      </div>
      <div style={styles.list}>
        {ITEMS.map(({ key, icon, label }) => {
          const checked = required.includes(key)
          return (
            <label key={key} style={styles.row}>
              <input
                type="checkbox"
                checked={checked}
                disabled={saving}
                onChange={() => toggle(key)}
                style={styles.checkbox}
              />
              <span style={styles.icon}>{icon}</span>
              <span style={styles.label}>{label}</span>
              <span style={{ ...styles.state, color: checked ? "#00e676" : "#666" }}>
                {checked ? "обязателен" : "не требуется"}
              </span>
            </label>
          )
        })}
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
    marginBottom: "14px",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "10px 12px",
    background: "#2a2a2a",
    borderRadius: "8px",
    cursor: "pointer",
  },
  checkbox: {
    width: "18px",
    height: "18px",
    accentColor: "#00e676",
    cursor: "pointer",
    flexShrink: 0,
  },
  icon: {
    fontSize: "1.2rem",
    flexShrink: 0,
  },
  label: {
    fontSize: "0.85rem",
    color: "#fff",
    fontWeight: 500,
  },
  state: {
    marginLeft: "auto",
    fontSize: "0.7rem",
    fontFamily: "monospace",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
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
