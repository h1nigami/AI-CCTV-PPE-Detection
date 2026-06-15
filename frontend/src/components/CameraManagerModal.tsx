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

  if (!open) return null

  const handleAdd = async () => {
    if (!newName.trim() || !newSource.trim()) {
      setStatus("⚠️ Заполните имя и источник")
      return
    }
    try {
      const srcInt = parseInt(newSource)
      await api.addCamera(newName.trim(), isNaN(srcInt) ? newSource.trim() : srcInt)
      setNewName("")
      setNewSource("")
      setStatus("✅ Камера добавлена")
      onRefresh()
    } catch (err) {
      setStatus("❌ " + (err as Error).message)
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
      alert("Ошибка: " + (err as Error).message)
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

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <span>📷 Управление камерами</span>
          <button style={styles.closeBtn} onClick={onClose}>
            ✕
          </button>
        </div>

        <div style={styles.body}>
          {/* Add form */}
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
              ➕ Добавить
            </button>
          </div>

          {status && (
            <div
              style={{
                fontFamily: "'Share Tech Mono', monospace",
                fontSize: ".7rem",
                color: status.startsWith("✅") ? "#00ff88" : status.startsWith("⚠️") ? "#ffd600" : "#ff3355",
                marginBottom: "8px",
              }}
            >
              {status}
            </div>
          )}

          {/* Camera list */}
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
                          <span style={{ color: "#00e5ff" }}>{cam.name}</span>
                        )}
                      </div>
                      <div style={styles.meta}>
                        {typeof cam.source === "number"
                          ? `🔌 Локальная камера ${cam.source}`
                          : `📡 ${cam.source}`}
                      </div>
                    </div>
                    <div style={styles.actions}>
                      {isEditing ? (
                        <button style={styles.actionBtn} onClick={() => handleRename(cam.name)}>
                          💾
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
                          ✏️
                        </button>
                      )}
                      <button style={styles.actionBtn} onClick={() => handleDelete(cam.name)}>
                        🗑
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        <div style={styles.footer}>
          <span style={styles.footerCount}>{cameraList.length} камер</span>
        </div>
      </div>
    </div>
  )
}

const baseInput: React.CSSProperties = {
  background: "#080d14",
  border: "1px solid #1a3a5c",
  borderRadius: "3px",
  padding: "6px 8px",
  fontFamily: "'Share Tech Mono', monospace",
  fontSize: ".75rem",
  color: "#c8dff0",
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
    background: "#0d1520",
    border: "1px solid #1a3a5c",
    borderRadius: "10px",
    width: "90vw",
    maxWidth: "560px",
    maxHeight: "80vh",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px 12px",
    borderBottom: "1px solid #1a3a5c",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.9rem",
    letterSpacing: "2px",
    color: "#00e5ff",
    textTransform: "uppercase",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "#4a6a8a",
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
    background: "#111c2b",
    border: "1px solid #00e5ff",
    color: "#00e5ff",
    borderRadius: "3px",
    padding: "6px 12px",
    cursor: "pointer",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: ".7rem",
    textTransform: "uppercase",
  },
  empty: {
    textAlign: "center",
    padding: "30px 20px",
    color: "#4a6a8a",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.75rem",
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "10px 12px",
    marginBottom: "6px",
    background: "#111c2b",
    border: "1px solid #1a3a5c",
    borderRadius: "6px",
    transition: "border-color .2s",
  },
  avatar: {
    width: "36px",
    height: "36px",
    borderRadius: "50%",
    background: "#1a3a5c",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.8rem",
    color: "#00e5ff",
    flexShrink: 0,
  },
  info: {
    flex: 1,
    minWidth: 0,
  },
  nameRow: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.85rem",
    color: "#c8dff0",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  nameInput: { ...baseInput, width: "120px" },
  meta: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
    color: "#4a6a8a",
    marginTop: "2px",
  },
  actions: {
    display: "flex",
    gap: "4px",
  },
  actionBtn: {
    background: "none",
    border: "1px solid #1a3a5c",
    borderRadius: "3px",
    color: "#4a6a8a",
    cursor: "pointer",
    padding: "2px 8px",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    transition: "all .2s",
  },
  footer: {
    padding: "10px 16px",
    borderTop: "1px solid #1a3a5c",
  },
  footerCount: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    color: "#4a6a8a",
  },
}
