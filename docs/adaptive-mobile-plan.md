# План адаптивной вёрстки и миграции на React Native (Web + Mobile)

## Условные обозначения

| Метка | Значение |
|-------|----------|
| `[Web]` | Адаптация текущего веб-приложения |
| `[RN]` | Специфично для React Native |
| `[Web+RN]` | Общая логика для обеих платформ |
| `[ ]` | Не начато |
| `[~]` | В работе |
| `[✓]` | Готово |

---

## Фаза 0: Аудит текущего состояния

- [ ] [Web] Зафиксировать все места с фиксированными `px`/`rem` размерами (ширины, отступы, шрифты)
- [ ] [Web] Составить карту всех `style`-объектов для замены на токены
- [ ] [Web+RN] Определить минимальный набор цветовых/типографических токенов

---

## Фаза 1: Design Tokens (3 дня)

- [✓] [Web+RN] Создать `src/design/tokens.ts` — единый источник цветов, отступов, радиусов, теней, типографики
- [ ] [Web+RN] Создать `src/design/theme.ts` — ThemeProvider (dark mode + light mode)
- [✓] [Web] Подключить токены в `index.css` через CSS-переменные
- [ ] [RN] Подготовить StyleSheet-фабрику на основе токенов
- [ ] [Web] Заменить все inline `{ color: "#00e676" }` на `tokens.colors.accent`
- [ ] [Web] Заменить все inline `{ fontFamily: "'Inter', sans-serif" }` на `tokens.typography.fontFamily.web`
- [ ] [Web] Заменить все inline `{ borderRadius: "12px" }` на `tokens.radius.lg`
- [ ] [Web+RN] Создать хук `useTokens()` / `useTheme()` для доступа из компонентов

---

## Фаза 2: Layout Primitives (5 дней)

### 2.1. База
- [✓] [Web+RN] Создать `Box` — универсальный layout-компонент (View/div)
- [ ] [Web+RN] Создать `Text` — единый компонент для текста с токенами
- [✓] [Web+RN] Создать `Flex` — Box с `display: flex` (web) / `View` с `flexDirection` (RN)

### 2.2. Responsive
- [✓] [Web] Создать `useBreakpoint()` на основе `matchMedia`
- [ ] [RN] Создать `useBreakpoint()` на основе `useWindowDimensions`
- [ ] [Web+RN] Создать `ResponsiveGrid` — адаптивная сетка для карточек камер
- [ ] [Web+RN] Создать `AdaptiveSidebar` — сайдбар ↔ BottomSheet ↔ Drawer

### 2.3. Common UI
- [ ] [Web+RN] Обновить `Button` — единый компонент с токенами
- [ ] [Web+RN] Обновить `Input` — единый компонент с токенами
- [ ] [Web+RN] Создать `Modal` — на основе портала (web) / `Modal` (RN)
- [✓] [Web+RN] Создать `BottomSheet` — для мобильных панелей

---

## Фаза 3: Адаптация Dashboard (7 дней)

### 3.1. Макет страницы

**Desktop (≥ 1200px):** 3 колонки (LeftPanel | CameraGrid | RightPanel) — текущий вид

- [✓] [Web] Заменить `gridTemplateColumns: "260px 1fr 260px"` на расчёт от брейкпоинта
- [✓] [Web+RN] Создать `PageContainer` — обёртка с переключением между 3/2/1 колонкой

**Tablet (768–1199px):** 2 колонки (CameraGrid + коллапсируемый сайдбар)

- [ ] [Web+RN] LeftPanel → `ControlSheet` (сворачивается в иконку или вкладку)
- [ ] [Web+RN] RightPanel → `EventsSheet` (сворачивается в иконку или вкладку)
- [ ] [Web+RN] Tabs для переключения между Control/Events на планшете

**Mobile (< 768px):** 1 колонка (Video Carousel + FAB + BottomSheets)

- [ ] [Web+RN] `CameraGrid` → `CameraCarousel` (горизонтальная прокрутка)
- [✓] [Web+RN] ControlPanel и EventsPanel → BottomSheets (по иконке в FAB/menu)
- [~] [Web+RN] Управление запуском/остановкой через FAB — в drawer меню

### 3.2. Header (Desktop ↔ Mobile)

- [✓] [Web] Навигация (Дашборд/События/Настройки) → Hamburger-меню на `< 768px`
- [✓] [Web+RN] Детекция modes dropdown → drawer меню на мобильном
- [✓] [Web+RN] Часы и пользователь → компактная строка
- [ ] [RN] Header адаптировать под SafeAreaView (статус-бар, notch)

### 3.3. DispatcherPanel

- [ ] [Web+RN] Всегда full-screen модальное окно (overlay на всех размерах)
- [ ] [Web+RN] Закрытие по свайпу вниз (touch gesture)
- [ ] [RN] Использовать Native Modal / BottomSheet

---

## Фаза 4: Видео (5 дней)

- [ ] [Web+RN] Создать `VideoPlayer` с платформенной реализацией
- [ ] [Web] Оставить MJPEG через `<img>` + polling fallback
- [ ] [RN] Подключить `expo-av` / `react-native-video` для RTSP/HLS
- [ ] [RN] Рассмотреть `react-native-webrtc` для низкой задержки
- [ ] [Web+RN] Создать `useVideoStream(cameraId)` — возвращает `{ uri, isLoading, error }`
- [ ] [Web+RN] Автоматический fallback между MJPEG / polling / WebRTC
- [ ] [Web+RN] Стоп-кадр при уходе с экрана (экономия батареи)

---

## Фаза 5: Навигация (4 дня)

- [ ] [Web+RN] Создать `NavigationProvider` — единый интерфейс для обоих платформ
- [ ] [Web] Использовать React Router DOM (без изменений)
- [ ] [RN] Подключить React Navigation (Stack + Drawer)
- [ ] [Web+RN] Унифицировать типы маршрутов:

```typescript
type AppRoute = '/' | '/events' | '/settings' | '/login' | '/register'
```

- [ ] [RN] Bottom Tab Navigator: Dashboard | Events | Settings
- [ ] [RN] Drawer Navigator для гамбургер-меню (опционально)
- [ ] [RN] Обработка Deep Links (уведомление → событие)

---

## Фаза 6: Real-time (3 дня)

- [ ] [Web+RN] Создать `useEventStream()` — подписка на события в реальном времени
- [ ] [Web+RN] Выбрать транспорт: SSE vs WebSocket

| Транспорт | Web | RN |
|-----------|-----|-----|
| SSE (`EventSource`) | ✅ Нативно | ❌ Нужен polyfill |
| WebSocket | ✅ Нативно | ✅ Нативно (желательно) |

**Рекомендация: WebSocket** — единый для обеих платформ.

- [ ] [Backend] Добавить `/ws/events` endpoint
- [ ] [Web+RN] Переписать `api.getLogs()` polling на WebSocket
- [ ] [Web+RN] Автоматическое переподключение при обрыве сети
- [ ] [Web+RN] Оптимизация: приостановка WebSocket когда приложение в фоне

---

## Фаза 7: Миграция на React Native (8 дней)

### 7.1. Настройка проекта
- [ ] [RN] Инициализировать проект (Expo или bare RN)
- [ ] [RN] Настроить Metro bundler
- [ ] [RN] Подключить `react-native-web` (опционально, для SSR/браузера)

### 7.2. Перенос компонентов
- [ ] [RN] Перенести `ui/` — Box, Text, Flex, Button, Input, Modal, BottomSheet
- [ ] [RN] Перенести `layout/` — Header, PageContainer, AdaptiveSidebar
- [ ] [RN] Перенести `video/` — VideoPlayer, CameraCarousel, useVideoStream
- [ ] [RN] Перенести `dashboard/` — ControlPanel, EventsPanel, DashboardContent
- [ ] [RN] Перенести `settings/` — CameraManager, SettingsList
- [ ] [RN] Перенести `navigation/` — AppNavigator с React Navigation

### 7.3. Платформенные замены
| Компонент | Web | RN |
|-----------|-----|-----|
| `<img>` | `<img src={...}/>` | `<Image source={{uri:...}}/>` |
| `<video>` | MJPEG/img | `<Video/>` из expo-av |
| `<input>` | `<input/>` | `<TextInput/>` |
| `<select>` | `<select/>` | `Picker` / BottomSheet выбора |
| Scroll | `overflow: auto` | `<ScrollView/>` / `<FlatList/>` |
| Анимации | CSS Transitions/Animations | `Animated` / `Reanimated` |
| Gestures | Mouse/Touch | `GestureHandler` / `Pressable` |
| SafeArea | `padding` / env(safe-area-inset) | `<SafeAreaView/>` |

### 7.4. Контексты и API
- [ ] [RN] `CameraContext` — без изменений (чистый React)
- [ ] [RN] `AuthContext` — заменить `localStorage` на `AsyncStorage`
- [ ] [RN] `api/client.ts` — заменить `fetch` на `axios` или оставить fetch (RN поддерживает)

---

## Чек-лист быстрых побед (можно делать сейчас)

- [ ] [Web] Изменить `Dashboard.tsx:gridTemplateColumns` с `"260px 1fr 260px"` на `"clamp(200px, 20vw, 260px) 1fr clamp(200px, 20vw, 260px)"`
- [ ] [Web] Заменить `fontSize: "0.75rem"` на `fontSize: "clamp(0.65rem, 1.5vw, 0.85rem)"`
- [✓] [Web] Добавить мета-тег viewport в `index.html` (если ещё нет)
- [✓] [Web+RN] Создать `tokens.ts` — вынести все цвета и размеры
- [✓] [Web+RN] Создать `useWindowSize()` — хук для отслеживания размеров окна
- [ ] [Web] Обновить `CameraGrid`: заменить жёсткие колонки на `auto-fit, minmax(300px, 1fr)`

---

## Технические решения

| Решение | Выбор | Обоснование |
|---------|-------|-------------|
| **Сборка мобильного приложения** | Expo (managed workflow) | Быстрый старт, OTA-обновления |
| **Стилизация в RN** | StyleSheet + tokens | Ноль зависимостей, maps 1:1 с текущим кодом |
| **Видео на RN** | expo-av + RTSP | Проверенная библиотека с поддержкой Expo |
| **Real-time транспорт** | WebSocket | Единый для Web и RN, двунаправленный |
| **Навигация RN** | React Navigation v6 (Bottom Tab + Stack) | Стандарт индустрии |
| **Жесты** | react-native-gesture-handler + react-native-reanimated | Для BottomSheet и свайпов |
| **Офлайн/кеш** | AsyncStorage + NetInfo | Базовая обработка офлайна |

---

## Критерии готовности

1. **Web**: Dashboard корректно отображается на 320px, 768px, 1280px, 1920px
2. **Web**: Все элементы интерфейса доступны без горизонтального скролла на≤ 768px
3. **Web**: LeftPanel/RightPanel сворачиваются в BottomSheet на мобильном
4. **Web+RN**: Все компоненты используют единую систему токенов
5. **RN**: Приложение собирается и запускается на iOS Simulator + Android Emulator
6. **RN**: Видео-поток отображается через нативный плеер
7. **RN**: Навигация работает (Dashboard → Events → Settings и обратно)
8. **RN**: Real-time обновления приходят через WebSocket
