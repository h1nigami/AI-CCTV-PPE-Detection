import { useEffect, useRef } from "react"
import { api } from "../api/client"

const POLL_INTERVAL_MS = 2000

export function useVoiceAlerts(enabled: boolean) {
  const seenIds = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!enabled) return

    const synth = typeof window !== "undefined" ? window.speechSynthesis : null
    if (!synth) return

    const poll = async () => {
      try {
        const alert = await api.getVoiceAlert()
        if (!alert.id) return
        if (seenIds.current.has(alert.id)) return

        seenIds.current.add(alert.id)
        // Не давать сету расти бесконечно
        if (seenIds.current.size > 200) {
          const oldest = seenIds.current.values().next().value
          if (oldest) seenIds.current.delete(oldest)
        }

        if (!alert.text) return

        const utter = new SpeechSynthesisUtterance(alert.text)
        utter.lang = "ru-RU"
        utter.rate = 0.9
        utter.volume = 1.0

        // Подобрать русский голос, если доступен
        const voices = synth.getVoices()
        const ruVoice = voices.find((v) => v.lang.startsWith("ru"))
        if (ruVoice) utter.voice = ruVoice

        synth.speak(utter)
      } catch {
        // сеть недоступна или детекция не запущена — игнорируем
      }
    }

    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [enabled])
}
