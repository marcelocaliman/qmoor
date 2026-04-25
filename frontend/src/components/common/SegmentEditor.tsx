import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import {
  Controller,
  type Control,
  type FieldValues,
  type Path,
  type UseFormRegister,
  type UseFormWatch,
  type UseFormSetValue,
} from 'react-hook-form'
import { LineTypePicker } from '@/components/common/LineTypePicker'
import { UnitInput } from '@/components/common/UnitInput'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { LineTypeOutput } from '@/api/types'
import type { CaseFormValues } from '@/lib/caseSchema'
import { cn, fmtDiameterMM, fmtNumber } from '@/lib/utils'
import { toast } from 'sonner'

export interface SegmentEditorProps<T extends FieldValues = CaseFormValues> {
  index: number
  total: number
  control: Control<T>
  register: UseFormRegister<T>
  watch: UseFormWatch<T>
  setValue: UseFormSetValue<T>
  /**
   * Caminho-base para os segmentos no form (default `'segments'`).
   * Use, por exemplo, `'lines.0.segments'` para reusar este editor
   * dentro de um sistema multi-linha onde cada linha tem seu próprio
   * array de segmentos.
   */
  basePath?: string
  onRemove?: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}

/**
 * Editor de um único segmento. Recebe o `index` e um `basePath` para
 * que todos os campos apontem para `${basePath}[index].*`. Estado vive
 * no react-hook-form do pai; aqui só renderizamos.
 *
 * Convenção de ordem:
 *   - index 0 é o segmento mais próximo da âncora (chain inferior, etc.)
 *   - último index é o segmento mais próximo do fairlead
 */
export function SegmentEditor<T extends FieldValues = CaseFormValues>({
  index,
  total,
  control,
  register,
  watch,
  setValue,
  basePath = 'segments',
  onRemove,
  onMoveUp,
  onMoveDown,
}: SegmentEditorProps<T>) {
  // Helper: junta basePath + índice + sufixo, com cast de tipo confinado
  // (Path<T> em runtime é só uma string; o react-hook-form despacha por
  // string interna). Mantém o boundary do componente tipado.
  const p = (suffix: string): Path<T> =>
    `${basePath}.${index}.${suffix}` as Path<T>

  function applyLineTypeToSegment(lt: LineTypeOutput | null) {
    if (!lt) return
    setValue(p('line_type'), lt.line_type as never, { shouldValidate: true })
    setValue(p('category'), lt.category as never, { shouldValidate: true })
    setValue(p('w'), roundTo(lt.wet_weight, 2) as never, { shouldValidate: true })
    setValue(
      p('EA'),
      roundTo(lt.qmoor_ea ?? lt.gmoor_ea ?? 0, 0) as never,
      { shouldValidate: true },
    )
    setValue(p('MBL'), roundTo(lt.break_strength, 0) as never, { shouldValidate: true })
    setValue(p('diameter'), roundTo(lt.diameter, 5) as never, { shouldValidate: true })
    setValue(p('dry_weight'), roundTo(lt.dry_weight, 2) as never, { shouldValidate: true })
    if (lt.modulus) {
      setValue(p('modulus'), roundTo(lt.modulus, 0) as never, { shouldValidate: true })
    }
    toast.success(`${lt.line_type} aplicado ao segmento ${index + 1}`, {
      description: `Ø ${fmtDiameterMM(lt.diameter, 0)} · MBL ${fmtNumber(
        lt.break_strength / 1000, 0,
      )} kN`,
    })
  }

  const positionLabel =
    total === 1
      ? 'Linha homogênea'
      : index === 0
        ? `Segmento ${index + 1} — junto à âncora`
        : index === total - 1
          ? `Segmento ${index + 1} — junto ao fairlead`
          : `Segmento ${index + 1}`

  return (
    <div
      className={cn(
        'rounded-md border border-border/60 bg-muted/10 p-2.5',
        'space-y-2',
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {positionLabel}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {onMoveUp && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={onMoveUp}
              title="Mover para cima (mais perto da âncora)"
            >
              <ArrowUp className="h-3 w-3" />
            </Button>
          )}
          {onMoveDown && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={onMoveDown}
              title="Mover para baixo (mais perto do fairlead)"
            >
              <ArrowDown className="h-3 w-3" />
            </Button>
          )}
          {onRemove && total > 1 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 text-danger hover:bg-danger/10 hover:text-danger"
              onClick={onRemove}
              title="Remover este segmento"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      <Controller
        control={control}
        name={p('line_type')}
        render={({ field }) => (
          <LineTypePicker
            value={
              field.value
                ? ({
                    id: 0,
                    line_type: field.value as string,
                    category:
                      (watch(p('category')) as string | null) ?? 'Wire',
                    diameter: (watch(p('diameter')) as number) ?? 0,
                    dry_weight: (watch(p('dry_weight')) as number) ?? 0,
                    wet_weight: watch(p('w')) as number,
                    break_strength: watch(p('MBL')) as number,
                    qmoor_ea: watch(p('EA')) as number,
                    data_source: 'legacy_qmoor',
                  } as LineTypeOutput)
                : null
            }
            onChange={applyLineTypeToSegment}
          />
        )}
      />

      <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
        <InlineLabeled label="Comprimento" unit="m">
          <Input
            type="number"
            step="1"
            {...register(p('length'), { valueAsNumber: true })}
            className="h-8 font-mono"
          />
        </InlineLabeled>
        <InlineLabeled label="Diâmetro" unit="m">
          <Input
            type="number"
            step="0.001"
            min="0"
            {...register(p('diameter'), { valueAsNumber: true })}
            className="h-8 font-mono"
          />
        </InlineLabeled>
        <InlineLabeled label="Categoria" className="col-span-2">
          <Controller
            control={control}
            name={p('category')}
            render={({ field }) => (
              <Select
                value={(field.value as string | undefined) ?? undefined}
                onValueChange={field.onChange}
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Wire">Wire</SelectItem>
                  <SelectItem value="StuddedChain">Studded chain</SelectItem>
                  <SelectItem value="StudlessChain">Studless chain</SelectItem>
                  <SelectItem value="Polyester">Poliéster</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </InlineLabeled>
        <InlineLabeled label="Peso submerso">
          <Controller
            control={control}
            name={p('w')}
            render={({ field }) => (
              <UnitInput
                value={field.value as number}
                onChange={field.onChange}
                quantity="force_per_m"
                digits={2}
                className="h-8"
              />
            )}
          />
        </InlineLabeled>
        <InlineLabeled label="Peso seco">
          <Controller
            control={control}
            name={p('dry_weight')}
            render={({ field }) => (
              <UnitInput
                value={(field.value as number | null) ?? null}
                onChange={field.onChange}
                quantity="force_per_m"
                digits={2}
                className="h-8"
              />
            )}
          />
        </InlineLabeled>
        <InlineLabeled label="EA">
          <Controller
            control={control}
            name={p('EA')}
            render={({ field }) => (
              <UnitInput
                value={field.value as number}
                onChange={field.onChange}
                quantity="force"
                digits={2}
                className="h-8"
              />
            )}
          />
        </InlineLabeled>
        <InlineLabeled label="MBL">
          <Controller
            control={control}
            name={p('MBL')}
            render={({ field }) => (
              <UnitInput
                value={field.value as number}
                onChange={field.onChange}
                quantity="force"
                digits={2}
                className="h-8"
              />
            )}
          />
        </InlineLabeled>
        <InlineLabeled label="Módulo" unit="Pa" className="col-span-2">
          <Input
            type="number"
            step="1e9"
            {...register(p('modulus'), { valueAsNumber: true })}
            className="h-8 font-mono"
          />
        </InlineLabeled>
      </div>
    </div>
  )
}

function InlineLabeled({
  label,
  unit,
  className,
  children,
}: {
  label: string
  unit?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('flex flex-col gap-0.5', className)}>
      <Label className="flex items-center justify-between gap-1 text-[10px] font-medium text-muted-foreground">
        <span className="truncate">{label}</span>
        {unit && (
          <span className="shrink-0 font-mono text-[9px] font-normal">{unit}</span>
        )}
      </Label>
      {children}
    </div>
  )
}

function roundTo(value: number, digits: number): number {
  const f = 10 ** digits
  return Math.round(value * f) / f
}
