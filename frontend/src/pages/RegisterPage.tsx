import { useState } from "react"
import { useNavigate, Link } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (password !== confirm) {
      setError("Пароли не совпадают")
      return
    }
    setBusy(true)
    try {
      await register(username, password)
      navigate("/login")
    } catch (err: any) {
      setError(err.message || "Ошибка регистрации")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={styles.wrapper}>
      <form style={styles.form} onSubmit={handleSubmit}>
        <h1 style={styles.title}>AI-CCTV PPE Detection</h1>
        <h2 style={styles.subtitle}>Регистрация</h2>

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
        <input
          style={styles.input}
          type="password"
          placeholder="Подтвердите пароль"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />

        <button style={styles.button} type="submit" disabled={busy}>
          {busy ? "Регистрация..." : "Зарегистрироваться"}
        </button>

        <p style={styles.link}>
          Уже есть аккаунт? <Link to="/login" style={styles.a}>Войти</Link>
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
    background: "#080d14",
    color: "#c8dff0",
    fontFamily: "'Exo 2', sans-serif",
  },
  form: {
    background: "#101a24",
    padding: "40px",
    borderRadius: "12px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
    width: "340px",
    border: "1px solid #1e2d3d",
  },
  title: {
    margin: 0,
    fontSize: "20px",
    textAlign: "center",
    color: "#4fc3f7",
  },
  subtitle: {
    margin: 0,
    fontSize: "14px",
    textAlign: "center",
    color: "#8899aa",
    fontWeight: 400,
  },
  input: {
    background: "#0d1520",
    border: "1px solid #1e2d3d",
    borderRadius: "8px",
    padding: "12px 16px",
    color: "#c8dff0",
    fontSize: "14px",
    outline: "none",
  },
  button: {
    background: "#1565c0",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    padding: "12px",
    fontSize: "15px",
    cursor: "pointer",
    fontWeight: 600,
  },
  error: {
    background: "#3e1515",
    border: "1px solid #6b2a2a",
    borderRadius: "8px",
    padding: "10px",
    color: "#ff8a80",
    fontSize: "13px",
    textAlign: "center",
  },
  link: {
    textAlign: "center",
    fontSize: "13px",
    color: "#667788",
    margin: 0,
  },
  a: {
    color: "#4fc3f7",
    textDecoration: "none",
  },
}
