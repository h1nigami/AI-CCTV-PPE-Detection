import type { ReactNode } from 'react'
import { useBreakpoint } from '../../hooks/useBreakpoint'

interface ResponsiveProps {
  mobile?: ReactNode
  tablet?: ReactNode
  desktop?: ReactNode
  children?: ReactNode
}

export function Responsive({ mobile, tablet, desktop, children }: ResponsiveProps) {
  const bp = useBreakpoint()

  if (bp === 'mobile' && mobile !== undefined) return <>{mobile}</>
  if (bp === 'tablet' && tablet !== undefined) return <>{tablet}</>
  if (bp === 'desktop' && desktop !== undefined) return <>{desktop}</>
  return <>{children}</>
}
