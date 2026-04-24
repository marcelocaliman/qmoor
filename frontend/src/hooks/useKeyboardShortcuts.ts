import { useEffect } from 'react'

export interface Shortcut {
  /** Tecla principal (em minúsculo). */
  key: string
  /** Exige Cmd/Ctrl. */
  meta?: boolean
  shift?: boolean
  handler: (e: KeyboardEvent) => void
}

/**
 * Handler global de atalhos. Ignora eventos quando o foco está em
 * input/textarea/contenteditable.
 */
export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      if (target && shouldIgnore(target)) return
      for (const s of shortcuts) {
        if (e.key.toLowerCase() !== s.key.toLowerCase()) continue
        if (s.meta && !(e.metaKey || e.ctrlKey)) continue
        if (!s.meta && (e.metaKey || e.ctrlKey)) continue
        if (s.shift && !e.shiftKey) continue
        e.preventDefault()
        s.handler(e)
        return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shortcuts])
}

function shouldIgnore(el: HTMLElement): boolean {
  const tag = el.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    el.isContentEditable
  )
}
