import type { CSSProperties, ReactNode } from 'react'

interface BoxProps {
  children?: ReactNode
  style?: CSSProperties
  p?: number | string
  px?: number | string
  py?: number | string
  m?: number | string
  mx?: number | string
  my?: number | string
  gap?: number | string
  flex?: number | string
  width?: number | string
  minWidth?: number | string
  maxWidth?: number | string
  height?: number | string
  minHeight?: number | string
  maxHeight?: number | string
  display?: CSSProperties['display']
  position?: CSSProperties['position']
  overflow?: CSSProperties['overflow']
  className?: string
  onClick?: () => void
  ref?: React.Ref<HTMLDivElement>
}

export function Box({
  children, style, p, px, py, m, mx, my, gap, flex,
  width, minWidth, maxWidth, height, minHeight, maxHeight,
  display, position, overflow, className, onClick, ref,
}: BoxProps) {
  const s: CSSProperties = {
    ...(p !== undefined ? { padding: p } : {}),
    ...(px !== undefined ? { paddingLeft: px, paddingRight: px } : {}),
    ...(py !== undefined ? { paddingTop: py, paddingBottom: py } : {}),
    ...(m !== undefined ? { margin: m } : {}),
    ...(mx !== undefined ? { marginLeft: mx, marginRight: mx } : {}),
    ...(my !== undefined ? { marginTop: my, marginBottom: my } : {}),
    ...(gap !== undefined ? { gap } : {}),
    ...(flex !== undefined ? { flex } : {}),
    ...(width !== undefined ? { width } : {}),
    ...(minWidth !== undefined ? { minWidth } : {}),
    ...(maxWidth !== undefined ? { maxWidth } : {}),
    ...(height !== undefined ? { height } : {}),
    ...(minHeight !== undefined ? { minHeight } : {}),
    ...(maxHeight !== undefined ? { maxHeight } : {}),
    ...(display !== undefined ? { display } : {}),
    ...(position !== undefined ? { position } : {}),
    ...(overflow !== undefined ? { overflow } : {}),
    ...style,
  }
  return <div ref={ref} className={className} style={s} onClick={onClick}>{children}</div>
}
