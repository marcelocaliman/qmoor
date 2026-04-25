import { useEffect, useId, useRef, useState } from 'react'
import { siToUnit, unitFor, unitToSi, type Quantity } from '@/lib/units'
import { useUnitsStore } from '@/store/units'
import { cn } from '@/lib/utils'

export interface UnitInputProps {
  /** Valor canônico em SI (N, N/m). `null/undefined/NaN` mostram vazio. */
  value: number | null | undefined
  /** Callback recebe novo valor SI; ou `NaN` se o input estiver vazio. */
  onChange: (siValue: number) => void
  /** Que tipo de quantidade — define unidades aceitas pelo sistema. */
  quantity: Quantity
  /** Casas decimais no display. Default 2. */
  digits?: number
  /** Step do <input>. Default proporcional aos digits. */
  step?: number | string
  className?: string
  inputClassName?: string
  placeholder?: string
  disabled?: boolean
  id?: string
}

/**
 * Input numérico unit-aware. Estado externo SEMPRE em SI; este componente
 * apresenta e edita na unidade do sistema escolhido (`useUnitsStore`).
 *
 * Estratégia anti-rounding-loop: mantém o texto exibido em estado local;
 * só ressincroniza com o valor externo quando ele muda *fora* da edição
 * deste input (e.g., aplicar do catálogo). Assim evitamos o problema clássico
 * de digitar "20,5" e o input "saltar" pra "20,55" porque o roundtrip
 * SI→display introduz drift.
 */
export function UnitInput({
  value,
  onChange,
  quantity,
  digits = 2,
  step,
  className,
  inputClassName,
  placeholder,
  disabled,
  id,
}: UnitInputProps) {
  const system = useUnitsStore((s) => s.system)
  const toggleSystem = useUnitsStore((s) => s.toggle)
  const unit = unitFor(quantity, system)

  const autoId = useId()
  const reactId = id ?? autoId

  const lastExternalSi = useRef<number | null | undefined>(value)
  const [text, setText] = useState<string>(() =>
    formatForInput(value ?? null, unit, digits),
  )

  // Quando o valor externo muda (não pelo nosso onChange), reformata o display.
  useEffect(() => {
    if (value !== lastExternalSi.current) {
      lastExternalSi.current = value
      setText(formatForInput(value ?? null, unit, digits))
    }
  }, [value, unit, digits])

  // Trocar o sistema de unidades também força reformatação.
  useEffect(() => {
    setText(formatForInput(value ?? null, unit, digits))
    // value é mantido SI; recomputamos o display.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unit])

  function handleChange(raw: string) {
    setText(raw)
    const normalized = raw.replace(',', '.').trim()
    if (normalized === '' || normalized === '-') {
      onChange(NaN)
      lastExternalSi.current = NaN
      return
    }
    const n = Number(normalized)
    if (!Number.isFinite(n)) return
    const si = unitToSi(n, unit)
    lastExternalSi.current = si
    onChange(si)
  }

  function handleBlur() {
    // Reformatar texto pra forma canônica (ex: "20,5" → "20,50")
    const numeric =
      lastExternalSi.current != null && Number.isFinite(lastExternalSi.current)
        ? lastExternalSi.current
        : null
    setText(formatForInput(numeric, unit, digits))
  }

  return (
    <div
      className={cn(
        'flex items-stretch overflow-hidden rounded-md border border-input bg-background',
        'focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1',
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
    >
      <input
        id={reactId}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        step={step}
        className={cn(
          'min-w-0 flex-1 bg-transparent px-2.5 py-1 font-mono text-sm tabular-nums',
          'placeholder:text-muted-foreground',
          'focus:outline-none disabled:cursor-not-allowed',
          inputClassName,
        )}
      />
      <button
        type="button"
        onClick={toggleSystem}
        disabled={disabled}
        title={
          system === 'metric'
            ? `Sistema atual: Metric (${unit}). Clique para SI.`
            : `Sistema atual: SI (${unit}). Clique para Metric.`
        }
        className={cn(
          'flex shrink-0 items-center justify-center whitespace-nowrap border-l border-input',
          'min-w-[3rem] px-2 bg-muted/40 font-mono text-[10px] font-semibold uppercase tracking-tight',
          'text-muted-foreground transition-colors',
          'hover:bg-muted hover:text-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset',
          disabled && 'cursor-not-allowed',
        )}
      >
        {unit}
      </button>
    </div>
  )
}

function formatForInput(
  siValue: number | null,
  unit: 'N' | 'kN' | 'te' | 'N/m' | 'kgf/m',
  digits: number,
): string {
  if (siValue == null || !Number.isFinite(siValue)) return ''
  const v = siToUnit(siValue, unit)
  // Para valores em N (SI puro), preserve inteiros; outras unidades respeitam digits.
  const finalDigits = unit === 'N' || unit === 'N/m' ? 0 : digits
  return v.toLocaleString('pt-BR', {
    minimumFractionDigits: finalDigits,
    maximumFractionDigits: finalDigits,
    useGrouping: false, // sem separador de milhar no input — facilita edição
  })
}
