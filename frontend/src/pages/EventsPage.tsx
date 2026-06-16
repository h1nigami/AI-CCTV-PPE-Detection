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
    background: "#080d14",
    color: "#c8dff0",
    minHeight: 0,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 24px",
    borderBottom: "1px solid #1a3a5c",
  },
  title: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "1rem",
    letterSpacing: "3px",
    color: "#00e5ff",
    textTransform: "uppercase",
    margin: 0,
  },
  count: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
    color: "#4a6a8a",
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
    fontFamily: "'Rajdhani', sans-serif",
    fontSize: "0.9rem",
    color: "#4a6a8a",
    marginBottom: "8px",
  },
  placeholderHint: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.65rem",
    color: "#1a3a5c",
  },
}
