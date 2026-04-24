import { Info } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Disclaimer obrigatório (Seção 10 do Documento A v2.2) visível em
 * rodapé permanente, discreto.
 */
export function Disclaimer({ className }: { className?: string }) {
  return (
    <footer
      className={cn(
        'border-t border-border bg-muted/20 px-6 py-2 text-[11px] text-muted-foreground',
        className,
      )}
    >
      <div className="mx-auto flex max-w-6xl items-start gap-2">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        <p>
          <strong className="font-medium text-foreground">Disclaimer:</strong>{' '}
          Os resultados apresentados são estimativas de análise estática
          simplificada e <strong>não substituem</strong> análise de engenharia
          realizada com ferramenta validada, dados certificados, premissas
          aprovadas e revisão por responsável técnico habilitado.
        </p>
      </div>
    </footer>
  )
}
