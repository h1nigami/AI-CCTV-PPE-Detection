import { useEffect, useRef } from "react"
import { api } from "../api/client"

const POLL_INTERVAL_MS = 2000

export function useVoiceAlerts(enabled: boolean) {
  // Курсор последнего полученного алерта (seq на бэке). undefined — клиент ещё не
  // инициализирован: первый опрос лишь узнаёт текущий курсор и НЕ переигрывает
  // накопившийся бэклог. Дальше шлём ?after=cursor и получаем только новые.
  const cursorRef = useRef<number | undefined>(undefined)
  // Очередь текстов на проигрывание + флаг «сейчас играет»: алерты нескольких
  // камер проигрываются ПОСЛЕДОВАТЕЛЬНО, а не накладываются друг на друга.
  const queueRef = useRef<string[]>([])
  const playingRef = useRef(false)
  // Кэш голосов Web Speech (фоллбэк). В Chrome getVoices() при первом вызове
  // пуст — голоса подгружаются асинхронно (событие voiceschanged). Если читать
  // их в момент speak, русский голос не находится и кириллицу озвучивает
  // дефолтный (английский) голос — «быстро и неразборчиво».
  const voicesRef = useRef<SpeechSynthesisVoice[]>([])

  useEffect(() => {
    if (!enabled) return

    // Переинициализация при включении: с «чистого листа», без бэклога.
    cursorRef.current = undefined
    queueRef.current = []
    playingRef.current = false

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

    // Озвучка через Web Speech; промис резолвится по ОКОНЧАНИИ речи (для очереди).
    const speakWebSpeech = (text: string): Promise<void> =>
      new Promise((resolve) => {
        if (!synth) return resolve()
        const ruVoice = pickRuVoice()
        if (!ruVoice) {
          console.warn(
            "[voice] Бэкенд-TTS недоступен и русский голос ОС не найден — " +
              "озвучка пропущена. Установите русский TTS-голос или включите Piper.",
          )
          return resolve()
        }
        const utter = new SpeechSynthesisUtterance(text)
        utter.voice = ruVoice
        utter.lang = ruVoice.lang
        utter.rate = 0.95
        utter.pitch = 1.0
        utter.volume = 1.0
        utter.onend = () => resolve()
        utter.onerror = () => resolve()
        synth.resume() // Chrome иногда «засыпает» — нативный воркэраунд
        synth.speak(utter)
      })

    // ── Основной путь: готовый WAV с бэкенда (Piper, не зависит от ОС) ──
    // Промис резолвится по ОКОНЧАНИИ воспроизведения (true) либо при недоступности
    // бэкенд-TTS/ошибке/блокировке autoplay (false → фоллбэк на Web Speech).
    const playBackendAudio = (text: string): Promise<boolean> =>
      new Promise((resolve) => {
        let settled = false
        const finish = (ok: boolean, url?: string) => {
          if (settled) return
          settled = true
          if (url) URL.revokeObjectURL(url)
          resolve(ok)
        }
        ;(async () => {
          try {
            const resp = await fetch(api.getVoiceAlertAudioUrl(text))
            if (!resp.ok) return finish(false) // 503 — TTS на бэке выключен/недоступен
            const blob = await resp.blob()
            const url = URL.createObjectURL(blob)
            const audio = new Audio(url)
            // Страховка от зависшего промиса (onended не пришёл) — очередь не должна
            // встать навсегда. Алерты короткие, 20с с запасом.
            const guard = window.setTimeout(() => finish(true, url), 20000)
            audio.onended = () => {
              window.clearTimeout(guard)
              finish(true, url)
            }
            audio.onerror = () => {
              window.clearTimeout(guard)
              finish(false, url)
            }
            try {
              await audio.play() // может отклониться autoplay-политикой → фоллбэк
            } catch {
              window.clearTimeout(guard)
              finish(false, url)
            }
          } catch {
            finish(false)
          }
        })()
      })

    // Последовательное проигрывание очереди — по одному алерту за раз.
    const drain = async () => {
      if (playingRef.current) return
      playingRef.current = true
      try {
        while (queueRef.current.length) {
          const text = queueRef.current.shift()!
          const played = await playBackendAudio(text)
          if (!played) await speakWebSpeech(text)
        }
      } finally {
        playingRef.current = false
      }
    }

    const poll = async () => {
      try {
        const { alerts, cursor } = await api.getVoiceAlerts(cursorRef.current)
        const firstPoll = cursorRef.current === undefined
        cursorRef.current = cursor
        if (firstPoll) return // только инициализация курсора, без проигрывания бэклога
        if (alerts.length) {
          for (const a of alerts) if (a.text) queueRef.current.push(a.text)
          // Ограничиваем очередь последними алертами — иначе при подвисании
          // воспроизведения накапливается бэклог и проигрывается задним числом.
          if (queueRef.current.length > 3) queueRef.current = queueRef.current.slice(-3)
          void drain()
        }
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
