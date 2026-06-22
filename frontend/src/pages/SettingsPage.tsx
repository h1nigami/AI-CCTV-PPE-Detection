import { CameraManager } from "../components/CameraManager"
import { PpeRequiredSettings } from "../components/PpeRequiredSettings"

export default function SettingsPage() {
  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>НАСТРОЙКИ</h1>
      </div>

      <div style={styles.content}>
        {/* Блок: камеры — общий компонент (тот же, что в модалке дашборда) */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>КАМЕРЫ</div>
          <div style={styles.cardBody}>
            <CameraManager />
          </div>
        </div>

        {/* Блок: какие СИЗ нужны для пропуска по жесту «ОК» */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>ОБЯЗАТЕЛЬНЫЕ СИЗ ДЛЯ ПРОПУСКА</div>
          <div style={styles.cardBody}>
            <PpeRequiredSettings />
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
  placeholder: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
    textAlign: "center" as const,
    padding: "20px",
  },
}
