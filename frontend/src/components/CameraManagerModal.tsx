import { useState } from "react"
import { api } from "../api/client"
import type { CameraInfo } from "../types"

interface CameraManagerModalProps {
  open: boolean
  cameraList: CameraInfo[]
  isRunning: boolean
  onClose: () => void
  onRefresh: () => void
}

export function CameraManagerModal({
  open,
  cameraList,
  isRunning,
  onClose,
  onRefresh,
}: CameraManagerModalProps) {
  const [newName, setNewName] = useState("")
  const [newSource, setNewSource] = useState("")
  const [status, setStatus] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState("")
  const [editingSource, setEditingSource] = useState("")
  const [togglingId, setTogglingId] = useState<string | null>(null)

  if (!open) return null

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
      onRefresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`Удалить камеру ${id}?`)) return
    try {
      await api.deleteCamera(id)
      onRefresh()
    } catch {
      // ignore
    }
  }

  const handleRename = async (oldId: string) => {
    if (!editingName.trim()) return
    try {
      await api.renameCamera(oldId, editingName.trim())
      setEditingId(null)
      onRefresh()
    } catch (err) {
      alert("ERR " + (err as Error).message)
    }
  }

  const handleUpdateSource = async (id: string) => {
    if (!editingSource.trim()) return
    try {
      const srcInt = parseInt(editingSource)
      await api.updateCamera(id, isNaN(srcInt) ? editingSource.trim() : srcInt)
      setEditingId(null)
      onRefresh()
    } catch {
      // ignore
    }
  }

  const handleToggleAnalytics = async (cam: CameraInfo) => {
    setTogglingId(cam.name)
    try {
      await api.toggleAnalytics(cam.name, !cam.detect_enabled)
      onRefresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <span>Управление камерами</span>
          <button style={styles.closeBtn} onClick={onClose}>
            X
          </button>
        </div>

        <div style={styles.body}>
          <div style={styles.addRow}>
            <input
              style={styles.input}
              placeholder="Имя (cam4)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              style={styles.inputWide}
              placeholder="URL / число (0)"
              value={newSource}
              onChange={(e) => setNewSource(e.target.value)}
            />
            <button style={styles.addBtn} onClick={handleAdd}>
              + Добавить
            </button>
          </div>

            {status && (
            <div
              style={{
                ...styles.status,
                color: status.startsWith("OK") ? "#00e676" : status.startsWith("ERR") ? "#f44336" : "#ffd600",
              }}
            >
              {status}
            </div>
            )}

          <div>
            {cameraList.length === 0 ? (
              <div style={styles.empty}>Нет камер</div>
            ) : (
              cameraList.map((cam) => {
                const isEditing = editingId === cam.name
                return (
                  <div key={cam.name} style={styles.item}>
                    <div style={styles.avatar}>
                      {cam.name.charAt(0).toUpperCase()}
                    </div>
                    <div style={styles.info}>
                      <div style={styles.nameRow}>
                        {isEditing ? (
                          <input
                            style={styles.nameInput}
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRename(cam.name)
                              if (e.key === "Escape") setEditingId(null)
                            }}
                            autoFocus
                          />
                        ) : (
                          <span style={{ color: "#00e676" }}>{cam.name}</span>
                        )}
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
                      <div style={styles.meta}>
                        {typeof cam.source === "number"
                          ? `LOCAL ${cam.source}`
                          : `RTSP ${cam.source}`}
                      </div>
                    </div>
                    <div style={styles.actions}>
                      <button
                        style={{
                          ...styles.actionBtn,
                          borderColor: cam.detect_enabled ? "#00e676" : "#f44336",
                          color: cam.detect_enabled ? "#00e676" : "#f44336",
                        }}
                        onClick={() => handleToggleAnalytics(cam)}
                        disabled={togglingId === cam.name}
                      >
                        {togglingId === cam.name ? "..." : cam.detect_enabled ? "OFF" : "ON"}
                      </button>
                      {isEditing ? (
                        <button style={styles.actionBtn} onClick={() => handleRename(cam.name)}>
                          SAVE
                        </button>
                      ) : (
                        <button
                          style={styles.actionBtn}
                          onClick={() => {
                            setEditingId(cam.name)
                            setEditingName(cam.name)
                            setEditingSource(String(cam.source))
                          }}
                        >
                          EDIT
                        </button>
                      )}
                      <button style={{ ...styles.actionBtn, color: "#ff5566" }} onClick={() => handleDelete(cam.name)}>
                        DEL
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        <div style={styles.footer}>
          <span style={styles.footerCount}>{cameraList.length} cameras</span>
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
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 500,
    background: "#000000cc",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  modal: {
    background: "#222",
    border: "1px solid #333",
    borderRadius: "12px",
    width: "90vw",
    maxWidth: "600px",
    maxHeight: "80vh",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px 12px",
    borderBottom: "1px solid #333",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 700,
    fontSize: "0.9rem",
    letterSpacing: "2px",
    color: "#00e676",
    textTransform: "uppercase",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "#888",
    fontSize: "1.2rem",
    cursor: "pointer",
    padding: "0 4px",
  },
  body: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 16px",
  },
  addRow: {
    display: "flex",
    gap: "6px",
    marginBottom: "12px",
    flexWrap: "wrap",
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
    textTransform: "uppercase",
  },
  status: {
    fontFamily: "monospace",
    fontSize: ".7rem",
    marginBottom: "8px",
  },
  empty: {
    textAlign: "center",
    padding: "30px 20px",
    color: "#888",
    fontFamily: "monospace",
    fontSize: "0.75rem",
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "10px 12px",
    marginBottom: "6px",
    background: "#2a2a2a",
    border: "1px solid #333",
    borderRadius: "8px",
    transition: "border-color .2s",
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
    fontWeight: 600,
    fontSize: "0.85rem",
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  nameInput: { ...baseInput, width: "120px" },
  meta: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    marginTop: "2px",
  },
  actions: {
    display: "flex",
    gap: "4px",
  },
  actionBtn: {
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
  footer: {
    padding: "10px 16px",
    borderTop: "1px solid #333",
  },
  footerCount: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#888",
  },
}
