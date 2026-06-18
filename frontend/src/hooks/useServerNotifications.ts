import { useEffect, useRef } from "react"
import { api } from "../api/client"

const POLL_INTERVAL_MS = 1000

type AddNotification = (type: string, title: string, sub?: string, duration?: number) => void

// Длительность показа по типу уведомления (мс).
const DURATION: Record<string, number> = {
  granted: 5000,
  missing: 4000,
  violation: 4000,
  warning: 3500,
}

// Эмодзи-префикс заголовка по типу.
const ICON: Record<string, string> = {
  granted: "✅ ",
  missing: "⚠️ ",
  violation: "🚨 ",
}

/**
 * Поллит /api/notifications и прокидывает серверные уведомления (жест ОК,
 * нехватка СИЗ и т.п.) в верхнюю панель уведомлений. Источник структурированный,
 * поэтому не зависит от парсинга текста логов и срабатывает ровно один раз.
 */
export function useServerNotifications(addNotification: AddNotification, enabled: boolean) {
  const seen = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!enabled) return
    const poll = async () => {
      try {
        const { notifications } = await api.getNotifications()
        for (const n of notifications) {
          if (seen.current.has(n.id)) continue
          seen.current.add(n.id)
          if (seen.current.size > 300) {
            const oldest = seen.current.values().next().value
            if (oldest) seen.current.delete(oldest)
          }
          addNotification(
            n.type,
            `${ICON[n.type] ?? ""}${n.title}`,
            n.sub,
            DURATION[n.type] ?? 4000,
          )
        }
      } catch {
        // детекция не запущена / сеть — игнорируем
      }
    }
    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [enabled, addNotification])
}
