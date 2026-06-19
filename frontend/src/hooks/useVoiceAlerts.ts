import { useEffect, useRef } from "react"
import { api } from "../api/client"

const POLL_INTERVAL_MS = 2000

export function useVoiceAlerts(enabled: boolean) {
  const seenIds = useRef<Set<string>>(new Set())
  // Кэш голосов Web Speech (фоллбэк). В Chrome getVoices() при первом вызове
  // пуст — голоса подгружаются асинхронно (событие voiceschanged). Если читать
  // их в момент speak, русский голос не находится и кириллицу озвучивает
  // дефолтный (английский) голос — «быстро и неразборчиво».
  const voicesRef = useRef<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    if (!enabled) return

    const synth = typeof window !== "undefined" ? window.speechSynthesis : null

    // ── Фоллбэк: Web Speech API (зависит от TTS-голосов ОС) ──
    const loadVoices = () => {
      if (!synth) return
      const v = synth.getVoices()
      if (v.length) voicesRef.current = v
    }
    loadVoices()
    synth?.addEventListener("voiceschanged", loadVoices)

    const pickRuVoice = (): SpeechSynthesisVoice | null => {
      if (!synth) return null
      const voices = voicesRef.current.length
        ? voicesRef.current
        : synth.getVoices()
      if (voices.length && !voicesRef.current.length) voicesRef.current = voices
      return (
        voices.find((v) => v.lang.toLowerCase() === "ru-ru") ||
        voices.find((v) => v.lang.toLowerCase().startsWith("ru")) ||
        null
      )
    }

    const speakWebSpeech = (text: string) => {
      if (!synth) return
      const ruVoice = pickRuVoice()
      if (!ruVoice) {
        console.warn(
          "[voice] Бэкенд-TTS недоступен и русский голос ОС не найден — " +
            "озвучка пропущена. Установите русский TTS-голос или включите Piper.",
        )
        return
      }
      const utter = new SpeechSynthesisUtterance(text)
      utter.voice = ruVoice
      utter.lang = ruVoice.lang
      utter.rate = 0.95
      utter.pitch = 1.0
      utter.volume = 1.0
      synth.resume() // Chrome иногда «засыпает» — нативный воркэраунд
      synth.speak(utter)
    }

    // ── Основной путь: готовый WAV с бэкенда (Piper, не зависит от ОС) ──
    const playBackendAudio = async (text: string): Promise<boolean> => {
      try {
        const resp = await fetch(api.getVoiceAlertAudioUrl(text))
        if (!resp.ok) return false // 503 — TTS на бэке выключен/недоступен
        const blob = await resp.blob()
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.onended = () => URL.revokeObjectURL(url)
        audio.onerror = () => URL.revokeObjectURL(url)
        await audio.play() // может отклониться autoplay-политикой → фоллбэк
        return true
      } catch {
        return false
      }
    }

    const poll = async () => {
      try {
        const alert = await api.getVoiceAlert()
        if (!alert.id) return
        if (seenIds.current.has(alert.id)) return

        seenIds.current.add(alert.id)
        if (seenIds.current.size > 200) {
          const oldest = seenIds.current.values().next().value
          if (oldest) seenIds.current.delete(oldest)
        }

        if (!alert.text) return
        // Сначала пробуем серверный синтез; при неудаче — Web Speech.
        const played = await playBackendAudio(alert.text)
        if (!played) speakWebSpeech(alert.text)
      } catch {
        // сеть недоступна или детекция не запущена — игнорируем
      }
    }

    const timer = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      clearInterval(timer)
      synth?.removeEventListener("voiceschanged", loadVoices)
    }
  }, [enabled])
}
