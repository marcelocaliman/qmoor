import { Anchor, Plus, Trash2, Waves } from 'lucide-react'
import {
  Controller,
  type Control,
  type UseFieldArrayReturn,
} from 'react-hook-form'
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
import type { AttachmentKind } from '@/api/types'
import type { CaseFormValues } from '@/lib/caseSchema'
import { cn } from '@/lib/utils'

export interface AttachmentsEditorProps {
  control: Control<CaseFormValues>
  attachments: UseFieldArrayReturn<CaseFormValues, 'attachments', 'id'>
  segmentCount: number
  /**
   * Quando definido, mostra somente itens deste tipo (boias OU clumps).
   * Sem o filtro, mostra ambos junto com seletor de tipo (modo legacy).
   */
  kind?: AttachmentKind
}

/**
 * Editor de attachments (boias e clump weights).
 * Cada attachment fica numa junção entre dois segmentos (position_index =
 * 0 → entre seg 0 e seg 1, etc.). Quando há apenas 1 segmento, mostra
 * estado vazio com instrução para adicionar mais segmentos antes.
 */
export function AttachmentsEditor({
  control,
  attachments,
  segmentCount,
  kind,
}: AttachmentsEditorProps) {
  const maxJunctions = Math.max(0, segmentCount - 1)
  const canAdd = segmentCount >= 2

  const allFields = attachments.fields as unknown as Array<{
    id: string
    kind: AttachmentKind
    position_index: number
  }>
  const visibleItems = (kind
    ? allFields.map((f, realIdx) => ({ field: f, realIdx })).filter(
        ({ field }) => field.kind === kind,
      )
    : allFields.map((f, realIdx) => ({ field: f, realIdx })))

  const Icon = kind === 'clump_weight' ? Anchor : Waves
  const title =
    kind === 'buoy'
      ? 'Boias'
      : kind === 'clump_weight'
        ? 'Clump weights'
        : 'Boias e clump weights'

  const addNew = () => {
    const usedJunctions = new Set(allFields.map((a) => a.position_index))
    let firstFree = 0
    while (firstFree < maxJunctions && usedJunctions.has(firstFree))
      firstFree += 1
    attachments.append({
      kind: kind ?? 'buoy',
      submerged_force: 50_000,
      position_index: Math.min(firstFree, maxJunctions - 1),
      name: null,
    })
  }

  const emptyMsg =
    kind === 'buoy'
      ? 'Nenhuma boia. Adicione uma para gerar empuxo positivo numa junção entre segmentos.'
      : kind === 'clump_weight'
        ? 'Nenhum clump weight. Adicione um peso pontual numa junção entre segmentos.'
        : 'Nenhum elemento pontual. Adicione uma boia ou clump weight numa junção entre segmentos.'

  const addLabel =
    kind === 'buoy'
      ? 'Adicionar boia'
      : kind === 'clump_weight'
        ? 'Adicionar clump weight'
        : 'Adicionar elemento pontual'

  return (
    <div className="rounded-md border border-border/60 bg-muted/10">
      <div className="flex items-center gap-2 border-b border-border/60 bg-muted/20 px-3 py-1.5">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {title}
        </span>
        <span className="text-[10px] text-muted-foreground/70">
          ({visibleItems.length})
        </span>
        {!canAdd && (
          <span className="ml-auto text-[10px] text-muted-foreground/70">
            adicione 2+ segmentos para usar
          </span>
        )}
      </div>
      <div className="space-y-2 p-2">
        {visibleItems.length === 0 && !canAdd && (
          <p className="px-2 py-1.5 text-[11px] text-muted-foreground">
            {emptyMsg}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {visibleItems.map(({ field, realIdx }) => (
            <div
              key={field.id}
              className="min-w-[280px] max-w-[360px] flex-1"
            >
              <AttachmentRow
                realIndex={realIdx}
                control={control}
                maxJunction={maxJunctions - 1}
                showKindSelect={!kind}
                onRemove={() => attachments.remove(realIdx)}
              />
            </div>
          ))}
          {canAdd && allFields.length < 20 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-auto min-h-[44px] min-w-[280px] max-w-[360px] flex-1 gap-1.5 border-dashed text-[11px]"
              onClick={addNew}
            >
              <Plus className="h-3.5 w-3.5" />
              {addLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function AttachmentRow({
  realIndex,
  control,
  maxJunction,
  showKindSelect,
  onRemove,
}: {
  realIndex: number
  control: Control<CaseFormValues>
  maxJunction: number
  showKindSelect: boolean
  onRemove: () => void
}) {
  return (
    <div className="space-y-2 rounded-md border border-border/40 bg-background p-2">
      <div className="flex items-center gap-2">
        <Controller
          control={control}
          name={`attachments.${realIndex}.kind`}
          render={({ field }) => (
            <span
              className={cn(
                'flex h-7 w-7 shrink-0 items-center justify-center rounded',
                field.value === 'buoy'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-warning/20 text-warning',
              )}
              title={field.value === 'buoy' ? 'Boia (empuxo)' : 'Clump weight'}
            >
              {field.value === 'buoy' ? (
                <Waves className="h-3.5 w-3.5" />
              ) : (
                <Anchor className="h-3.5 w-3.5" />
              )}
            </span>
          )}
        />
        <Controller
          control={control}
          name={`attachments.${realIndex}.name`}
          render={({ field }) => (
            <Input
              type="text"
              value={field.value ?? ''}
              onChange={(e) => field.onChange(e.target.value || null)}
              placeholder="Nome (opcional)"
              className="h-7 flex-1 text-xs"
              maxLength={80}
            />
          )}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 w-7 shrink-0 p-0 text-danger hover:bg-danger/10 hover:text-danger"
          onClick={onRemove}
          title="Remover"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
      <div
        className={cn(
          'grid gap-2',
          showKindSelect ? 'grid-cols-3' : 'grid-cols-2',
        )}
      >
        {showKindSelect && (
          <div className="flex flex-col gap-0.5">
            <Label className="text-[10px] font-medium text-muted-foreground">
              Tipo
            </Label>
            <Controller
              control={control}
              name={`attachments.${realIndex}.kind`}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="buoy">Boia</SelectItem>
                    <SelectItem value="clump_weight">Clump</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <Label className="text-[10px] font-medium text-muted-foreground">
            Força submersa
          </Label>
          <Controller
            control={control}
            name={`attachments.${realIndex}.submerged_force`}
            render={({ field }) => (
              <UnitInput
                value={field.value}
                onChange={field.onChange}
                quantity="force"
                digits={2}
                className="h-8"
              />
            )}
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <Label className="text-[10px] font-medium text-muted-foreground">
            Junção
          </Label>
          <Controller
            control={control}
            name={`attachments.${realIndex}.position_index`}
            render={({ field }) => (
              <Input
                type="number"
                min={0}
                max={maxJunction}
                step={1}
                value={field.value ?? 0}
                onChange={(e) =>
                  field.onChange(parseInt(e.target.value || '0', 10))
                }
                className="h-8 font-mono"
                title={`Entre seg ${(field.value ?? 0) + 1} e seg ${(field.value ?? 0) + 2}`}
              />
            )}
          />
        </div>
      </div>
    </div>
  )
}
