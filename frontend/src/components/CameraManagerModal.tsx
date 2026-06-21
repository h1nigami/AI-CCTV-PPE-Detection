import { useCamerasContext } from "../contexts/CameraContext"
import { CameraManager } from "./CameraManager"

interface CameraManagerModalProps {
  open: boolean
  onClose: () => void
}

// Тонкая обёртка-оверлей вокруг общего блока CameraManager (вся CRUD-логика
// и автообнаружение — там; данные берутся из CameraContext).
export function CameraManagerModal({ open, onClose }: CameraManagerModalProps) {
  const { cameras } = useCamerasContext()
  if (!open) return null

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
          <CameraManager />
        </div>

        <div style={styles.footer}>
          <span style={styles.footerCount}>{cameras.length} cameras</span>
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
