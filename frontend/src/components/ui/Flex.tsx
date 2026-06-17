import type { CSSProperties, ReactNode } from 'react'

interface FlexProps {
  children?: ReactNode
  style?: CSSProperties
  direction?: CSSProperties['flexDirection']
  align?: CSSProperties['alignItems']
  justify?: CSSProperties['justifyContent']
  wrap?: CSSProperties['flexWrap']
  gap?: number | string
  flex?: number | string
  p?: number | string
  px?: number | string
  py?: number | string
  m?: number | string
  width?: number | string
  height?: number | string
  minHeight?: number | string
  overflow?: CSSProperties['overflow']
  onClick?: () => void
  className?: string
}

export function Flex({
  children, style, direction = 'row', align, justify, wrap,
  gap, flex, p, px, py, m, width, height, minHeight, overflow,
  onClick, className,
}: FlexProps) {
  const s: CSSProperties = {
    display: 'flex',
    flexDirection: direction,
    ...(align !== undefined ? { alignItems: align } : {}),
    ...(justify !== undefined ? { justifyContent: justify } : {}),
    ...(wrap !== undefined ? { flexWrap: wrap } : {}),
    ...(gap !== undefined ? { gap } : {}),
    ...(flex !== undefined ? { flex } : {}),
    ...(p !== undefined ? { padding: p } : {}),
    ...(px !== undefined ? { paddingLeft: px, paddingRight: px } : {}),
    ...(py !== undefined ? { paddingTop: py, paddingBottom: py } : {}),
    ...(m !== undefined ? { margin: m } : {}),
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
    ...(minHeight !== undefined ? { minHeight } : {}),
    ...(overflow !== undefined ? { overflow } : {}),
    ...style,
  }
  return <div className={className} style={s} onClick={onClick}>{children}</div>
}
