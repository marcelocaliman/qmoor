import { AlertCircle, Anchor, Compass } from 'lucide-react'
import type {
  MooringLineResult,
  SystemLineSpec,
} from '@/api/types'
import { Card, CardContent } from '@/components/ui/card'
import { UtilizationGauge } from '@/components/common/UtilizationGauge'
import {
  AlertBadge,
  AnchorUpliftBadge,
} from '@/components/common/StatusBadge'
import { cn, fmtAngleDeg, fmtMeters, fmtPercent } from '@/lib/utils'

export interface MooringLineMetricsCardProps {
  /** Definição da linha (input do usuário). */
  lineSpec: SystemLineSpec
  /**
   * Resultado da linha vindo de um cálculo (solve do estado neutro,
   * ou equilíbrio sob carga, ou um ponto da watchcircle). Quando
   * ausente, o card mostra só os dados de input.
   */
  result?: MooringLineResult
  /** Cor faixa lateral por ordem da linha no sistema (1, 2, 3...). */
  paletteIndex?: number
  className?: string
}

const PALETTE_LIGHT = ['#1E3A5F', '#D97706', '#047857', '#7C3AED', '#BE185D']
const PALETTE_DARK = ['#60A5FA', '#FBBF24', '#34D399', '#A78BFA', '#F472B6']

/**
 * Card compacto de métricas de uma linha individual num mooring system.
 * Pensado para grids responsivos (min-w 280px) onde o engenheiro vê
 * todas as linhas lado a lado para comparação visual.
 *
 * Quando `result` está presente, exibe T_fl, H, ângulo de uplift,
 * utilização e badge de alerta. Quando ausente (sistema ainda não
 * resolvido), mostra apenas geometria e identidade.
 */
export function MooringLineMetricsCard({
  lineSpec,
  result,
  paletteIndex = 0,
  className,
}: MooringLineMetricsCardProps) {
  const sr = result?.solver_result
  const isInvalid = sr != null && sr.status !== 'converged'
  // Cor da faixa lateral: prefere light/dark via media query do CSS,
  // usando vars do Tailwind. Fallback para light.
  const stripeColor =
    PALETTE_LIGHT[paletteIndex % PALETTE_LIGHT.length] ?? '#1E3A5F'
  const stripeColorDark =
    PALETTE_DARK[paletteIndex % PALETTE_DARK.length] ?? '#60A5FA'

  return (
    <Card
      className={cn(
        'relative overflow-hidden transition-shadow hover:shadow-md',
        isInvalid && 'opacity-80',
        className,
      )}
      style={{
        // Faixa colorida na borda esquerda — identifica a linha
        // visualmente em coerência com a cor do plot.
        borderLeftWidth: 4,
        borderLeftColor: `var(--msys-stripe, ${stripeColor})`,
      }}
    >
      {/* Truque: define a CSS var de stripe baseada no tema via media
          query usando attribute selector. Em practice usamos só a cor
          light ou dark — Tailwind dark mode toggle controla via class
          no html/body. */}
      <style>{`
        .dark .msys-line-card-stripe { border-left-color: ${stripeColorDark} !important; }
      `}</style>
      <CardContent className="space-y-2 p-3">
        {/* Header: nome + badges */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="inline-block h-3 w-3 shrink-0 rounded-sm msys-line-card-stripe"
              style={{ backgroundColor: stripeColor }}
            />
            <span className="truncate font-mono text-sm font-semibold">
              {lineSpec.name}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {sr ? (
              <>
                <AlertBadge level={sr.alert_level} />
                <AnchorUpliftBadge
                  severity={sr.anchor_uplift_severity}
                  angleDeg={
                    (sr.angle_wrt_horz_anchor * 180) / Math.PI
                  }
                />
              </>
            ) : (
              <span className="text-[10px] text-muted-foreground">
                não resolvida
              </span>
            )}
          </div>
        </div>

        {isInvalid && (
          <p className="flex items-center gap-1 text-[11px] text-danger">
            <AlertCircle className="h-3 w-3" />
            {sr?.message ||
              `Status: ${sr?.status ?? 'desconhecido'} — solver não convergiu`}
          </p>
        )}

        {/* Identidade & posição polar */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
          <Row
            icon={<Compass className="h-3 w-3" />}
            label="Azimuth"
            value={fmtAngleDeg(
              (lineSpec.fairlead_azimuth_deg * Math.PI) / 180,
              1,
            )}
          />
          <Row
            icon={<Anchor className="h-3 w-3" />}
            label="Raio fairlead"
            value={fmtMeters(lineSpec.fairlead_radius, 1)}
          />
        </div>

        {/* Tração principal — destaque */}
        {sr && (
          <div className="rounded-md bg-muted/30 px-3 py-2">
            <p className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
              Tração no fairlead
            </p>
            <p className="font-mono text-base font-semibold tabular-nums">
              {(sr.fairlead_tension / 1000).toFixed(1)}{' '}
              <span className="text-[10px] font-normal text-muted-foreground">
                kN
              </span>
            </p>
            <UtilizationGauge
              value={sr.utilization}
              alertLevel={sr.alert_level}
              className="mt-1"
            />
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              Utilização: {fmtPercent(sr.utilization, 1)} MBL
            </p>
          </div>
        )}

        {/* Outras métricas em grid 2 cols */}
        {sr && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[10.5px] tabular-nums">
            <Row label="H (horiz.)" value={`${(sr.H / 1000).toFixed(1)} kN`} />
            <Row
              label="T_anc"
              value={`${(sr.anchor_tension / 1000).toFixed(1)} kN`}
            />
            <Row
              label="Âng. fairlead"
              value={fmtAngleDeg(sr.angle_wrt_horz_fairlead, 1)}
            />
            <Row
              label="Âng. âncora"
              value={fmtAngleDeg(sr.angle_wrt_horz_anchor, 1)}
            />
            <Row
              label="X total"
              value={fmtMeters(sr.total_horz_distance, 1)}
            />
            <Row
              label="L apoiado"
              value={fmtMeters(sr.total_grounded_length, 1)}
            />
          </div>
        )}

        {/* Quando não resolvido, mostra hint do que vai aparecer */}
        {!sr && (
          <p className="text-[11px] text-muted-foreground">
            Resolva o sistema para ver métricas (tração, ângulos,
            utilização).
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function Row({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="flex items-center gap-1 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="truncate text-right font-medium text-foreground">
        {value}
      </span>
    </div>
  )
}
