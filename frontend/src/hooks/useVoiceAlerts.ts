import { useEffect, useRef } from "react"
import { api } from "../api/client"

const POLL_INTERVAL_MS = 2000

export function useVoiceAlerts(enabled: boolean) {
  const seenIds = useRef<Set<string>>(new Set())
  // Кэш голосов синтеза. В Chrome getVoices() при первом вызове пуст —
  // голоса подгружаются асинхронно (событие voiceschanged). Если читать
  // их прямо в момент speak, русский голос не находится и кириллицу
  // озвучивает дефолтный (английский) голос — «быстро и неразборчиво».
  const voicesRef = useRef<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    if (!enabled) return

    const synth = typeof window !== "undefined" ? window.speechSynthesis : null
    if (!synth) return

    // Подгружаем и кэшируем список голосов заранее
    const loadVoices = () => {
      const v = synth.getVoices()
      if (v.length) voicesRef.current = v
    }
    loadVoices()
    synth.addEventListener("voiceschanged", loadVoices)

    const pickRuVoice = (): SpeechSynthesisVoice | null => {
      const voices = voicesRef.current.length
        ? voicesRef.current
        : synth.getVoices()
      if (voices.length && !voicesRef.current.length) voicesRef.current = voices
      // Точное совпадение ru-RU предпочтительнее любого ru-*
      return (
        voices.find((v) => v.lang.toLowerCase() === "ru-ru") ||
        voices.find((v) => v.lang.toLowerCase().startsWith("ru")) ||
        null
      )
    }

    const speak = (text: string) => {
      const ruVoice = pickRuVoice()
      // Нет русского голоса в системе — кириллицу нормально не озвучить,
      // лучше не «тараторить» английским голосом. Предупреждаем в консоль.
      if (!ruVoice) {
        console.warn(
          "[voice] Русский голос синтеза не найден — озвучка пропущена. " +
            "Установите русский TTS-голос в системе/браузере.",
        )
        return
      }

      const utter = new SpeechSynthesisUtterance(text)
      utter.voice = ruVoice
      utter.lang = ruVoice.lang
      utter.rate = 0.95
      utter.pitch = 1.0
      utter.volume = 1.0

      // Chrome иногда «засыпает» — нативный воркэраунд: resume перед speak
      synth.resume()
      synth.speak(utter)
    }

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
        speak(alert.text)
      } catch {
        // сеть недоступна или детекция не запущена — игнорируем
      }
    }

    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      clearInterval(timer)
      synth.removeEventListener("voiceschanged", loadVoices)
    }
  }, [enabled])
}
