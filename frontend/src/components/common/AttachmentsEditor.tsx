import { Anchor, ChevronDown, ChevronUp, Plus, Trash2, Waves } from 'lucide-react'
import { useState } from 'react'
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
import type { CaseFormValues } from '@/lib/caseSchema'
import { cn } from '@/lib/utils'

export interface AttachmentsEditorProps {
  control: Control<CaseFormValues>
  attachments: UseFieldArrayReturn<CaseFormValues, 'attachments', 'id'>
  segmentCount: number
}

/**
 * Editor de attachments (boias e clump weights) — F5.2.
 *
 * Cada attachment fica numa junção entre dois segmentos (position_index =
 * 0 → entre seg 0 e seg 1, etc.). Visualmente collapsible: começa fechado,
 * o usuário expande quando precisa adicionar.
 *
 * Exibido apenas quando há ≥ 2 segmentos (com 1 segmento não há junção).
 */
export function AttachmentsEditor({
  control,
  attachments,
  segmentCount,
}: AttachmentsEditorProps) {
  const [expanded, setExpanded] = useState(attachments.fields.length > 0)
  const maxJunctions = Math.max(0, segmentCount - 1)

  if (segmentCount < 2) return null

  return (
    <div className="rounded-md border border-border/60 bg-muted/10">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          'flex w-full items-center gap-2 px-3 py-2 text-left',
          'text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground',
          'transition-colors hover:bg-muted/30',
        )}
      >
        <Waves className="h-3.5 w-3.5" />
        <span>
          Boias e clump weights ({attachments.fields.length})
        </span>
        {attachments.fields.length === 0 && !expanded && (
          <span className="ml-1 text-[9px] font-normal normal-case text-muted-foreground/70">
            opcional — clique para adicionar
          </span>
        )}
        <span className="ml-auto">
          {expanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-border/60 p-2">
          {attachments.fields.map((field, idx) => (
            <AttachmentRow
              key={field.id}
              index={idx}
              control={control}
              maxJunction={maxJunctions - 1}
              onRemove={() => attachments.remove(idx)}
            />
          ))}
          {attachments.fields.length < 20 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 w-full gap-1.5 border-dashed text-[11px]"
              onClick={() => {
                const usedJunctions = new Set(
                  (attachments.fields as unknown as Array<{
                    position_index: number
                  }>).map((a) => a.position_index),
                )
                let firstFree = 0
                while (
                  firstFree < maxJunctions && usedJunctions.has(firstFree)
                ) firstFree += 1
                attachments.append({
                  kind: 'buoy',
                  submerged_force: 50_000,
                  position_index: Math.min(firstFree, maxJunctions - 1),
                  name: null,
                })
              }}
            >
              <Plus className="h-3.5 w-3.5" />
              Adicionar boia ou clump
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function AttachmentRow({
  index,
  control,
  maxJunction,
  onRemove,
}: {
  index: number
  control: Control<CaseFormValues>
  maxJunction: number
  onRemove: () => void
}) {
  return (
    <div className="grid grid-cols-[auto_1fr_1fr_auto_auto] items-end gap-2 rounded-md bg-background p-2">
      <Controller
        control={control}
        name={`attachments.${index}.kind`}
        render={({ field }) => (
          <span
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded',
              field.value === 'buoy'
                ? 'bg-primary/15 text-primary'
                : 'bg-warning/20 text-warning',
            )}
            title={field.value === 'buoy' ? 'Boia (empuxo)' : 'Clump weight'}
          >
            {field.value === 'buoy' ? (
              <Waves className="h-4 w-4" />
            ) : (
              <Anchor className="h-4 w-4" />
            )}
          </span>
        )}
      />

      <div className="flex flex-col gap-0.5">
        <Label className="text-[10px] font-medium text-muted-foreground">
          Tipo
        </Label>
        <Controller
          control={control}
          name={`attachments.${index}.kind`}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="buoy">Boia (empuxo)</SelectItem>
                <SelectItem value="clump_weight">Clump weight</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>

      <div className="flex flex-col gap-0.5">
        <Label className="text-[10px] font-medium text-muted-foreground">
          Força submersa
        </Label>
        <Controller
          control={control}
          name={`attachments.${index}.submerged_force`}
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
          name={`attachments.${index}.position_index`}
          render={({ field }) => (
            <Input
              type="number"
              min={0}
              max={maxJunction}
              step={1}
              value={field.value ?? 0}
              onChange={(e) => field.onChange(parseInt(e.target.value || '0', 10))}
              className="h-8 w-16 font-mono"
              title={`Entre seg ${(field.value ?? 0) + 1} e seg ${(field.value ?? 0) + 2}`}
            />
          )}
        />
      </div>

      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 w-8 p-0 text-danger hover:bg-danger/10 hover:text-danger"
        onClick={onRemove}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
