import { useState, useEffect, useCallback } from "react"
import { api } from "../api/client"
import type { Cameras, CameraInfo } from "../types"

export function useCameras() {
  const [cameras, setCameras] = useState<Cameras>({})
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await api.getCameras()
      setCameras(data.cameras)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const cameraList: CameraInfo[] = Object.entries(cameras).map(([name, cfg]) => ({
    name,
    source: typeof cfg === "object" && cfg !== null ? cfg.source : cfg,
    detect_enabled: typeof cfg === "object" && cfg !== null ? cfg.detect_enabled : true,
  }))

  return { cameras, cameraList, loading, refresh }
}
