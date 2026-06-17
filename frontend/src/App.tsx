import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom"
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

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <CameraProvider>
        <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Header />
          <Outlet />
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

          {/* Защищённые страницы — layout один для всех */}
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          {/* Редирект на дашборд по умолчанию */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
