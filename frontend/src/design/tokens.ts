export const breakpoints = {
  mobile: 768,
  tablet: 1200,
} as const

export const colors = {
  bg: '#1a1a1a',
  panel: '#222222',
  panel2: '#2a2a2a',
  panel3: '#333333',
  border: '#333333',
  accent: '#00e676',
  red: '#f44336',
  orange: '#ff9800',
  yellow: '#ffd600',
  blue: '#00b0ff',
  cyan: '#00e5ff',
  text: '#ffffff',
  textDim: '#888888',
  textMid: '#cccccc',
  textMuted: '#aaaaaa',
} as const

export const spacing = {
  xs: 4,
  sm: 6,
  md: 10,
  lg: 12,
  xl: 16,
  xxl: 24,
  xxxl: 32,
} as const

export const radius = {
  xs: 2,
  sm: 4,
  md: 6,
  lg: 8,
  xl: 12,
  full: '50%',
} as const

export const fontSize = {
  xs: 'clamp(0.55rem, 1.2vw, 0.6rem)',
  sm: 'clamp(0.6rem, 1.5vw, 0.65rem)',
  md: 'clamp(0.65rem, 1.8vw, 0.7rem)',
  lg: 'clamp(0.7rem, 2vw, 0.75rem)',
  xl: 'clamp(0.75rem, 2.2vw, 0.8rem)',
  xxl: 'clamp(0.8rem, 2.5vw, 0.85rem)',
  xxxl: 'clamp(0.9rem, 2.8vw, 1rem)',
  hero: 'clamp(2.5rem, 8vw, 4rem)',
} as const

export const fontWeight = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  extrabold: 800,
} as const

export const fontFamily = {
  sans: "'Inter', sans-serif",
  mono: 'monospace',
} as const

export const zIndex = {
  base: 1,
  header: 100,
  dropdown: 1000,
  modal: 500,
  overlay: 500,
  toast: 1000,
} as const
