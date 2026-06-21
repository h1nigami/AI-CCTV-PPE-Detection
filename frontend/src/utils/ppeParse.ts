import type { PpeStatus, PersonSummary } from "../types"

// ============================================================
// Разбор статуса СИЗ из текста лог-строки детекции.
// ⚠️ Источник хрупкий (русский текст вида
//   "Людей: 2 | Иван [!К М Ж]: ОПАСНАЯ ЗОНА | Гость [К М Ж]: ПРОПУСК").
// Раньше эта логика дублировалась в ControlPanel и DispatcherPanel —
// вынесена сюда, чтобы парсинг был в одном месте.
// Компактный статус СИЗ в скобках: "!К" — нет каски, "!М" — нет маски,
// "!Ж" — нет жилета (восклицательный знак = отсутствует).
// ============================================================

const EMPTY_PPE: PpeStatus = {
  helmet: null,
  mask: null,
  vest: null,
  zone: null,
  gesture: null,
}

/** Разбивает сообщение на части-людей (отбрасывая "Людей:" и "Нет СИЗ"). */
export function splitPersonParts(message: string): string[] {
  return message.split(" | ").filter((p) => {
    if (p.startsWith("Людей:") || p.startsWith("Нет СИЗ")) return false
    return /^[^\[\:]+(?:\[.*?\])?\s*:\s/.test(p)
  })
}

/**
 * Агрегированный статус СИЗ по кадру (одна камера / одно сообщение).
 * Если данных о людях нет или ни у кого нет блока СИЗ — всё null ("Ожидание").
 */
export function parsePpeFromMessage(message: string | undefined): PpeStatus {
  if (!message || !message.includes("Людей:")) return { ...EMPTY_PPE }

  const personParts = splitPersonParts(message)
  const hasPpeBrackets = personParts.some((p) => /\[.*?\]/.test(p))
  if (!hasPpeBrackets) return { ...EMPTY_PPE }

  let helmetOk = true
  let maskOk = true
  let vestOk = true
  let inDanger = false
  let hasPass = false

  for (const part of personParts) {
    const ppeMatch = part.match(/\[(.*?)\]/)
    if (ppeMatch) {
      const ppeStr = ppeMatch[1]
      if (ppeStr.includes("!К")) helmetOk = false
      if (ppeStr.includes("!М")) maskOk = false
      if (ppeStr.includes("!Ж")) vestOk = false
    }
    if (part.includes("ОПАСНАЯ ЗОНА")) inDanger = true
    if (part.includes("ПРОПУСК")) hasPass = true
  }

  return {
    helmet: helmetOk,
    mask: maskOk,
    vest: vestOk,
    zone: !inDanger,
    gesture: hasPass,
  }
}

/** Список людей в кадре с их компактным статусом СИЗ. */
export function parsePersonsFromMessage(message: string | undefined): PersonSummary[] {
  if (!message) return []
  return splitPersonParts(message).map((part, idx) => {
    const ppeMatch = part.match(/\[(.*?)\]/)
    const ppeStr = ppeMatch ? ppeMatch[1] + " " : ""
    const nameMatch = part.match(/^([^[]+?)\s*\[/)
    const name = nameMatch ? nameMatch[1].trim() : part.split(":")[0].trim()
    return {
      name,
      ppe: ppeStr,
      approved: part.includes("ПРОПУСК"),
      danger: part.includes("ОПАСНАЯ"),
      violation: ppeStr.includes("!К") || ppeStr.includes("!М") || ppeStr.includes("!Ж"),
      index: idx,
    }
  })
}

/** Количество людей в кадре из "Людей: N". */
export function parsePeopleCount(message: string | undefined): number {
  if (!message) return 0
  const m = message.match(/Людей:\s*(\d+)/)
  return m ? parseInt(m[1]) : 0
}
