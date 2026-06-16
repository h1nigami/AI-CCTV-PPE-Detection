import { useState } from "react"
import { useNavigate, Link } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setBusy(true)
    try {
      await login(username, password)
      navigate("/")
    } catch (err: any) {
      setError(err.message || "Ошибка входа")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={styles.wrapper}>
      <form style={styles.form} onSubmit={handleSubmit}>
        <h1 style={styles.title}>AI-CCTV PPE Detection</h1>
        <h2 style={styles.subtitle}>Вход в систему</h2>

        {error && <div style={styles.error}>{error}</div>}

        <input
          style={styles.input}
          placeholder="Имя пользователя"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <input
          style={styles.input}
          type="password"
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button style={styles.button} type="submit" disabled={busy}>
          {busy ? "Вход..." : "Войти"}
        </button>

        <p style={styles.link}>
          Нет аккаунта? <Link to="/register" style={styles.a}>Зарегистрироваться</Link>
        </p>
      </form>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    height: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#1a1a1a",
    color: "#ffffff",
    fontFamily: "'Inter', sans-serif",
  },
  form: {
    background: "#222",
    padding: "40px",
    borderRadius: "12px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    width: "340px",
    border: "1px solid #333",
  },
  title: {
    margin: 0,
    fontSize: "20px",
    textAlign: "center",
    color: "#00e676",
  },
  subtitle: {
    margin: 0,
    fontSize: "14px",
    textAlign: "center",
    color: "#888",
    fontWeight: 400,
  },
  input: {
    background: "#1a1a1a",
    border: "1px solid #333",
    borderRadius: "8px",
    padding: "12px 16px",
    color: "#ffffff",
    fontSize: "14px",
    outline: "none",
    fontFamily: "'Inter', sans-serif",
  },
  button: {
    background: "#00e676",
    color: "#1a1a1a",
    border: "none",
    borderRadius: "8px",
    padding: "12px",
    fontSize: "15px",
    cursor: "pointer",
    fontWeight: 700,
    fontFamily: "'Inter', sans-serif",
  },
  error: {
    background: "#3e1515",
    border: "1px solid #6b2a2a",
    borderRadius: "8px",
    padding: "10px",
    color: "#f44336",
    fontSize: "13px",
    textAlign: "center",
  },
  link: {
    textAlign: "center",
    fontSize: "13px",
    color: "#888",
    margin: 0,
  },
  a: {
    color: "#00e676",
    textDecoration: "none",
  },
}
