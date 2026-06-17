import { useState, useEffect } from 'react'

type Orientation = 'portrait' | 'landscape'

export function useOrientation(): Orientation {
  const [orientation, setOrientation] = useState<Orientation>(() =>
    window.innerWidth > window.innerHeight ? 'landscape' : 'portrait',
  )

  useEffect(() => {
    const handler = () => {
      setOrientation(window.innerWidth > window.innerHeight ? 'landscape' : 'portrait')
    }
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])

  return orientation
}
