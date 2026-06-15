import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/video_frame": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/start": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/stop": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/cameras": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/detection_log": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/export_logs": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/upload": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
})
