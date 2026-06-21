import { useState } from "react"
import { api } from "../api/client"
import { useCamerasContext } from "../contexts/CameraContext"

// ============================================================
// Единый блок управления камерами (CRUD + автообнаружение).
// Используется и в модалке (CameraManagerModal), и на странице настроек
// (SettingsPage) — раньше это была продублированная логика в двух местах.
// Источник данных — CameraContext (cameras + refresh), без своих запросов.
// ============================================================

interface DiscoveredCamera {
  ip: string
  rtsp_url: string
  name: string
  status: string
}

export function CameraManager() {
  const { cameras, refresh } = useCamerasContext()

  const [newName, setNewName] = useState("")
  const [newSource, setNewSource] = useState("")
  const [status, setStatus] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState("")
  const [editingSource, setEditingSource] = useState("")
  const [discovering, setDiscovering] = useState(false)
  const [discovered, setDiscovered] = useState<DiscoveredCamera[]>([])

  const handleDiscover = async () => {
    setDiscovering(true)
    setStatus("Поиск камер в сети…")
    try {
      const res = await api.discoverCameras(false)
      setDiscovered(res.found)
      setStatus(res.found.length ? `Найдено: ${res.found.length}` : "Открытых камер не найдено")
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    } finally {
      setDiscovering(false)
    }
  }

  const handleAddDiscovered = async (d: DiscoveredCamera) => {
    try {
      await api.addCamera(d.name, d.rtsp_url)
      setDiscovered((prev) => prev.filter((x) => x.rtsp_url !== d.rtsp_url))
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

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
    if (!confirm(`Удалить камеру ${id}?`)) return
    try {
      await api.deleteCamera(id)
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

  const startEdit = (id: string, source: string | number) => {
    setEditingId(id)
    setEditingName(id)
    setEditingSource(String(source))
  }

  // SAVE применяет оба изменения: сначала источник (по старому id), затем имя
  // (переименование меняет id, поэтому обновление источника идёт первым).
  const handleSave = async (oldId: string, oldSource: string | number) => {
    if (!editingName.trim()) {
      setStatus("Имя не может быть пустым")
      return
    }
    try {
      if (editingSource.trim() && editingSource.trim() !== String(oldSource)) {
        const srcInt = parseInt(editingSource)
        await api.updateCamera(oldId, isNaN(srcInt) ? editingSource.trim() : srcInt)
      }
      if (editingName.trim() !== oldId) {
        await api.renameCamera(oldId, editingName.trim())
      }
      setEditingId(null)
      refresh()
    } catch (err) {
      setStatus("ERR " + (err as Error).message)
    }
  }

  return (
    <div>
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
          placeholder="URL / число (0)"
          value={newSource}
          onChange={(e) => setNewSource(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleAdd() }}
        />
        <button style={styles.addBtn} onClick={handleAdd}>
          + Добавить
        </button>
        <button style={styles.discoverBtn} onClick={handleDiscover} disabled={discovering}>
          {discovering ? "Поиск…" : "🔍 Найти камеры"}
        </button>
      </div>

      {discovered.length > 0 && (
        <div style={styles.discoverList}>
          {discovered.map((d) => (
            <div key={d.rtsp_url} style={styles.discoverItem}>
              <div style={styles.discoverInfo}>
                <span style={{ color: "#00b0ff" }}>{d.ip}</span>
                <span style={styles.discoverUrl}>{d.rtsp_url}</span>
              </div>
              {d.status === "exists" ? (
                <span style={styles.discoverExists}>уже есть</span>
              ) : (
                <button style={styles.actionBtn} onClick={() => handleAddDiscovered(d)}>
                  + Добавить
                </button>
              )}
            </div>
          ))}
        </div>
      )}

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
        {cameras.length === 0 ? (
          <div style={styles.empty}>Нет камер</div>
        ) : (
          cameras.map((cam) => {
            const isEditing = editingId === cam.name
            return (
              <div key={cam.name} style={styles.item}>
                <div style={styles.avatar}>{cam.name.charAt(0).toUpperCase()}</div>
                <div style={styles.info}>
                  {isEditing ? (
                    <div style={styles.editRow}>
                      <input
                        style={styles.nameInput}
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSave(cam.name, cam.source)
                          if (e.key === "Escape") setEditingId(null)
                        }}
                        autoFocus
                      />
                      <input
                        style={styles.sourceInput}
                        value={editingSource}
                        onChange={(e) => setEditingSource(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSave(cam.name, cam.source)
                          if (e.key === "Escape") setEditingId(null)
                        }}
                      />
                    </div>
                  ) : (
                    <>
                      <div style={styles.nameRow}>
                        <span style={{ color: "#00e676", fontWeight: 600 }}>{cam.name}</span>
                        {!cam.detect_enabled && <span style={styles.detectOff}>детекция выкл</span>}
                      </div>
                      <div style={styles.meta}>
                        {typeof cam.source === "number" ? `LOCAL ${cam.source}` : `RTSP ${cam.source}`}
                      </div>
                    </>
                  )}
                </div>
                <div style={styles.actions}>
                  {isEditing ? (
                    <>
                      <button style={styles.actionBtn} onClick={() => handleSave(cam.name, cam.source)}>
                        SAVE
                      </button>
                      <button style={{ ...styles.actionBtn, color: "#888" }} onClick={() => setEditingId(null)}>
                        CANCEL
                      </button>
                    </>
                  ) : (
                    <button style={styles.actionBtn} onClick={() => startEdit(cam.name, cam.source)}>
                      EDIT
                    </button>
                  )}
                  <button
                    style={{ ...styles.actionBtn, color: "#ff5566", borderColor: "#ff556644" }}
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
  discoverBtn: {
    background: "#2a2a2a",
    border: "1px solid #00b0ff",
    color: "#00b0ff",
    borderRadius: "6px",
    padding: "6px 12px",
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: ".7rem",
    textTransform: "uppercase",
  },
  discoverList: {
    marginBottom: "12px",
    border: "1px solid #2e3a44",
    borderRadius: "8px",
    overflow: "hidden",
  },
  discoverItem: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px",
    padding: "8px 12px",
    borderBottom: "1px solid #222",
  },
  discoverInfo: { display: "flex", flexDirection: "column", minWidth: 0, gap: "2px" },
  discoverUrl: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#888",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "320px",
  },
  discoverExists: { fontFamily: "monospace", fontSize: "0.65rem", color: "#666" },
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
  detectOff: {
    fontFamily: "monospace",
    fontSize: "0.6rem",
    color: "#ff9800",
    border: "1px solid #ff980044",
    borderRadius: "4px",
    padding: "0 4px",
  },
  meta: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    marginTop: "2px",
  },
  editRow: {
    display: "flex",
    gap: "4px",
    flexWrap: "wrap",
    alignItems: "center",
  },
  nameInput: { ...baseInput, width: "100px" },
  sourceInput: { ...baseInput, width: "160px" },
  actions: {
    display: "flex",
    gap: "4px",
    flexShrink: 0,
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
}
