import { useState, useEffect } from "react"
import { api } from "../api/client"
import type { ReidPerson } from "../types"

interface GalleryModalProps {
  open: boolean
  onClose: () => void
}

export function GalleryModal({ open, onClose }: GalleryModalProps) {
  const [persons, setPersons] = useState<ReidPerson[]>([])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState("")

  useEffect(() => {
    if (!open) return
    const load = () =>
      api
        .getReidPersons()
        .then((data) => setPersons(data.persons))
        .catch(() => setPersons([]))
    load()
    // Обновляем, пока модалка открыта — чтобы остаток пропуска был актуальным.
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [open])

  if (!open) return null

  const handleRename = async (gid: number) => {
    if (!editName.trim()) return
    try {
      await api.renameReidPerson(gid, editName.trim())
      setPersons((prev) =>
        prev.map((p) => (p.global_id === gid ? { ...p, name: editName.trim() } : p)),
      )
      setEditingId(null)
    } catch {
      // ignore
    }
  }

  const handleDelete = async (gid: number) => {
    if (!confirm("Удалить этого человека из галереи?")) return
    try {
      await api.deleteReidPerson(gid)
      setPersons((prev) => prev.filter((p) => p.global_id !== gid))
    } catch {
      // ignore
    }
  }

  const handleGrant = async (gid: number) => {
    try {
      await api.grantReidPass(gid)
      // Оптимистично 5 минут; точное значение подтянет поллинг через 3с.
      setPersons((prev) =>
        prev.map((p) => (p.global_id === gid ? { ...p, pass_seconds_left: 300 } : p)),
      )
    } catch {
      // ignore
    }
  }

  const handleRevoke = async (gid: number) => {
    if (!confirm("Сбросить пропуск этого человека? Он снова будет под контролем СИЗ.")) return
    try {
      await api.revokeReidPass(gid)
      setPersons((prev) =>
        prev.map((p) => (p.global_id === gid ? { ...p, pass_seconds_left: 0 } : p)),
      )
    } catch {
      // ignore
    }
  }

  const handleClear = async () => {
    if (!confirm("Очистить всю галерею лиц?")) return
    try {
      await api.clearReid()
      setPersons([])
    } catch {
      // ignore
    }
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <span>👤 Галерея лиц</span>
          <button style={styles.closeBtn} onClick={onClose}>
            ✕
          </button>
        </div>

        <div style={styles.body}>
          {persons.length === 0 ? (
            <div style={styles.empty}>Галерея пуста</div>
          ) : (
            persons.map((p) => {
              const initials = p.name ? p.name.charAt(0) : "?"
              const lastSeen = new Date(p.last_seen * 1000).toLocaleString("ru-RU")
              const cams = (p.cameras || []).join(", ").toUpperCase()
              const isEditing = editingId === p.global_id
              const passLeft = p.pass_seconds_left ?? 0
              const hasPass = passLeft > 0
              const passLabel = `${Math.floor(passLeft / 60)}:${String(passLeft % 60).padStart(2, "0")}`

              return (
                <div key={p.global_id} style={styles.item}>
                  <div style={styles.avatar}>{initials}</div>
                  <div style={styles.info}>
                    <div style={styles.nameRow}>
                      {isEditing ? (
                        <input
                          style={styles.nameInput}
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleRename(p.global_id)
                            if (e.key === "Escape") setEditingId(null)
                          }}
                          autoFocus
                        />
                      ) : (
                        <span style={{ color: "#00e676" }}>{p.name}</span>
                      )}
                      {hasPass && (
                        <span style={styles.passBadge} title="Активный пропуск — предупреждения не озвучиваются">
                          🎫 ПРОПУСК {passLabel}
                        </span>
                      )}
                    </div>
                    <div style={styles.meta}>
                      ID={p.global_id} · {lastSeen} · {cams} · эмб:{p.embedding_count}
                    </div>
                  </div>
                  <div style={styles.actions}>
                    {isEditing ? (
                      <button style={styles.actionBtn} onClick={() => handleRename(p.global_id)}>
                        💾
                      </button>
                    ) : (
                      <button
                        style={styles.actionBtn}
                        onClick={() => {
                          setEditingId(p.global_id)
                          setEditName(p.name)
                        }}
                      >
                        ✏️
                      </button>
                    )}
                    {hasPass ? (
                      <button
                        style={styles.revokeBtn}
                        title="Сбросить пропуск"
                        onClick={() => handleRevoke(p.global_id)}
                      >
                        🎫✕
                      </button>
                    ) : (
                      <button
                        style={styles.grantBtn}
                        title="Выдать пропуск на 5 минут"
                        onClick={() => handleGrant(p.global_id)}
                      >
                        🎫
                      </button>
                    )}
                    <button style={styles.actionBtn} onClick={() => handleDelete(p.global_id)}>
                      🗑
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </div>

        <div style={styles.footer}>
          <span style={styles.footerCount}>{persons.length} человек</span>
          <button style={styles.clearBtn} onClick={handleClear}>
            🗑 Очистить всё
          </button>
        </div>
      </div>
    </div>
  )
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
  nameInput: {
    background: "#1a1a1a",
    border: "1px solid #333",
    borderRadius: "6px",
    padding: "2px 6px",
    fontFamily: "monospace",
    fontSize: "0.8rem",
    color: "#ffffff",
    width: "140px",
  },
  meta: {
    fontFamily: "monospace",
    fontSize: "0.62rem",
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
  revokeBtn: {
    background: "none",
    border: "1px solid #ffa726",
    borderRadius: "6px",
    color: "#ffa726",
    cursor: "pointer",
    padding: "2px 8px",
    fontFamily: "monospace",
    fontSize: "0.65rem",
    transition: "all .2s",
  },
  grantBtn: {
    background: "none",
    border: "1px solid #00e67655",
    borderRadius: "6px",
    color: "#00e676",
    cursor: "pointer",
    padding: "2px 8px",
    fontFamily: "monospace",
    fontSize: "0.65rem",
    transition: "all .2s",
  },
  passBadge: {
    background: "#1b5e2033",
    border: "1px solid #00e67655",
    borderRadius: "10px",
    color: "#00e676",
    fontFamily: "monospace",
    fontSize: "0.58rem",
    padding: "1px 6px",
    letterSpacing: "0.5px",
  },
  footer: {
    padding: "10px 16px",
    borderTop: "1px solid #333",
    display: "flex",
    gap: "8px",
    justifyContent: "space-between",
    alignItems: "center",
  },
  footerCount: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#888",
  },
  clearBtn: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: "0.75rem",
    letterSpacing: "1px",
    background: "transparent",
    border: "1px solid #333",
    color: "#888",
    borderRadius: "6px",
    padding: "6px 12px",
    cursor: "pointer",
    textTransform: "uppercase",
    transition: "all .2s",
  },
}
