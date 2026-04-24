import { Badge } from '@/components/ui/badge'
import type { AlertLevel, ConvergenceStatus, LineCategory } from '@/api/types'

/** Mapa de alert_level → cor do badge. */
const ALERT_VARIANT: Record<AlertLevel, React.ComponentProps<typeof Badge>['variant']> = {
  ok: 'success',
  yellow: 'warning',
  red: 'danger',
  broken: 'danger',
}

const ALERT_LABEL: Record<AlertLevel, string> = {
  ok: 'OK',
  yellow: 'Atenção',
  red: 'Crítico',
  broken: 'Rompido',
}

export function AlertBadge({ level }: { level: AlertLevel }) {
  return <Badge variant={ALERT_VARIANT[level]}>{ALERT_LABEL[level]}</Badge>
}

const STATUS_VARIANT: Record<
  ConvergenceStatus,
  React.ComponentProps<typeof Badge>['variant']
> = {
  converged: 'success',
  ill_conditioned: 'warning',
  max_iterations: 'warning',
  invalid_case: 'danger',
  numerical_error: 'danger',
}

const STATUS_LABEL: Record<ConvergenceStatus, string> = {
  converged: 'Convergiu',
  ill_conditioned: 'Mal cond.',
  max_iterations: 'Max iter',
  invalid_case: 'Inválido',
  numerical_error: 'Erro num.',
}

export function StatusBadge({ status }: { status: ConvergenceStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>
}

const CATEGORY_VARIANT: Record<
  LineCategory,
  React.ComponentProps<typeof Badge>['variant']
> = {
  Wire: 'info',
  StuddedChain: 'default',
  StudlessChain: 'default',
  Polyester: 'secondary',
}

const CATEGORY_LABEL: Record<LineCategory, string> = {
  Wire: 'Wire',
  StuddedChain: 'Studded',
  StudlessChain: 'Studless',
  Polyester: 'Poliéster',
}

export function CategoryBadge({ category }: { category?: string | null }) {
  if (!category) return <span className="text-muted-foreground">—</span>
  const cat = category as LineCategory
  if (!(cat in CATEGORY_VARIANT)) {
    return <Badge variant="outline">{category}</Badge>
  }
  return <Badge variant={CATEGORY_VARIANT[cat]}>{CATEGORY_LABEL[cat]}</Badge>
}

export function ModeBadge({ mode }: { mode: string }) {
  return (
    <Badge variant="outline" className="font-mono text-[11px]">
      {mode}
    </Badge>
  )
}
