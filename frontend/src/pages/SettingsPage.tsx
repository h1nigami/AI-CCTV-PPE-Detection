import { useState, useEffect, useCallback } from "react"
import { api } from "../api/client"
import type { CameraInfo } from "../types"

export default function SettingsPage() {
  const [cameras, setCameras] = useState<CameraInfo[]>([])
  const [newName, setNewName] = useState("")
  const [newSource, setNewSource] = useState("")
  const [status, setStatus] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState("")
  const [editingSource, setEditingSource] = useState("")
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getCameras()
      const list = Object.entries(data.cameras).map(([name, cfg]) => ({
        name,
        source: typeof cfg === "object" && cfg !== null ? cfg.source : cfg,
        detect_enabled: typeof cfg === "object" && cfg !== null ? cfg.detect_enabled : true,
      }))
      setCameras(list)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAdd = async () => {
    if (!newName.trim() || !newSource.trim()) {
      setStatus("Заполните имя и источник")
      return
    }
    try {
      const srcInt = parseInt(newSource)
      await api.addCamera(newName.trim(), isNaN(srcInt) ? newSource.trim() : srcInt)
      setNewName("")
      setNewSource("")
      setStatus("OK")
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteCamera(id)
      refresh()
    } catch {
      // ignore
    }
  }

  const handleRename = async (oldId: string) => {
    if (!editingName.trim()) return
    try {
      await api.renameCamera(oldId, editingName.trim())
      setEditingId(null)
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

  const handleUpdateSource = async (id: string) => {
    if (!editingSource.trim()) return
    try {
      const srcInt = parseInt(editingSource)
      await api.updateCamera(id, isNaN(srcInt) ? editingSource.trim() : srcInt)
      setEditingId(null)
      refresh()
    } catch {
      // ignore
    }
  }

  const handleToggleAnalytics = async (cam: CameraInfo) => {
    setTogglingId(cam.name)
    try {
      await api.toggleAnalytics(cam.name, !cam.detect_enabled)
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>НАСТРОЙКИ</h1>
      </div>

      <div style={styles.content}>
        {/* Блок: камеры */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>КАМЕРЫ</div>
          <div style={styles.cardBody}>
            {/* Форма добавления */}
            <div style={styles.addRow}>
              <input
                style={styles.input}
                placeholder="Имя (cam4)"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleAdd() }}
              />
              <input
                style={styles.inputWide}
                placeholder="URL / номер (0)"
                value={newSource}
                onChange={(e) => setNewSource(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleAdd() }}
              />
              <button style={styles.addBtn} onClick={handleAdd}>
                + Добавить
              </button>
            </div>

            {status && (
              <div
                style={{
                  ...styles.statusLine,
                  color: status.startsWith("OK") ? "#00e676" : status.startsWith("ERR") ? "#f44336" : "#ffd600",
                }}
              >
                {status}
              </div>
            )}

            {/* Список камер */}
            {cameras.length === 0 ? (
              <div style={styles.empty}>Нет камер</div>
            ) : (
              cameras.map((cam) => {
                const isEditing = editingId === cam.name
                return (
                  <div key={cam.name} style={styles.row}>
                    <div style={styles.avatar}>
                      {cam.name.charAt(0).toUpperCase()}
                    </div>
                    <div style={styles.info}>
                      {isEditing ? (
                        <div style={styles.editRow}>
                          <input
                            style={styles.inlineInput}
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRename(cam.name)
                              if (e.key === "Escape") setEditingId(null)
                            }}
                            autoFocus
                          />
                          <input
                            style={styles.inlineInputWide}
                            value={editingSource}
                            onChange={(e) => setEditingSource(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleUpdateSource(cam.name)
                              if (e.key === "Escape") setEditingId(null)
                            }}
                          />
                          <button style={styles.miniBtn} onClick={() => handleRename(cam.name)}>
                            SAVE
                          </button>
                          <button style={{ ...styles.miniBtn, color: "#888" }} onClick={() => setEditingId(null)}>
                            CANCEL
                          </button>
                        </div>
                      ) : (
                        <>
                          <div style={styles.nameRow}>
                            <span style={{ color: "#00e676", fontWeight: 600 }}>{cam.name}</span>
                            <span
                              style={{
                                fontSize: "0.6rem",
                                padding: "1px 6px",
                                borderRadius: "4px",
                                background: cam.detect_enabled ? "#0a2a1a" : "#2a1a1a",
                                color: cam.detect_enabled ? "#00e676" : "#f44336",
                                border: `1px solid ${cam.detect_enabled ? "#00e676" : "#f44336"}`,
                              }}
                            >
                              {cam.detect_enabled ? "ANALYTICS ON" : "ANALYTICS OFF"}
                            </span>
                          </div>
                          <div style={styles.sourceLine}>
                            {typeof cam.source === "number"
                              ? `LOCAL ${cam.source}`
                              : `RTSP ${cam.source}`}
                          </div>
                        </>
                      )}
                    </div>
                    <div style={styles.actions}>
                      <button
                        style={{
                          ...styles.miniBtn,
                          borderColor: cam.detect_enabled ? "#00e676" : "#f44336",
                          color: cam.detect_enabled ? "#00e676" : "#f44336",
                        }}
                        onClick={() => handleToggleAnalytics(cam)}
                        disabled={togglingId === cam.name}
                      >
                        {togglingId === cam.name ? "..." : cam.detect_enabled ? "OFF" : "ON"}
                      </button>
                      {!isEditing && (
                        <button
                          style={styles.miniBtn}
                          onClick={() => {
                            setEditingId(cam.name)
                            setEditingName(cam.name)
                            setEditingSource(String(cam.source))
                          }}
                        >
                          EDIT
                        </button>
                      )}
                      <button
                        style={{ ...styles.miniBtn, color: "#ff5566", borderColor: "#ff556644" }}
                        onClick={() => handleDelete(cam.name)}
                      >
                        DEL
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Блок: управление (заглушка) */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>УПРАВЛЕНИЕ</div>
          <div style={styles.cardBody}>
            <div style={styles.placeholder}>
              Управление API-ключами, пользователями и группами камер появится здесь.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const baseInput: React.CSSProperties = {
  background: "#1a1a1a",
  border: "1px solid #333",
  borderRadius: "6px",
  padding: "6px 8px",
  fontFamily: "monospace",
  fontSize: ".75rem",
  color: "#ffffff",
  outline: "none",
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#1a1a1a",
    color: "#ffffff",
    overflow: "hidden",
    minHeight: 0,
  },
  header: {
    padding: "16px 24px",
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
  content: {
    flex: 1,
    overflow: "auto",
    padding: "20px 24px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  card: {
    background: "#222",
    border: "1px solid #333",
    borderRadius: "12px",
    overflow: "hidden",
  },
  cardTitle: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: "0.7rem",
    letterSpacing: "3px",
    color: "#888",
    textTransform: "uppercase",
    padding: "12px 16px",
    borderBottom: "1px solid #333",
    background: "#1a1a1a",
  },
  cardBody: {
    padding: "12px 16px",
  },
  addRow: {
    display: "flex",
    gap: "6px",
    marginBottom: "8px",
    flexWrap: "wrap" as const,
  },
  input: { ...baseInput, flex: 1, minWidth: "80px" },
  inputWide: { ...baseInput, flex: 2, minWidth: "140px" },
  addBtn: {
    background: "#2a2a2a",
    border: "1px solid #00e676",
    color: "#00e676",
    borderRadius: "6px",
    padding: "6px 12px",
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: ".7rem",
    textTransform: "uppercase" as const,
  },
  statusLine: {
    fontFamily: "monospace",
    fontSize: ".7rem",
    marginBottom: "8px",
  },
  empty: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    textAlign: "center" as const,
    padding: "20px",
  },
  placeholder: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    textAlign: "center" as const,
    padding: "20px",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "10px 12px",
    marginBottom: "6px",
    background: "#2a2a2a",
    border: "1px solid #333",
    borderRadius: "8px",
  },
  avatar: {
    width: "36px",
    height: "36px",
    borderRadius: "50%",
    background: "#333",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    color: "#00e676",
    flexShrink: 0,
  },
  info: {
    flex: 1,
    minWidth: 0,
  },
  nameRow: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.85rem",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    marginBottom: "2px",
  },
  sourceLine: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
  },
  editRow: {
    display: "flex",
    gap: "4px",
    flexWrap: "wrap" as const,
    alignItems: "center",
  },
  inlineInput: { ...baseInput, width: "100px" },
  inlineInputWide: { ...baseInput, width: "160px" },
  actions: {
    display: "flex",
    gap: "4px",
    flexShrink: 0,
  },
  miniBtn: {
    background: "none",
    border: "1px solid #333",
    borderRadius: "6px",
    color: "#888",
    cursor: "pointer",
    padding: "2px 8px",
    fontFamily: "monospace",
    fontSize: "0.65rem",
    transition: "all .2s",
  },
}
