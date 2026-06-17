# Phase 0 — Style Audit

## Total hardcoded values across 17 files + 3 clean files

### Colors
Most frequent:
| Color | Occurrences | Primary uses |
|-------|-------------|--------------|
| `#1a1a1a` | 7 files | page/card/panel backgrounds |
| `#333` / `#333333` | 14 files | borders, separators |
| `#888` / `#888888` | 16 files | muted/secondary text, borders |
| `#00e676` | 16 files | accent green, active states, buttons |
| `#f44336` | 10 files | danger, offline, violations |
| `#222` / `#222222` | 9 files | card/modal/dropdown backgrounds |
| `#2a2a2a` | 7 files | secondary card/item backgrounds |
| `#111` | 4 files | dark backgrounds, overlays |
| `#ffffff` | 8 files | primary text |
| `#ccc` | 4 files | secondary text |
| `#33333380` / `#000000cc` / `rgba(...)` | 6 files | overlays, shadows |

### PX values (non-exhaustive, top repeated)
| Value | Files | Used for |
|-------|-------|----------|
| `16px` | 10+ | padding, gap |
| `12px` | 12+ | padding, gap, borderRadius |
| `8px` | 12+ | gap, padding, borderRadius |
| `6px` | 10+ | gap, padding, width/height dots |
| `4px` | 12+ | gap, padding, border |
| `10px` | 8+ | gap, padding |
| `24px` | 4+ | header padding |
| `56px` | 1 (Header) | header height |
| `260px` | 1 (Dashboard) | sidebar width |
| `420px` | 1 (Dispatcher) | panel width |
| `90vw` / `80vh` | 3 modals | modal sizing |
| `48`/`48px` | 3 files | FAB/svg sizing |
| `40px` | 3 files | svg/spinner sizing |

### REM values
`0.55rem` → `1.4rem` across all files. Most common sizes:
- `0.65rem` (small labels, timestamps)
- `0.75rem` (body text, secondary info)
- `0.85rem` (titles, buttons)
- `1rem` (headings)
- LoginPage uses raw `px` font-sizes (`20px`, `14px`, etc.) — no rem at all.

### fontFamily
- `"'Inter', sans-serif"` — 16 files, the primary UI font
- `"monospace"` — 6 files, for camera sources, timestamps, metrics, code-style data

### borderRadius
| Value | Files |
|-------|-------|
| `8px` | 12+ files |
| `6px` | 10+ files |
| `12px` | 10+ files |
| `50%` | 7 files (circles) |
| `4px` | 4 files |
| `2px` | 4 files (badges) |
| `3px` | 1 file (badges) |

### zIndex layers
| Value | Usage |
|-------|-------|
| `3` | topBar/bottomBar/spinner overlays (camera cards) |
| `10` | CameraGrid exitHint |
| `100` | Header |
| `200` | Header menuOverlay |
| `201` | Header menuDrawer |
| `400` | Dashboard mobileFabs |
| `500` | Dashboard overlay, Gallery modal, CameraManager modal |
| `600` | BottomSheet backdrop |
| `1000` | Header modesDropdown |
| `9999` | Notifications container |

### Custom animations
| Name | Used in |
|------|---------|
| `spin 0.8s linear infinite` | CameraCell, CameraCard |
| `blink 1.2s ease-in-out infinite` | CameraCard (violation badge) |
| `fadeIn 0.15s ease` | Header (menuDrawer) |
| `fadeIn .25s ease` | RightPanel (logItem) |
| `notifIn 0.5s cubic-bezier(...)` | Notifications |
| `notifOut 0.35s ease-in forwards` | Notifications |
| `sheetUp 0.25s ease` | BottomSheet |

---

## Files with zero hardcoded values (already token-ready)
1. `ui/Responsive.tsx` — no inline styles
2. `ui/Flex.tsx` — all dynamic via props
3. `ui/Box.tsx` — all dynamic via props

---

## Component style object map

### Components with `const styles: Record<string, React.CSSProperties> = {...}`
| File | Style keys count | Needs refactor priority |
|------|-----------------|------------------------|
| CameraCard.tsx | ~25 keys | High |
| Header.tsx | ~25 keys | High |
| DispatcherPanel.tsx | ~30 keys | High |
| LeftPanel.tsx | ~35 keys | High |
| RightPanel.tsx | ~20 keys | High |
| CameraGrid.tsx | ~10 keys | Medium |
| GalleryModal.tsx | ~25 keys | Medium |
| CameraManagerModal.tsx | ~25 keys | Medium |
| Notifications.tsx | ~15 keys | Medium |
| BottomSheet.tsx | ~8 keys | Low (already uses tokens partially) |
| Grid.tsx | ~5 keys | Low (primitive) |

### Components with inline `style={{...}}` scattered in JSX
| File | Occurrences | Needs refactor priority |
|------|-------------|------------------------|
| Dashboard.tsx | ~20 inline | High |
| Header.tsx | ~15 inline | High |
| DispatcherPanel.tsx | ~10 inline | Medium |
| SettingsPage.tsx | ~15 inline | Medium |
| LoginPage.tsx | ~15 inline | Medium |
| RegisterPage.tsx | ~15 inline | Medium |
| EventsPage.tsx | ~5 inline | Low |

---

## Minimal token set needed

```typescript
// tokens.ts (existing — needs expansion)
export const colors = {
  bg:        { page: "#1a1a1a", card: "#222", surface: "#2a2a2a", overlay: "#111" },
  border:    { default: "#333", light: "#444", focus: "#00e67640" },
  text:      { primary: "#fff", secondary: "#ccc", muted: "#888", accent: "#00e676" },
  status:    { online: "#00e676", offline: "#f44336", error: "#ff9800", warning: "#ffd600" },
  semantic:  { success: "#00e676", danger: "#f44336", info: "#00b0ff", warning: "#ffd600" },
  // gradients
}

export const spacing = {
  xs: "4px", sm: "8px", md: "12px", lg: "16px", xl: "24px",
  headerH: "56px", sidebarW: "260px", fab: "48px",
}

export const radius = {
  sm: "4px", md: "6px", lg: "8px", xl: "12px", round: "50%", pill: "999px",
}

export const fontSize = {
  xs: "0.55rem", sm: "0.65rem", base: "0.75rem", md: "0.85rem",
  lg: "1rem", xl: "1.25rem", xxl: "1.4rem", hero: "4rem",
}

export const fontFamily = {
  ui: "'Inter', sans-serif",
  mono: "monospace",
}

export const zIndex = {
  cardOverlay: 3, header: 100, drawer: 200, fab: 400,
  modal: 500, sheet: 600, dropdown: 1000, notification: 9999,
}

export const animation = {
  spin: "spin 0.8s linear infinite",
  blink: "blink 1.2s ease-in-out infinite",
  fadeIn: "fadeIn 0.15s ease",
  sheetUp: "sheetUp 0.25s ease",
  notifIn: "notifIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards",
  notifOut: "notifOut 0.35s ease-in forwards",
}
```

---

## Replace priority order (by value density)
1. **Colors** — 17 files, hundreds of inline hex values
2. **fontFamily** — 16 files `'Inter', sans-serif`, 6 files `monospace`
3. **borderRadius** — 12+ files with 5 distinct values
4. **spacing (px)** — all files, highly repetitive values
5. **fontSize (rem)** — all files, 9 distinct values
6. **zIndex** — 9 layers across 7 files
7. **animations** — 6 named animations across 4 files
