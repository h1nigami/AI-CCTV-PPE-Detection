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
                  <span style={{ ...styles.rowStatus,                     color: cam.detect_enabled ? "#00e676" : "#f44336" }}>
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
    fontWeight: 700,
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
  row: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "8px 0",
    borderBottom: "1px solid #33333322",
    fontFamily: "monospace",
    fontSize: "0.7rem",
  },
  rowName: {
    color: "#ffffff",
    minWidth: "120px",
  },
  rowSource: {
    color: "#888",
    flex: 1,
  },
  rowStatus: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
  },
  empty: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    textAlign: "center",
    padding: "20px",
  },
  placeholder: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    textAlign: "center",
    padding: "20px",
  },
}
