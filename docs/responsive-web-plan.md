# План адаптивной вёрстки (Web)

## Брейкпоинты

| Уровень | Ширина | Layout | Header |
|---------|--------|--------|--------|
| Desktop | ≥ 1200px | 3 колонки (LeftPanel \| Grid \| RightPanel) | Tabs visible |
| Tablet | 768–1199px | 2 колонки (Grid + Collapsible Sidebar) | Tabs + collapse btn |
| Mobile | < 768px | 1 колонка + BottomSheets | Hamburger + FAB |

---

## Условные обозначения

- `[ ]` — не начато
- `[~]` — в работе
- `[✓]` — готово

---

## Этап 0: Токены и брейкпоинты (~1 день)

- [ ] Создать `src/design/tokens.ts` — цвета, радиусы, отступы, шрифты, тени
- [ ] Подключить токены через CSS-переменные в `index.css`
- [ ] Создать `src/hooks/useBreakpoint.ts` на основе `matchMedia`
- [ ] Определить брейкпоинты: `mobile: 768`, `tablet: 1200`

---

## Этап 1: Layout Primitives (~1-2 дня)

- [ ] `Box` — универсальный div с props: `p`, `m`, `gap`, `flex`, `width`
- [ ] `Flex` — Box с `display: flex` + `direction`, `align`, `justify`, `wrap`
- [ ] `Grid` — CSS Grid wrapper: `columns`, `gap`, `minItemWidth`
- [ ] `Responsive` — условный рендер `<Responsive mobile={...} tablet={...} desktop={...} />`

---

## Этап 2: Dashboard — 3 брейкпоинта (~3-4 дня)

### Desktop (≥ 1200px) — текущее состояние
- [ ] Левая панель (фиксированная ширина)
- [ ] CameraGrid (1-3 колонки)
- [ ] Правая панель (фиксированная ширина)

### Tablet (768–1199px) — 2 колонки
- [ ] LeftPanel + RightPanel → общий `Sidebar` с табами (Управление / События / Статус)
- [ ] Сайдбар сворачивается по кнопке в Header
- [ ] CameraGrid: 2 колонки

### Mobile (< 768px) — 1 колонка
- [ ] `CameraGrid` → `CameraCarousel` (горизонтальный скролл, snap-x)
- [ ] `LeftPanel`/`RightPanel` → BottomSheets (FAB + иконка в Header)
- [ ] Header: сайдбар с навигацией (гамбургер)
- [ ] Детекция modes → BottomSheet
- [ ] FAB: запуск/остановка детекции

---

## Этап 3: Компоненты-панели (~2 дня)

- [ ] `ControlPanel` — props: `variant: 'sidebar' | 'sheet'` (отвечает за LeftPanel)
- [ ] `EventsPanel` — props: `variant: 'sidebar' | 'sheet'` (отвечает за RightPanel)
- [ ] BottomSheet с CSS-анимацией (`transform: translateY`)
- [ ] Header: `HamburgerMenu` + `ModesBottomSheet`

---

## Этап 4: Типографика и отступы (~0.5 дня)

- [ ] `fontSize`: `rem` → `clamp(min, preferred, max)`
- [ ] `padding`, `gap`, `margin`: фиксированные px → CSS-переменные (`var(--spacing-md)`)
- [ ] Проверить читаемость на 320px

---

## Этап 5: Тестирование и полировка (~1 день)

- [ ] Chrome DevTools: 320, 375, 414, 768, 1024, 1280, 1920
- [ ] Нет горизонтального скролла
- [ ] Тач-таргеты ≥ 44×44px
- [ ] `overflow: hidden` не ломает скролл на мобильном

---

## Оценка: ~7-9 дней

### Порядок PR

1. `feat/design-tokens`
2. `feat/layout-primitives`
3. `feat/dashboard-responsive`
4. `feat/panels-adaptive`
5. `feat/typography-fluid`
6. `feat/polish-testing`
