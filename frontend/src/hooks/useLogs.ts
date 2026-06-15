import { useState, useEffect, useRef, useCallback } from "react"
import { api } from "../api/client"
import type { LogEntry } from "../types"

export function useLogs(enabled: boolean, selectedCam: string | null) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetch = useCallback(async () => {
    try {
      const data = await api.getLogs(selectedCam ?? undefined)
      setLogs(data.logs)
    } catch {
      // ignore
    }
  }, [selectedCam])

  useEffect(() => {
    if (!enabled) {
      setLogs([])
      return
    }
    fetch()
    intervalRef.current = setInterval(fetch, 1000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [enabled, fetch])

  return logs
}
