import { Mountain } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export interface BathymetryPopoverProps {
  /** Slope atual (rad). Usado para pre-popular `depth_at_fairlead`. */
  currentSlopeRad: number
  /** Lâmina d'água atual sob a âncora (m). */
  currentH: number
  /** Callback recebe novo slope em radianos. */
  onApplyRad: (rad: number) => void
  /**
   * X total resultante do solver no caso atual (m). Quando disponível,
   * o popover pré-popula como "Distância horizontal estimada" — assim o
   * slope calculado bate com o caso real, não com uma estimativa solta.
   */
  currentXTotal?: number
}

/**
 * Popover de "calcular slope pela batimetria nos dois pontos".
 *
 * O usuário fornece:
 *   - profundidade do seabed sob a âncora (m)
 *   - profundidade do seabed sob o fairlead (m)
 *   - distância horizontal entre os pontos (m, estimativa)
 *
 * E o sistema calcula:
 *   slope_rad = atan2(depth_anchor − depth_fairlead, horizontal_distance)
 *
 * Convenção: se anchor é mais profundo, slope > 0 (seabed sobe ao fairlead).
 *
 * Útil quando o engenheiro tem batimetria local em vez de slope angular.
 */
export function BathymetryPopover({
  currentSlopeRad,
  currentH,
  onApplyRad,
  currentXTotal,
}: BathymetryPopoverProps) {
  const [open, setOpen] = useState(false)
  const [depthAnchor, setDepthAnchor] = useState<number>(currentH)
  const [depthFairlead, setDepthFairlead] = useState<number>(0)
  // Default da distância horizontal: X total do caso (preview) quando
  // disponível; senão 500 m como estimativa.
  const [horizDistance, setHorizDistance] = useState<number>(
    currentXTotal && currentXTotal > 0 ? currentXTotal : 500,
  )

  // Pre-popula depth_fairlead a partir do slope atual sempre que o popover
  // abre. O X usado é o do caso atual (preview), garantindo coerência com
  // a geometria real — assim o slope calculado bate exatamente.
  useEffect(() => {
    if (!open) return
    setDepthAnchor(currentH)
    const xUse = currentXTotal && currentXTotal > 0 ? currentXTotal : horizDistance
    setHorizDistance(xUse)
    const m = Math.tan(currentSlopeRad)
    const dF = currentH - m * xUse
    setDepthFairlead(Number.isFinite(dF) ? Math.max(0, dF) : 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, currentH, currentSlopeRad, currentXTotal])

  const dx = horizDistance > 0 ? horizDistance : 1
  const dz = depthAnchor - depthFairlead
  const slopeRadPreview = Math.atan2(dz, dx)
  const slopeDegPreview = (slopeRadPreview * 180) / Math.PI

  function handleApply() {
    onApplyRad(slopeRadPreview)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title="Calcular inclinação a partir da batimetria nos dois pontos"
          className={cn(
            'flex w-9 shrink-0 items-center justify-center border-l border-input',
            'bg-muted/40 text-muted-foreground transition-colors',
            'hover:bg-muted hover:text-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset',
          )}
        >
          <Mountain className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-3">
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-semibold">Inclinação por batimetria</h4>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Forneça as profundidades nos dois pontos e a distância horizontal
              entre eles. A inclinação é calculada automaticamente.
            </p>
          </div>
          <div className="space-y-2">
            <FieldRow
              label="Prof. seabed sob âncora"
              unit="m"
              value={depthAnchor}
              onChange={setDepthAnchor}
              min={0}
              hint="Geralmente igual à lâmina d'água"
            />
            <FieldRow
              label="Prof. seabed sob fairlead"
              unit="m"
              value={depthFairlead}
              onChange={setDepthFairlead}
              min={0}
            />
            <FieldRow
              label="Distância horizontal entre os pontos"
              unit="m"
              value={horizDistance}
              onChange={setHorizDistance}
              min={1}
              hint={
                currentXTotal && currentXTotal > 0
                  ? `Pré-preenchido com X total do caso atual (${currentXTotal.toFixed(1)} m). Ajuste se for outro.`
                  : 'Use o X total esperado do caso'
              }
            />
          </div>
          <div className="rounded-md border border-border/60 bg-muted/30 p-2">
            <div className="flex items-baseline justify-between gap-2 text-[12px]">
              <span className="text-muted-foreground">Inclinação calculada</span>
              <span className="font-mono font-semibold tabular-nums">
                {slopeDegPreview.toFixed(2)}°
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-2 text-[10px] text-muted-foreground">
              <span>Δz / Δx</span>
              <span className="font-mono tabular-nums">
                {dz.toFixed(1)} m / {dx.toFixed(1)} m
              </span>
            </div>
          </div>
          {Math.abs(slopeDegPreview) > 45 && (
            <p className="rounded-md border border-warning/40 bg-warning/10 p-2 text-[11px] text-warning">
              Inclinação fora do range admitido (±45°). O solver vai recusar.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              disabled={Math.abs(slopeDegPreview) > 45}
            >
              Aplicar
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function FieldRow({
  label,
  unit,
  value,
  onChange,
  min,
  hint,
}: {
  label: string
  unit: string
  value: number
  onChange: (v: number) => void
  min?: number
  hint?: string
}) {
  return (
    <div className="space-y-0.5">
      <Label className="flex items-center justify-between text-[10px] font-medium text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{unit}</span>
      </Label>
      <Input
        type="number"
        step="any"
        min={min}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(parseFloat(e.target.value || '0'))}
        className="h-8 font-mono text-sm"
      />
      {hint && (
        <p className="text-[9.5px] text-muted-foreground">{hint}</p>
      )}
    </div>
  )
}
