import { useState, useRef, useEffect, useCallback } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import { useCamerasContext } from "../contexts/CameraContext"
import { api } from "../api/client"
import { useClock } from "../hooks/useClock"
import { useBreakpoint } from "../hooks/useBreakpoint"

const MODE_LABELS: Record<string, string> = {
  people: "Люди",
  ppe: "СИЗ",
  faces: "Лица",
}

const DEFAULT_MODES: Record<string, boolean> = { people: true, ppe: true, faces: true }

export function Header() {
  const now = useClock()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const bp = useBreakpoint()
  const isMobile = bp === 'mobile'
  const { isRunning, setDetectionRunning, detectModes, updateDetectModes } = useCamerasContext()
  // Единый источник режимов — контекст (загружается там при монтировании).
  // null до первой загрузки → показываем дефолт, чтобы тумблеры не «прыгали».
  const modes = detectModes ?? DEFAULT_MODES

  const [modesOpen, setModesOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const modesRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modesRef.current && !modesRef.current.contains(e.target as Node)) {
        setModesOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const isPeopleDisabled = !modes.people

  const toggleMode = useCallback((key: string) => {
    if (key !== "people" && !modes.people) return
    const next = { ...modes, [key]: !modes[key] }
    if (key === "people" && !next.people) {
      next.ppe = false
      next.faces = false
    }
    updateDetectModes(next) // оптимистично + сохранение через контекст
  }, [modes, updateDetectModes])

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

  const handleNav = (path: string) => {
    navigate(path)
    setMobileMenuOpen(false)
  }

  const handleStart = useCallback(async () => {
    try {
      await api.start()
      setDetectionRunning(true)
    } catch {
      // ignore
    }
  }, [setDetectionRunning])

  const handleStop = useCallback(async () => {
    try {
      await api.stop()
      setDetectionRunning(false)
    } catch {
      // ignore
    }
  }, [setDetectionRunning])

  return (
    <header style={styles.header}>
      {/* Левая часть: гамбургер (mobile) или навигация (desktop) */}
      <div style={styles.headerLeft}>
        {isMobile ? (
          <button style={styles.hamburger} onClick={() => setMobileMenuOpen((o) => !o)}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        ) : (
          <nav style={styles.nav}>
            <button style={{ ...styles.navBtn, ...(location.pathname === "/" ? styles.navActive : {}) }} onClick={() => navigate("/")}>
              ДАШБОРД
            </button>
            <button style={{ ...styles.navBtn, ...(location.pathname === "/events" ? styles.navActive : {}) }} onClick={() => navigate("/events")}>
              СОБЫТИЯ
            </button>
            <button style={{ ...styles.navBtn, ...(location.pathname === "/archive" ? styles.navActive : {}) }} onClick={() => navigate("/archive")}>
              АРХИВ
            </button>
            <button style={{ ...styles.navBtn, ...(location.pathname === "/zones" ? styles.navActive : {}) }} onClick={() => navigate("/zones")}>
              ЗОНЫ
            </button>
            <button style={{ ...styles.navBtn, ...(location.pathname === "/settings" ? styles.navActive : {}) }} onClick={() => navigate("/settings")}>
              НАСТРОЙКИ
            </button>
          </nav>
        )}
        <div style={styles.logo}>
          <span style={styles.logoText}>Видеоаналитика в реальном времени</span>
        </div>
      </div>

      <div style={styles.headerCenter}>
        <img src="/logo.svg" alt="" style={styles.centerLogo} />
        {!isMobile && <span>Нейроконтролер</span>}
      </div>

      <div style={styles.headerRight}>
        {!isMobile && (
          <div ref={modesRef} style={styles.modesWrapper}>
            <button style={styles.modesBtn} onClick={() => setModesOpen((o) => !o)}>
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
                {Object.entries(MODE_LABELS).map(([key, label]) => {
                  const disabled = key !== "people" && isPeopleDisabled
                  return (
                    <label key={key} style={{ ...styles.modeOption, opacity: disabled ? 0.4 : 1 }}>
                      <input type="checkbox" checked={!!modes[key]} disabled={disabled} onChange={() => toggleMode(key)} style={styles.modeCheckbox} />
                      <span>{label}</span>
                      <span style={{ ...styles.modeDot, background: modes[key] ? "#00e676" : "#333" }} />
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {!isMobile && (
          <div style={styles.clock}>
            <div style={styles.clockTime}>{timeStr}</div>
            <div style={styles.clockDate}>{dateStr}</div>
          </div>
        )}

        {user && (
          <div style={isMobile ? styles.userSectionCompact : styles.userSection}>
            <div style={styles.userAvatar}>
              {user.username.charAt(0).toUpperCase()}
            </div>
            {!isMobile && (
              <div style={styles.userInfo}>
                <div style={styles.userName}>{user.username}</div>
                <div style={styles.userRole}>{user.role}</div>
              </div>
            )}
            <button style={styles.logoutBtn} onClick={handleLogout} title="Выйти">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M6 14H3a1 1 0 01-1-1V3a1 1 0 011-1h3M11 11l3-3-3-3M14 8H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Мобильное меню (полноэкранный overlay) */}
      {isMobile && mobileMenuOpen && (
        <>
          <div style={menuOverlay} onClick={() => setMobileMenuOpen(false)} />
          <div style={menuDrawer}>
            <div style={menuDrawerHeader}>
              <span style={{ fontWeight: 600, color: '#fff', fontSize: '0.9rem' }}>Меню</span>
              <button style={menuCloseBtn} onClick={() => setMobileMenuOpen(false)}>
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M4 4l10 10M14 4l-10 10" stroke="#888" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <button style={menuItem(location.pathname === "/")} onClick={() => handleNav("/")}>
              📺 Дашборд
            </button>
            <button style={menuItem(location.pathname === "/events")} onClick={() => handleNav("/events")}>
              📋 События
            </button>
            <button style={menuItem(location.pathname === "/archive")} onClick={() => handleNav("/archive")}>
              🎞️ Архив
            </button>
            <button style={menuItem(location.pathname === "/zones")} onClick={() => handleNav("/zones")}>
              ✏️ Зоны
            </button>
            <button style={menuItem(location.pathname === "/settings")} onClick={() => handleNav("/settings")}>
              ⚙️ Настройки
            </button>

            <div style={{ borderTop: '1px solid #333', marginTop: 12, paddingTop: 12 }}>
              <div style={{ fontSize: '0.75rem', color: '#888', marginBottom: 8 }}>Режимы детекции</div>
              {Object.entries(MODE_LABELS).map(([key, label]) => {
                const disabled = key !== "people" && isPeopleDisabled
                return (
                  <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', opacity: disabled ? 0.4 : 1 }}>
                    <input type="checkbox" checked={!!modes[key]} disabled={disabled} onChange={() => toggleMode(key)} style={{ accentColor: '#00e676' }} />
                    <span style={{ fontSize: '0.85rem', color: '#ccc' }}>{label}</span>
                  </label>
                )
              })}
            </div>

            <div style={{ borderTop: '1px solid #333', marginTop: 8, paddingTop: 12 }}>
              <button
                onClick={isRunning ? handleStop : handleStart}
                style={{
                  width: '100%',
                  padding: '10px 0',
                  borderRadius: 8,
                  border: 'none',
                  background: isRunning ? '#f4433620' : '#00e67620',
                  color: isRunning ? '#f44336' : '#00e676',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {isRunning ? '⏹ Остановить детекцию' : '▶ Запустить детекцию'}
              </button>
            </div>

            <div style={{ borderTop: '1px solid #333', marginTop: 12, paddingTop: 12 }}>
              <div style={{ fontSize: '0.75rem', color: '#888' }}>{timeStr} · {dateStr}</div>
            </div>
          </div>
        </>
      )}
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
  hamburger: {
    background: 'none',
    border: 'none',
    color: '#888',
    cursor: 'pointer',
    padding: '4px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  userSectionCompact: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    paddingLeft: '8px',
  },
}

const menuOverlay: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 200,
  background: 'rgba(0,0,0,0.5)',
}

const menuDrawer: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  bottom: 0,
  width: '280px',
  zIndex: 201,
  background: '#1a1a1a',
  borderRight: '1px solid #333',
  padding: 16,
  overflow: 'auto',
  animation: 'fadeIn 0.15s ease',
}

const menuDrawerHeader: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 16,
  paddingBottom: 12,
  borderBottom: '1px solid #333',
}

const menuCloseBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#888',
  cursor: 'pointer',
  padding: 4,
}

const menuItem = (active: boolean): React.CSSProperties => ({
  display: 'block',
  width: '100%',
  textAlign: 'left',
  padding: '10px 12px',
  borderRadius: 8,
  background: active ? '#00e67610' : 'transparent',
  border: active ? '1px solid #00e67640' : '1px solid transparent',
  color: active ? '#00e676' : '#ccc',
  cursor: 'pointer',
  fontSize: '0.85rem',
  fontFamily: "'Inter', sans-serif",
  fontWeight: active ? 600 : 400,
  marginBottom: 4,
})
