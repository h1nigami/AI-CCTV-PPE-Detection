// ============================================================
// Страница просмотра событий (заглушка).
// Будет содержать таймлайн с фильтрацией по камерам и типу.
// ============================================================

import { useCamerasContext } from "../contexts/CameraContext"

export default function EventsPage() {
  const { recentEvents } = useCamerasContext()

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>ЛЕНТА СОБЫТИЙ</h1>
        <span style={styles.count}>{recentEvents.length} событий</span>
      </div>

      <div style={styles.content}>
        <div style={styles.placeholder}>
          <div style={styles.placeholderText}>
            Здесь будет таймлайн событий с фильтрацией по камерам, типу и времени.
          </div>
          <div style={styles.placeholderHint}>
            Реализация после утверждения макета диспетчерской панели
          </div>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#1a1a1a",
    color: "#ffffff",
    minHeight: 0,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
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
  count: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
  },
  content: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  placeholder: {
    textAlign: "center",
    maxWidth: "400px",
  },
  placeholderText: {
    fontFamily: "'Inter', sans-serif",
    fontSize: "0.9rem",
    color: "#888",
    marginBottom: "8px",
  },
  placeholderHint: {
    fontFamily: "monospace",
    fontSize: "0.65rem",
    color: "#333",
  },
}
