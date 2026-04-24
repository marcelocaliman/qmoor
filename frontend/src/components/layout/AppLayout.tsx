import { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Disclaimer } from './Disclaimer'
import { Sidebar } from './Sidebar'
import { HelpDialog } from '@/components/common/HelpDialog'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useUIStore } from '@/store/ui'

/**
 * Shell da aplicação: sidebar + área central (topbar + outlet) + disclaimer
 * footer. Atalhos de teclado globais.
 */
export function AppLayout() {
  const navigate = useNavigate()
  const { toggleSidebar } = useUIStore()
  const [helpOpen, setHelpOpen] = useState(false)

  useKeyboardShortcuts([
    { key: '?', shift: true, handler: () => setHelpOpen((v) => !v) },
    { key: 'b', meta: true, handler: () => toggleSidebar() },
    // g c → /cases, g a → /catalog, g i → /import-export (sequence simplificada:
    // último `g` seguido imediatamente de letra. Implementação minimal abaixo.)
  ])

  // Sequência G + letra (minimal): memoriza se último keydown foi 'g'
  // e resolve atalho na próxima tecla.
  useKeyboardShortcuts([])
  // Implementação direta de "g c" sem depender do hook:
  // eslint-disable-next-line react-hooks/exhaustive-deps
  // (inline useEffect inside a hook helper would be cleaner; keeping in one place
  // for the MVP)

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </main>
        <Disclaimer />
      </div>
      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
      <GSequenceShortcut onNavigate={(to) => navigate(to)} />
    </div>
  )
}

/** Atalho "g + letra" — sequência de 2 teclas. */
function GSequenceShortcut({ onNavigate }: { onNavigate: (to: string) => void }) {
  // Usa um ref mutável via useState-idiom seguro para closures
  // (sem depender de useRef para manter este arquivo compacto).
  useKeyboardShortcuts([
    {
      key: 'g',
      handler: () => {
        const handler = (e: KeyboardEvent) => {
          window.removeEventListener('keydown', handler, true)
          const target = e.target as HTMLElement | null
          if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
          if (e.key === 'c') {
            e.preventDefault()
            onNavigate('/cases')
          } else if (e.key === 'a') {
            e.preventDefault()
            onNavigate('/catalog')
          } else if (e.key === 'i') {
            e.preventDefault()
            onNavigate('/import-export')
          } else if (e.key === 's') {
            e.preventDefault()
            onNavigate('/settings')
          }
        }
        window.addEventListener('keydown', handler, true)
        // Descarta o handler após 1200ms se nada vier
        setTimeout(() => window.removeEventListener('keydown', handler, true), 1200)
      },
    },
  ])
  return null
}
