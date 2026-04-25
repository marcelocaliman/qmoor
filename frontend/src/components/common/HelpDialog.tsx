import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export function HelpDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Atalhos de teclado</DialogTitle>
          <DialogDescription>
            Navegação rápida dentro da aplicação.
          </DialogDescription>
        </DialogHeader>
        <dl className="divide-y divide-border">
          {SHORTCUTS.map(({ keys, label }) => (
            <div
              key={label}
              className="flex items-center justify-between py-2 text-sm"
            >
              <dd className="text-muted-foreground">{label}</dd>
              <dt className="flex items-center gap-1">
                {keys.map((k, i) => (
                  <kbd
                    key={i}
                    className="inline-flex h-6 min-w-6 items-center justify-center rounded border border-border bg-muted px-1.5 font-mono text-[11px]"
                  >
                    {k}
                  </kbd>
                ))}
              </dt>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}

const SHORTCUTS = [
  { keys: ['Cmd', 'K'], label: 'Abrir busca / paleta de comandos' },
  { keys: ['?'], label: 'Mostrar esta ajuda' },
  { keys: ['Cmd', 'B'], label: 'Alternar sidebar' },
  { keys: ['g', 'c'], label: 'Ir para casos' },
  { keys: ['g', 'a'], label: 'Ir para catálogo' },
  { keys: ['g', 'i'], label: 'Ir para import/export' },
  { keys: ['g', 's'], label: 'Ir para configurações' },
  { keys: ['Esc'], label: 'Fechar diálogos' },
]
