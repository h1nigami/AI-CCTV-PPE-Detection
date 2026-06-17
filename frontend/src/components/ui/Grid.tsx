import type { CSSProperties, ReactNode } from 'react'

interface GridProps {
  children?: ReactNode
  style?: CSSProperties
  columns?: number
  gap?: number | string
  minItemWidth?: string
  fullscreen?: boolean
}

export function Grid({ children, style, columns, gap = '2px', minItemWidth = '280px', fullscreen }: GridProps) {
  const gridTemplateColumns = fullscreen
    ? '1fr'
    : columns
      ? `repeat(${columns}, 1fr)`
      : `repeat(auto-fit, minmax(${minItemWidth}, 1fr))`

  const s: CSSProperties = {
    display: 'grid',
    gridTemplateColumns,
    gap,
    width: '100%',
    height: '100%',
    flex: 1,
    minHeight: 0,
    background: '#000',
    ...style,
  }
  return <div style={s}>{children}</div>
}
