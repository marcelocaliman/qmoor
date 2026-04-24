import type { AlertLevel } from '@/api/types'
import { cn } from '@/lib/utils'

interface UtilizationGaugeProps {
  /** 0.0..1.0+ */
  value: number
  alertLevel: AlertLevel
  className?: string
}

/**
 * Barra horizontal mostrando T_fl/MBL, com 3 bandas (yellow/red/broken).
 * Cores derivadas do alert_level do solver.
 */
export function UtilizationGauge({
  value,
  alertLevel,
  className,
}: UtilizationGaugeProps) {
  const clamped = Math.max(0, Math.min(value, 1.1))
  const widthPct = Math.min(clamped * 100, 100)

  const fillClass =
    alertLevel === 'ok'
      ? 'bg-success'
      : alertLevel === 'yellow'
        ? 'bg-warning'
        : alertLevel === 'red'
          ? 'bg-danger'
          : 'bg-danger'

  return (
    <div className={cn('w-full space-y-1.5', className)}>
      <div className="relative h-3 w-full overflow-hidden rounded-full bg-muted">
        {/* Bandas de referência muito sutis */}
        <div className="absolute inset-y-0 left-[50%] w-px bg-border" />
        <div className="absolute inset-y-0 left-[60%] w-px bg-border" />
        {/* Fill */}
        <div
          className={cn(
            'absolute inset-y-0 left-0 rounded-full transition-all',
            fillClass,
          )}
          style={{ width: `${widthPct}%` }}
          role="meter"
          aria-label="Utilização da linha"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(clamped * 100)}
        />
      </div>
      <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>0%</span>
        <span className="text-warning/80">50%</span>
        <span className="text-danger/80">60%</span>
        <span className="text-danger">100%</span>
      </div>
    </div>
  )
}
