import { useState, useEffect, useCallback } from "react"
import { api } from "../api/client"
import type { Cameras } from "../types"

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

  const cameraList = Object.entries(cameras).map(([name, source]) => ({
    name,
    source,
  }))

  return { cameras, cameraList, loading, refresh }
}
