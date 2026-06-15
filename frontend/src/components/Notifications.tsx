import { useEffect, useState } from "react"

interface Notification {
  id: string
  type: string
  title: string
  sub?: string
  duration: number
}

interface NotificationsProps {
  notifications: Notification[]
  onRemove: (id: string) => void
}

export function Notifications({ notifications, onRemove }: NotificationsProps) {
  return (
    <div style={styles.container}>
      {notifications.map((n) => (
        <NotificationItem key={n.id} notification={n} onRemove={onRemove} />
      ))}
    </div>
  )
}

function NotificationItem({
  notification,
  onRemove,
}: {
  notification: Notification
  onRemove: (id: string) => void
}) {
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setExiting(true), notification.duration)
    const removeTimer = setTimeout(() => onRemove(notification.id), notification.duration + 350)
    return () => {
      clearTimeout(timer)
      clearTimeout(removeTimer)
    }
  }, [notification, onRemove])

  const typeStyles: Record<string, React.CSSProperties> = {
    granted: {
      background: "linear-gradient(135deg, #00ff8833 0%, #00ff8811 100%)",
      border: "1px solid #00ff8866",
      color: "#00ff88",
    },
    violation: {
      background: "linear-gradient(135deg, #ff335544 0%, #ff335522 100%)",
      border: "1px solid #ff335566",
      color: "#ff3355",
    },
    warning: {
      background: "linear-gradient(135deg, #ffd60044 0%, #ffd60022 100%)",
      border: "1px solid #ffd60066",
      color: "#ffd600",
    },
    missing: {
      background: "linear-gradient(135deg, #ff6d0044 0%, #ff6d0022 100%)",
      border: "1px solid #ff6d0066",
      color: "#ff6d00",
    },
  }

  return (
    <div
      style={{
        ...styles.notification,
        ...(typeStyles[notification.type] || typeStyles.warning),
        animation: exiting
          ? "notifOut 0.35s ease-in forwards"
          : "notifIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards",
      }}
    >
      <div style={styles.notifTitle}>{notification.title}</div>
      {notification.sub && <div style={styles.notifSub}>{notification.sub}</div>}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 9999,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "8px",
    padding: "12px 20px",
    pointerEvents: "none",
  },
  notification: {
    pointerEvents: "auto",
    maxWidth: "600px",
    width: "100%",
    padding: "16px 24px 14px",
    borderRadius: "0 0 14px 14px",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "1rem",
    letterSpacing: "2px",
    textTransform: "uppercase",
    textAlign: "center",
    boxShadow: "0 6px 32px rgba(0,0,0,0.6)",
    position: "relative",
    overflow: "hidden",
  },
  notifTitle: {
    fontSize: "1.1rem",
    lineHeight: "1.4",
  },
  notifSub: {
    fontSize: "0.72rem",
    fontWeight: 500,
    letterSpacing: "0.5px",
    opacity: 0.85,
    marginTop: "2px",
    textTransform: "none",
  },
}
