import { useEffect, type ReactNode } from 'react'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
}

const backdropStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 600,
  background: 'rgba(0,0,0,0.6)',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'flex-end',
}

const sheetStyle: React.CSSProperties = {
  background: '#222',
  borderTopLeftRadius: 16,
  borderTopRightRadius: 16,
  maxHeight: '80vh',
  overflow: 'auto',
  padding: 16,
  animation: 'sheetUp 0.25s ease',
}

const handleStyle: React.CSSProperties = {
  width: 40,
  height: 4,
  borderRadius: 2,
  background: '#555',
  margin: '0 auto 12px',
  flexShrink: 0,
}

export function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div style={backdropStyle} onClick={onClose}>
      <div style={sheetStyle} onClick={(e) => e.stopPropagation()}>
        <div style={handleStyle} />
        {title && (
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff', marginBottom: 12 }}>
            {title}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
