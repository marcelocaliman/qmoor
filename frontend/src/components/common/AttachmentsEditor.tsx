import { Anchor, Plus, Trash2, Waves } from 'lucide-react'
import { useEffect } from 'react'
import {
  Controller,
  useWatch,
  type Control,
  type FieldValues,
  type Path,
  type UseFieldArrayReturn,
  type UseFormSetValue,
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

export interface AttachmentsEditorProps<
  T extends FieldValues = CaseFormValues,
> {
  control: Control<T>
  attachments: UseFieldArrayReturn<T, never, 'id'>
  segmentCount: number
  /**
   * `setValue` do form pai. Necessário para o toggle de modo
   * Junção/Distância (F5.4.6a) — quando o usuário troca de modo,
   * limpamos um dos dois campos (`position_index` ou
   * `position_s_from_anchor`).
   */
  setValue: UseFormSetValue<T>
  /**
   * Quando definido, mostra somente itens deste tipo (boias OU clumps).
   * Sem o filtro, mostra ambos junto com seletor de tipo (modo legacy).
   */
  kind?: AttachmentKind
  /**
   * Caminho-base para o array no form (default `'attachments'`).
   * Use, por exemplo, `'lines.0.attachments'` para reusar este editor
   * dentro de um sistema multi-linha.
   */
  basePath?: string
  /**
   * Comprimento total da linha (m), usado para o input de distância
   * exibir o range válido. Quando ausente, usa um placeholder vazio.
   */
  totalLength?: number
}

/**
 * Editor de attachments (boias e clump weights).
 *
 * F5.4.6a: attachments podem ficar em qualquer arc length da linha
 * (`position_s_from_anchor` em metros) — o solver divide o segmento
 * que contém aquela posição automaticamente em sub-segmentos do
 * mesmo material. Por isso, basta **1 segmento** para adicionar
 * boia/clump (a versão antiga exigia 2+ porque só aceitava em
 * junções pré-existentes).
 *
 * O modo "junção" (legacy) ainda é exposto via toggle — útil quando
 * a linha tem materiais diferentes e o usuário quer fixar o
 * attachment exatamente na fronteira dos segmentos.
 */
export function AttachmentsEditor<T extends FieldValues = CaseFormValues>({
  control,
  attachments,
  segmentCount,
  setValue,
  kind,
  basePath = 'attachments',
  totalLength,
}: AttachmentsEditorProps<T>) {
  const maxJunctions = Math.max(0, segmentCount - 1)
  // F5.4.6a/F5.6: precisa de pelo menos 1 segmento. Modo distância
  // funciona com qualquer N ≥ 1; modo junção precisaria N ≥ 2 mas
  // o toggle só fica disponível quando aplicável (lógica no Row).
  const canAdd = segmentCount >= 1
  const hasJunctions = segmentCount >= 2

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
    // F5.4.6a: por padrão, novos attachments usam `position_s_from_anchor`
    // — mais flexível e didático ("a 100 m da âncora") do que apontar
    // para uma junção pré-existente.
    attachments.append({
      kind: kind ?? 'buoy',
      submerged_force: 50_000,
      position_s_from_anchor: 100,
      position_index: null,
      name: null,
    } as never)
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
            adicione 1+ segmento para usar
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
                setValue={setValue}
                maxJunction={maxJunctions - 1}
                hasJunctions={hasJunctions}
                showKindSelect={!kind}
                basePath={basePath}
                totalLength={totalLength}
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

function AttachmentRow<T extends FieldValues = CaseFormValues>({
  realIndex,
  control,
  setValue,
  maxJunction,
  hasJunctions,
  showKindSelect,
  basePath,
  totalLength,
  onRemove,
}: {
  realIndex: number
  control: Control<T>
  setValue: UseFormSetValue<T>
  maxJunction: number
  hasJunctions: boolean
  showKindSelect: boolean
  basePath: string
  totalLength?: number
  onRemove: () => void
}) {
  const p = (suffix: string): Path<T> =>
    `${basePath}.${realIndex}.${suffix}` as Path<T>
  // Modo derivado dos campos atuais: se `position_s_from_anchor` está
  // setado, mostra input de distância; caso contrário, input de junção.
  const positionS = useWatch({ control, name: p('position_s_from_anchor') })
  const mode: 'distance' | 'junction' =
    positionS != null ? 'distance' : 'junction'

  // Se o usuário tinha um attachment em modo "junção" e depois removeu
  // segmentos a ponto de não haver mais junções (1 segmento só),
  // migra automaticamente para modo "distância" para evitar erro
  // INVALID_CASE no solver.
  useEffect(() => {
    if (!hasJunctions && mode === 'junction') {
      setValue(p('position_s_from_anchor'), 100 as never, {
        shouldValidate: true,
      })
      setValue(p('position_index'), null as never, { shouldValidate: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasJunctions])

  function setMode(next: 'distance' | 'junction') {
    if (next === mode) return
    if (next === 'distance') {
      setValue(p('position_s_from_anchor'), 100 as never, {
        shouldValidate: true,
      })
      setValue(p('position_index'), null as never, { shouldValidate: true })
    } else {
      setValue(p('position_index'), 0 as never, { shouldValidate: true })
      setValue(p('position_s_from_anchor'), null as never, {
        shouldValidate: true,
      })
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-border/40 bg-background p-2">
      <div className="flex items-center gap-2">
        <Controller
          control={control}
          name={p('kind')}
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
          name={p('name')}
          render={({ field }) => (
            <Input
              type="text"
              value={(field.value as string | null) ?? ''}
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
              name={p('kind')}
              render={({ field }) => (
                <Select
                  value={field.value as string}
                  onValueChange={field.onChange}
                >
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
            name={p('submerged_force')}
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
        </div>
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center justify-between gap-1">
            <Label className="text-[10px] font-medium text-muted-foreground">
              {mode === 'distance' ? 'Distância da âncora (m)' : 'Junção'}
            </Label>
            {hasJunctions && (
              <button
                type="button"
                onClick={() =>
                  setMode(mode === 'distance' ? 'junction' : 'distance')
                }
                className="text-[9px] uppercase tracking-wide text-primary hover:underline"
                title="Alternar modo de posicionamento"
              >
                {mode === 'distance' ? '↺ junção' : '↺ distância'}
              </button>
            )}
          </div>
          {mode === 'distance' ? (
            <Controller
              control={control}
              name={p('position_s_from_anchor')}
              render={({ field }) => (
                <Input
                  type="number"
                  min={0.01}
                  max={totalLength ? totalLength - 0.01 : undefined}
                  step={1}
                  value={(field.value as number | null) ?? 0}
                  onChange={(e) =>
                    field.onChange(parseFloat(e.target.value || '0'))
                  }
                  className="h-8 font-mono"
                  title={
                    totalLength
                      ? `Range válido: 0 < s < ${totalLength.toFixed(1)} m`
                      : 'Distância em metros desde a âncora ao longo da linha'
                  }
                />
              )}
            />
          ) : (
            <Controller
              control={control}
              name={p('position_index')}
              render={({ field }) => (
                <Input
                  type="number"
                  min={0}
                  max={maxJunction}
                  step={1}
                  value={(field.value as number | null) ?? 0}
                  onChange={(e) =>
                    field.onChange(parseInt(e.target.value || '0', 10))
                  }
                  className="h-8 font-mono"
                  title={`Entre seg ${
                    ((field.value as number | null) ?? 0) + 1
                  } e seg ${((field.value as number | null) ?? 0) + 2}`}
                />
              )}
            />
          )}
        </div>
      </div>
      {/* F5.6.7 — Tether (pendant): comprimento do cabo de conexão
          entre o corpo (boia/clump) e a linha principal. Em mooring
          real, boias quase sempre ficam ligadas à linha principal
          via pendant; valor opcional aqui afeta apenas a
          visualização (corpo desenhado deslocado da linha por essa
          distância). A força submersa permanece o EFEITO LÍQUIDO
          no ponto de conexão. */}
      <div className="flex items-center gap-2">
        <Label className="shrink-0 text-[10px] font-medium text-muted-foreground">
          Pendant (m)
        </Label>
        <Controller
          control={control}
          name={p('tether_length')}
          render={({ field }) => (
            <Input
              type="number"
              min={0}
              step={0.5}
              value={(field.value as number | null) ?? ''}
              onChange={(e) => {
                const v = parseFloat(e.target.value || '')
                field.onChange(Number.isFinite(v) && v > 0 ? v : null)
              }}
              placeholder="0 = direto na linha"
              className="h-7 flex-1 font-mono text-xs"
              title={
                'Comprimento do pendant (cabo de conexão) entre o ' +
                'corpo e a linha principal. A força submersa deve ' +
                'continuar sendo o efeito líquido no ponto de ' +
                'conexão (empuxo do corpo menos peso do pendant).'
              }
            />
          )}
        />
      </div>
    </div>
  )
}
