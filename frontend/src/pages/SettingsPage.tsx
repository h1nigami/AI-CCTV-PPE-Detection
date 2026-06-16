// ============================================================
// Страница настроек (заглушка).
// Будет содержать: управление камерами, API-ключами, пользователями.
// ============================================================

import { useCamerasContext } from "../contexts/CameraContext"

export default function SettingsPage() {
  const { cameras } = useCamerasContext()

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
            {cameras.length === 0 ? (
              <div style={styles.empty}>Нет камер</div>
            ) : (
              cameras.map((cam) => (
                <div key={cam.name} style={styles.row}>
                  <span style={styles.rowName}>{cam.name}</span>
                  <span style={styles.rowSource}>{String(cam.source)}</span>
                  <span style={{ ...styles.rowStatus, color: cam.detect_enabled ? "#00ff88" : "#ff3355" }}>
                    {cam.detect_enabled ? "ВКЛ" : "ВЫКЛ"}
                  </span>
                </div>
              ))
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

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    background: "#080d14",
    color: "#c8dff0",
    overflow: "hidden",
    minHeight: 0,
  },
  header: {
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
  content: {
    flex: 1,
    overflow: "auto",
    padding: "20px 24px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  card: {
    background: "#0d1520",
    border: "1px solid #1a3a5c",
    borderRadius: "8px",
    overflow: "hidden",
  },
  cardTitle: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.7rem",
    letterSpacing: "3px",
    color: "#4a6a8a",
    textTransform: "uppercase",
    padding: "12px 16px",
    borderBottom: "1px solid #1a3a5c",
    background: "#080d14",
  },
  cardBody: {
    padding: "12px 16px",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "8px 0",
    borderBottom: "1px solid #1a3a5c22",
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
  },
  rowName: {
    color: "#c8dff0",
    minWidth: "120px",
  },
  rowSource: {
    color: "#4a6a8a",
    flex: 1,
  },
  rowStatus: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
  },
  empty: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
    color: "#4a6a8a",
    textAlign: "center",
    padding: "20px",
  },
  placeholder: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.7rem",
    color: "#4a6a8a",
    textAlign: "center",
    padding: "20px",
  },
}
