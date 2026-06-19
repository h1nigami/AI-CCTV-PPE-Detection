"""Формирование текста голосовой тревоги по статусам СИЗ.

Чистая функция (без тяжёлых зависимостей вроде ultralytics) — вынесена из
`backend/main.py`, чтобы быть юнит-тестируемой без загрузки YOLO/InsightFace.
`main.py` реэкспортирует её как `_build_voice_text` для совместимости.
"""


def build_voice_text(statuses: dict, person_name: str) -> str:
    """Сформировать текст голосового предупреждения по статусам СИЗ.

    Статус-строка: 'КМЖз' — позиции 0=каска, 1=маска, 2=жилет, 3=зона;
    заглавная = есть, строчная = нет.

    Озвучиваем ТОЛЬКО реальное нарушение В опасной зоне (человек внутри зоны
    без СИЗ). Если нарушение СИЗ есть, но человек ВНЕ зоны — возвращаем ''
    (пустую строку), чтобы не проигрывать ложное «в опасной зоне» (категория
    «нарушение» в пайплайне срабатывает и на отсутствие СИЗ вне зоны).
    """
    missing = []
    zone_violation = False
    for status in statuses.values():
        if len(status) >= 4 and status[3] == 'З':  # человек в зоне
            person_missing = []
            if status[0] == 'к':
                person_missing.append('каска')
            if status[1] == 'м':
                person_missing.append('маска')
            if status[2] == 'ж':
                person_missing.append('жилет')
            if person_missing:
                zone_violation = True
                for item in person_missing:
                    if item not in missing:
                        missing.append(item)
    if not zone_violation:
        return ""
    who = person_name if person_name else "Человек"
    if missing:
        return f"Внимание! {who} в опасной зоне. Нет СИЗ: {', '.join(missing)}"
    return f"Внимание! {who} вошёл в опасную зону без необходимых средств защиты"
