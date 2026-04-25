import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, RotateCcw, Save, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { previewSolve, solveCase, updateCase } from '@/api/endpoints'
import type { CaseInput, SolverResult } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Slider } from '@/components/ui/slider'
import { useDebounce } from '@/hooks/useDebounce'
import { fmtMeters, fmtNumber } from '@/lib/utils'
import { fmtForce, unitFor } from '@/lib/units'
import { useUnitsStore } from '@/store/units'

export interface SensitivityPanelProps {
  caseId: number
  /** Input baseline do caso (valores originalmente salvos). */
  baseInput: CaseInput
  /** Notificado a cada nova predição ao vivo (ou `null` quando sliders no zero). */
  onPreview: (result: SolverResult | null) => void
  /** Callback após aplicar mudanças com sucesso (recarregar dados do caso). */
  onApplied?: () => void
}

interface Knobs {
  /** Multiplicador do T_fl baseline (0.5 a 1.5). */
  tFlMul: number
  /** Multiplicador do L baseline (0.5 a 1.5). */
  lengthMul: number
  /** Atrito absoluto, 0 a 1.5 (μ não escala bem com multiplicador). */
  mu: number
}

const DEFAULT_KNOBS: Knobs = { tFlMul: 1, lengthMul: 1, mu: NaN }

/**
 * Painel de análise de sensibilidade — sliders que ajustam T_fl, L e μ
 * em torno do valor original do caso e dispara `solve/preview` ao vivo.
 *
 * Estado interno mínimo: 3 knobs. O resultado preview é propagado para
 * o pai via `onPreview` para que o gráfico e cards reflitam imediatamente.
 *
 * Aplicação persistente: PATCH no caso com novos valores + POST /solve
 * para criar uma nova execução.
 */
export function SensitivityPanel({
  caseId,
  baseInput,
  onPreview,
  onApplied,
}: SensitivityPanelProps) {
  const system = useUnitsStore((s) => s.system)
  const segment = baseInput.segments[0]!
  const baseTfl =
    baseInput.boundary.mode === 'Tension'
      ? baseInput.boundary.input_value
      : 0
  const baseLength = segment.length
  const baseMu = baseInput.seabed?.mu ?? 0

  const [knobs, setKnobs] = useState<Knobs>({
    ...DEFAULT_KNOBS,
    mu: baseMu,
  })

  // Snapshot dos sliders após debounce — fonte da verdade para a query.
  const debouncedKnobs = useDebounce(knobs, 300)

  // Detecta se há mudança em relação ao baseline. Quando NÃO há, devolve
  // null para o pai (isto é, o componente "se desliga" e o app volta a
  // mostrar o resultado salvo).
  const hasChange = useMemo(
    () =>
      Math.abs(debouncedKnobs.tFlMul - 1) > 1e-3 ||
      Math.abs(debouncedKnobs.lengthMul - 1) > 1e-3 ||
      Math.abs(debouncedKnobs.mu - baseMu) > 1e-3,
    [debouncedKnobs, baseMu],
  )

  const previewInput = useMemo<CaseInput>(() => {
    return {
      ...baseInput,
      segments: [
        { ...segment, length: baseLength * debouncedKnobs.lengthMul },
      ],
      boundary: {
        ...baseInput.boundary,
        input_value:
          baseInput.boundary.mode === 'Tension'
            ? baseTfl * debouncedKnobs.tFlMul
            : baseInput.boundary.input_value,
      },
      seabed: {
        ...baseInput.seabed,
        mu: Math.max(0, debouncedKnobs.mu),
        slope_rad: baseInput.seabed?.slope_rad ?? 0,
      },
    }
  }, [baseInput, segment, baseTfl, baseLength, debouncedKnobs])

  const previewQuery = useQuery<SolverResult, ApiError>({
    queryKey: ['sensitivity-preview', caseId, debouncedKnobs],
    queryFn: () => previewSolve(previewInput),
    enabled: hasChange,
    retry: false,
    staleTime: 30_000,
  })

  // Propaga o resultado para o pai. Quando hasChange = false, devolve null
  // para que o pai volte a mostrar o resultado salvo.
  useEffect(() => {
    if (!hasChange) {
      onPreview(null)
      return
    }
    if (previewQuery.data) onPreview(previewQuery.data)
    // Em erro/loading mantém o último válido para evitar flicker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasChange, previewQuery.data])

  const applyMutation = useMutation({
    mutationFn: async () => {
      // 1. Atualiza o caso com os valores dos sliders.
      await updateCase(caseId, previewInput)
      // 2. Dispara solve, que persiste a execução (#N do histórico).
      const exec = await solveCase(caseId)
      return exec
    },
    onSuccess: () => {
      toast.success('Mudanças aplicadas e nova execução salva.')
      reset()
      onApplied?.()
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao aplicar mudanças', { description: msg })
    },
  })

  function reset() {
    setKnobs({ tFlMul: 1, lengthMul: 1, mu: baseMu })
    onPreview(null)
  }

  const isFetching = previewQuery.isFetching && hasChange
  const previewResult = hasChange ? previewQuery.data : null
  const errored = previewQuery.isError && hasChange

  // Faixas dos sliders: ±50% para multiplicadores; μ vai de 0 a 1.5.
  const tFlActual = baseTfl * knobs.tFlMul
  const lengthActual = baseLength * knobs.lengthMul

  return (
    <Card className="border-primary/20 bg-primary/[0.02]">
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            Análise de sensibilidade
            {isFetching && (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            )}
            {hasChange && previewResult && !isFetching && (
              <Badge
                variant="secondary"
                className="h-5 bg-primary/15 text-[10px] text-primary"
              >
                preview ao vivo
              </Badge>
            )}
            {errored && (
              <Badge variant="danger" className="h-5 text-[10px]">
                inviável
              </Badge>
            )}
          </CardTitle>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Mova os sliders para ver o efeito em tempo real. As tabelas, o
            gráfico e os cards refletem o preview enquanto você ajusta. Use{' '}
            <strong>Aplicar</strong> para salvar como nova execução.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={reset}
            disabled={!hasChange || applyMutation.isPending}
            title="Voltar todos os sliders ao baseline do caso"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Resetar
          </Button>
          <Button
            size="sm"
            onClick={() => applyMutation.mutate()}
            disabled={
              !hasChange ||
              isFetching ||
              errored ||
              applyMutation.isPending ||
              !previewResult
            }
          >
            {applyMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            Aplicar como nova execução
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-5 pb-4 md:grid-cols-3">
        {baseInput.boundary.mode === 'Tension' && (
          <KnobSlider
            label="Tração no fairlead"
            valueLabel={fmtForce(tFlActual, system)}
            baselineLabel={`baseline ${fmtForce(baseTfl, system)}`}
            mul={knobs.tFlMul}
            onMulChange={(m) => setKnobs((k) => ({ ...k, tFlMul: m }))}
          />
        )}
        <KnobSlider
          label="Comprimento da linha"
          valueLabel={fmtMeters(lengthActual, 1)}
          baselineLabel={`baseline ${fmtMeters(baseLength, 1)}`}
          mul={knobs.lengthMul}
          onMulChange={(m) => setKnobs((k) => ({ ...k, lengthMul: m }))}
        />
        <MuSlider
          mu={knobs.mu}
          baselineLabel={`baseline ${fmtNumber(baseMu, 2)}`}
          onChange={(mu) => setKnobs((k) => ({ ...k, mu }))}
        />
      </CardContent>
      {errored && previewQuery.error && (
        <CardContent className="pt-0">
          <p className="rounded-md border border-danger/30 bg-danger/5 p-2 text-[11px] text-danger">
            {previewQuery.error.message ||
              'Caso inviável com os parâmetros atuais. Ajuste os sliders.'}
          </p>
        </CardContent>
      )}
      <input
        type="hidden"
        // Serve só para garantir que o badge da unidade de força fique
        // sincronizado em re-renders.
        data-unit={unitFor('force', system)}
      />
    </Card>
  )
}

function KnobSlider({
  label,
  valueLabel,
  baselineLabel,
  mul,
  onMulChange,
}: {
  label: string
  valueLabel: string
  baselineLabel: string
  mul: number
  onMulChange: (mul: number) => void
}) {
  // Slider opera em 0 a 100 (0% a 200% do baseline = ±100%).
  // Convertemos: mul=1 → 50, mul=0.5 → 25, mul=1.5 → 75.
  // Faixa total ±50% (mul ∈ [0.5, 1.5]) usa slider 0..100 mapeado linearmente.
  const sliderValue = ((mul - 0.5) / 1.0) * 100
  const pct = ((mul - 1) * 100).toFixed(0)
  const positive = mul > 1
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-foreground">{label}</span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {baselineLabel}
        </span>
      </div>
      <Slider
        min={0}
        max={100}
        step={1}
        value={[sliderValue]}
        onValueChange={(v) => {
          const sv = v[0] ?? 50
          onMulChange(0.5 + (sv / 100) * 1.0)
        }}
      />
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-semibold tabular-nums">
          {valueLabel}
        </span>
        <span
          className={`font-mono text-[10px] tabular-nums ${
            Math.abs(mul - 1) < 1e-3
              ? 'text-muted-foreground'
              : positive
                ? 'text-warning'
                : 'text-success'
          }`}
        >
          {Math.abs(mul - 1) < 1e-3 ? '—' : `${positive ? '+' : ''}${pct}%`}
        </span>
      </div>
    </div>
  )
}

function MuSlider({
  mu,
  baselineLabel,
  onChange,
}: {
  mu: number
  baselineLabel: string
  onChange: (mu: number) => void
}) {
  // μ ∈ [0, 1.5]; slider 0..150 inteiro.
  const sliderValue = mu * 100
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-foreground">
          Coeficiente de atrito (μ)
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {baselineLabel}
        </span>
      </div>
      <Slider
        min={0}
        max={150}
        step={5}
        value={[sliderValue]}
        onValueChange={(v) => {
          const sv = v[0] ?? 0
          onChange(sv / 100)
        }}
      />
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-semibold tabular-nums">
          {fmtNumber(mu, 2)}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          [0,00 — 1,50]
        </span>
      </div>
    </div>
  )
}
