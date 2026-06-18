import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Бэкенд развёрнут на удалённом GPU-сервере; локальный dev-фронт ходит на него
// через proxy. Адрес переопределяется переменной окружения VITE_API_TARGET.
const API_TARGET = process.env.VITE_API_TARGET || "http://192.168.0.97:8000"

// Все префиксы, которые фронт шлёт на бэкенд (см. src/api/client.ts).
const proxyPaths = [
  "/video_frame",
  "/video_feed",
  "/api",
  "/start",
  "/stop",
  "/cameras",
  "/detection_log",
  "/export_logs",
  "/upload",
]

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      proxyPaths.map((p) => [p, { target: API_TARGET, changeOrigin: true }]),
    ),
  },
})
