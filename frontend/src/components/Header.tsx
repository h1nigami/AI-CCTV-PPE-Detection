import { useState, useRef, useEffect, useCallback } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import { api } from "../api/client"
import { useClock } from "../hooks/useClock"

const MODE_LABELS: Record<string, string> = {
  people: "Люди",
  ppe: "СИЗ",
  faces: "Лица",
}

export function Header() {
  const now = useClock()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [modesOpen, setModesOpen] = useState(false)
  const [modes, setModes] = useState<Record<string, boolean>>({
    people: true,
    ppe: true,
    faces: true,
  })
  const modesRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getDetectModes().then((data) => {
      if (data.modes) setModes(data.modes)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modesRef.current && !modesRef.current.contains(e.target as Node)) {
        setModesOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const toggleMode = useCallback(async (key: string) => {
    const next = { ...modes, [key]: !modes[key] }
    setModes(next)
    try {
      await api.setDetectModes(next)
    } catch {
      setModes(modes)
    }
  }, [modes])

  const timeStr = now.toLocaleTimeString("ru-RU")
  const dateStr = now.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <header style={styles.header}>
      <div style={styles.headerLeft}>
        <div style={styles.logo}>
          <span style={styles.logoText}>Видеоаналитика в реальном времени</span>
        </div>

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

      <div style={styles.headerCenter}>
        <img src="/logo.svg" alt="" style={styles.centerLogo} />
        <span>Нейроконтролер</span>
      </div>

      <div style={styles.headerRight}>
        <div ref={modesRef} style={styles.modesWrapper}>
          <button
            style={styles.modesBtn}
            onClick={() => setModesOpen((o) => !o)}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="5" height="5" rx="1" stroke="#888" strokeWidth="1.2" />
              <rect x="8" y="1" width="5" height="5" rx="1" stroke="#888" strokeWidth="1.2" />
              <rect x="1" y="8" width="5" height="5" rx="1" stroke="#888" strokeWidth="1.2" />
              <rect x="8" y="8" width="5" height="5" rx="1" stroke="#888" strokeWidth="1.2" />
            </svg>
            Детекция
            <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ marginLeft: "4px" }}>
              <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          {modesOpen && (
            <div style={styles.modesDropdown}>
              {Object.entries(MODE_LABELS).map(([key, label]) => (
                <label key={key} style={styles.modeOption}>
                  <input
                    type="checkbox"
                    checked={!!modes[key]}
                    onChange={() => toggleMode(key)}
                    style={styles.modeCheckbox}
                  />
                  <span>{label}</span>
                  <span style={{
                    ...styles.modeDot,
                    background: modes[key] ? "#00e676" : "#333",
                  }} />
                </label>
              ))}
            </div>
          )}
        </div>

        <div style={styles.clock}>
          <div style={styles.clockTime}>{timeStr}</div>
          <div style={styles.clockDate}>{dateStr}</div>
        </div>

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
    padding: "0 24px",
    height: "56px",
    background: "#1a1a1a",
    borderBottom: "1px solid #333",
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
    gap: "10px",
  },
  logoText: {
    fontWeight: 500,
    fontSize: "0.75rem",
    color: "#aaa",
    fontFamily: "'Inter', sans-serif",
    letterSpacing: "1px",
  },
  headerCenter: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    fontSize: "1.25rem",
    fontWeight: 800,
    color: "#ffffff",
    fontFamily: "'Inter', sans-serif",
    letterSpacing: "2px",
  },
  centerLogo: {
    width: "24px",
    height: "24px",
  },
  nav: {
    display: "flex",
    gap: "4px",
  },
  navBtn: {
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    fontSize: "0.72rem",
    letterSpacing: "1.5px",
    border: "1px solid transparent",
    borderRadius: "8px",
    padding: "4px 12px",
    cursor: "pointer",
    background: "transparent",
    color: "#888",
    textTransform: "uppercase",
    transition: "all 0.2s",
  },
  navActive: {
    borderColor: "#333",
    color: "#00e676",
    background: "#00e67610",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  modesWrapper: {
    position: "relative",
  },
  modesBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 500,
    fontSize: "0.72rem",
    letterSpacing: "1px",
    border: "1px solid #333",
    borderRadius: "8px",
    padding: "5px 12px",
    cursor: "pointer",
    background: "#2a2a2a",
    color: "#888",
    textTransform: "uppercase",
    transition: "all 0.2s",
  },
  modesDropdown: {
    position: "absolute",
    top: "100%",
    right: 0,
    marginTop: "4px",
    background: "#222",
    border: "1px solid #333",
    borderRadius: "8px",
    overflow: "hidden",
    minWidth: "160px",
    zIndex: 1000,
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  modeOption: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 14px",
    cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 500,
    fontSize: "0.78rem",
    color: "#ccc",
    borderBottom: "1px solid #33333322",
    transition: "background 0.15s",
  },
  modeCheckbox: {
    width: "14px",
    height: "14px",
    accentColor: "#00e676",
    cursor: "pointer",
  },
  modeDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    marginLeft: "auto",
    transition: "background 0.2s",
  },
  clock: {
    textAlign: "right",
    lineHeight: "1.5",
  },
  clockTime: {
    fontFamily: "monospace",
    fontSize: "0.8rem",
    color: "#888",
  },
  clockDate: {
    fontFamily: "monospace",
    fontSize: "0.7rem",
    color: "#888",
  },
  userSection: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    borderLeft: "1px solid #333",
    paddingLeft: "12px",
  },
  userAvatar: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    background: "#00e67620",
    border: "1px solid #00e67640",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    fontSize: "0.75rem",
    color: "#00e676",
    fontFamily: "'Inter', sans-serif",
  },
  userInfo: {
    lineHeight: "1.2",
  },
  userName: {
    fontWeight: 600,
    fontSize: "0.78rem",
    color: "#ffffff",
    fontFamily: "'Inter', sans-serif",
  },
  userRole: {
    fontSize: "0.6rem",
    color: "#888",
    textTransform: "uppercase",
    fontFamily: "'Inter', sans-serif",
  },
  logoutBtn: {
    background: "none",
    border: "1px solid #888",
    borderRadius: "4px",
    color: "#f44336",
    cursor: "pointer",
    padding: "4px 6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.2s",
  },
}
