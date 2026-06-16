import { useState, useRef, useEffect } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import { useCamerasContext } from "../contexts/CameraContext"
import { useClock } from "../hooks/useClock"

// ============================================================
// Шапка приложения — навигация, выбор группы камер, часы,
// профиль пользователя.
// ============================================================

export function Header() {
  const now = useClock()
  const { user, logout } = useAuth()
  const { groups, activeGroupId, setActiveGroup } = useCamerasContext()
  const navigate = useNavigate()
  const location = useLocation()

  // Состояние дропдауна групп
  const [groupOpen, setGroupOpen] = useState(false)
  const groupRef = useRef<HTMLDivElement>(null)

  // Закрытие дропдауна по клику вне него
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (groupRef.current && !groupRef.current.contains(e.target as Node)) {
        setGroupOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  // Форматирование времени
  const timeStr = now.toLocaleTimeString("ru-RU")
  const dateStr = now.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })

  // Выход
  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  // Активная группа
  const activeGroup = groups.find((g) => g.id === activeGroupId)

  return (
    <header style={styles.header}>
      {/* Левая часть: логотип + навигация */}
      <div style={styles.headerLeft}>
        {/* Логотип */}
        <div style={styles.logo}>
          <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
            <rect x="2" y="2" width="24" height="24" rx="4" stroke="#00e5ff" strokeWidth="1.5" />
            <circle cx="14" cy="12" r="5" stroke="#00e5ff" strokeWidth="1.5" />
            <path d="M6 22c0-4 3.6-7 8-7s8 3 8 7" stroke="#00e5ff" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          KONTROLER AI
        </div>

        {/* Навигация */}
        <nav style={styles.nav}>
          <button
            style={{
              ...styles.navBtn,
              ...(location.pathname === "/" ? styles.navActive : {}),
            }}
            onClick={() => navigate("/")}
          >
            ДАШБОРД
          </button>
          <button
            style={{
              ...styles.navBtn,
              ...(location.pathname === "/events" ? styles.navActive : {}),
            }}
            onClick={() => navigate("/events")}
          >
            СОБЫТИЯ
          </button>
          <button
            style={{
              ...styles.navBtn,
              ...(location.pathname === "/settings" ? styles.navActive : {}),
            }}
            onClick={() => navigate("/settings")}
          >
            НАСТРОЙКИ
          </button>
        </nav>
      </div>

      {/* Правая часть: группы, часы, пользователь */}
      <div style={styles.headerRight}>
        {/* Выбор группы камер */}
        <div ref={groupRef} style={styles.groupWrapper}>
          <button
            style={styles.groupBtn}
            onClick={() => setGroupOpen((o) => !o)}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="5" height="5" rx="1" stroke="#4a6a8a" strokeWidth="1.2" />
              <rect x="8" y="1" width="5" height="5" rx="1" stroke="#4a6a8a" strokeWidth="1.2" />
              <rect x="1" y="8" width="5" height="5" rx="1" stroke="#4a6a8a" strokeWidth="1.2" />
              <rect x="8" y="8" width="5" height="5" rx="1" stroke="#4a6a8a" strokeWidth="1.2" />
            </svg>
            {activeGroup?.name || "Все камеры"}
            <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ marginLeft: "4px" }}>
              <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          {/* Дропдаун групп */}
          {groupOpen && (
            <div style={styles.groupDropdown}>
              {groups.map((g) => (
                <button
                  key={g.id}
                  style={{
                    ...styles.groupOption,
                    ...(activeGroupId === g.id ? styles.groupOptionActive : {}),
                  }}
                  onClick={() => {
                    setActiveGroup(g.id)
                    setGroupOpen(false)
                  }}
                >
                  {g.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Часы */}
        <div style={styles.clock}>
          <div style={styles.clockTime}>{timeStr}</div>
          <div style={styles.clockDate}>{dateStr}</div>
        </div>

        {/* Пользователь */}
        {user && (
          <div style={styles.userSection}>
            <div style={styles.userAvatar}>
              {user.username.charAt(0).toUpperCase()}
            </div>
            <div style={styles.userInfo}>
              <div style={styles.userName}>{user.username}</div>
              <div style={styles.userRole}>{user.role}</div>
            </div>
            <button style={styles.logoutBtn} onClick={handleLogout} title="Выйти">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M6 14H3a1 1 0 01-1-1V3a1 1 0 011-1h3M11 11l3-3-3-3M14 8H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 20px",
    background: "#0d1520",
    borderBottom: "1px solid #1a3a5c",
    flexShrink: 0,
    zIndex: 100,
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: "32px",
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "1rem",
    letterSpacing: "2px",
    color: "#00e5ff",
    flexShrink: 0,
  },
  nav: {
    display: "flex",
    gap: "4px",
  },
  navBtn: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.72rem",
    letterSpacing: "1.5px",
    border: "1px solid transparent",
    borderRadius: "4px",
    padding: "4px 12px",
    cursor: "pointer",
    background: "transparent",
    color: "#4a6a8a",
    textTransform: "uppercase",
    transition: "all 0.2s",
  },
  navActive: {
    borderColor: "#1a3a5c",
    color: "#00e5ff",
    background: "#00e5ff11",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  groupWrapper: {
    position: "relative",
  },
  groupBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.72rem",
    letterSpacing: "1px",
    border: "1px solid #1a3a5c",
    borderRadius: "4px",
    padding: "5px 12px",
    cursor: "pointer",
    background: "transparent",
    color: "#4a6a8a",
    textTransform: "uppercase",
    transition: "all 0.2s",
  },
  groupDropdown: {
    position: "absolute",
    top: "100%",
    right: 0,
    marginTop: "4px",
    background: "#101a24",
    border: "1px solid #1a3a5c",
    borderRadius: "6px",
    overflow: "hidden",
    minWidth: "180px",
    zIndex: 1000,
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  groupOption: {
    display: "block",
    width: "100%",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.72rem",
    letterSpacing: "1px",
    border: "none",
    borderBottom: "1px solid #1a3a5c22",
    padding: "10px 16px",
    cursor: "pointer",
    background: "transparent",
    color: "#4a6a8a",
    textTransform: "uppercase",
    textAlign: "left",
    transition: "all 0.15s",
  },
  groupOptionActive: {
    color: "#00e5ff",
    background: "#00e5ff11",
  },
  clock: {
    textAlign: "right",
    lineHeight: "1.3",
  },
  clockTime: {
    fontFamily: "'Share Tech Mono', monospace",
    fontSize: "0.85rem",
    color: "#00e5ff",
    letterSpacing: "1px",
  },
  clockDate: {
    fontSize: "0.6rem",
    color: "#4a6a8a",
    fontFamily: "'Exo 2', sans-serif",
  },
  userSection: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    borderLeft: "1px solid #1a3a5c",
    paddingLeft: "12px",
  },
  userAvatar: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    background: "#00e5ff22",
    border: "1px solid #00e5ff44",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 700,
    fontSize: "0.75rem",
    color: "#00e5ff",
  },
  userInfo: {
    lineHeight: "1.2",
  },
  userName: {
    fontFamily: "'Rajdhani', sans-serif",
    fontWeight: 600,
    fontSize: "0.78rem",
    color: "#c8dff0",
  },
  userRole: {
    fontSize: "0.6rem",
    color: "#4a6a8a",
    textTransform: "uppercase",
    fontFamily: "'Exo 2', sans-serif",
  },
  logoutBtn: {
    background: "none",
    border: "1px solid #4a6a8a",
    borderRadius: "4px",
    color: "#ff5566",
    cursor: "pointer",
    padding: "4px 6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.2s",
  },
}
