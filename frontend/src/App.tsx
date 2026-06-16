import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider, useAuth } from "./contexts/AuthContext"
import { CameraProvider } from "./contexts/CameraContext"
import { Header } from "./components/Header"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import DashboardPage from "./pages/Dashboard"
import EventsPage from "./pages/EventsPage"
import SettingsPage from "./pages/SettingsPage"

// ============================================================
// Корневой компонент приложения.
// Роутинг, провайдеры, защита маршрутов.
// ============================================================

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuth, loading } = useAuth()
  if (loading) return null
  if (!isAuth) return <Navigate to="/login" replace />
  return <>{children}</>
}

function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <CameraProvider>
        <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Header />
          {children}
        </div>
      </CameraProvider>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Публичные страницы */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Защищённые страницы */}
          <Route
            path="/"
            element={
              <ProtectedLayout>
                <DashboardPage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/events"
            element={
              <ProtectedLayout>
                <EventsPage />
              </ProtectedLayout>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedLayout>
                <SettingsPage />
              </ProtectedLayout>
            }
          />

          {/* Редирект на дашборд по умолчанию */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
