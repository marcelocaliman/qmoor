import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Anchor,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Info,
  Loader2,
  Mountain,
  Save,
  Sigma,
  Waves,
  Wrench,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import {
  createCase,
  fetchCriteriaProfiles,
  getCase,
  previewSolve,
  solveCase,
  updateCase,
} from '@/api/endpoints'
import type { SolverResult } from '@/api/types'
import { AttachmentsEditor } from '@/components/common/AttachmentsEditor'
import { BathymetryPopover } from '@/components/common/BathymetryPopover'
import { CatenaryPlot } from '@/components/common/CatenaryPlot'
import { SegmentEditor } from '@/components/common/SegmentEditor'
import { UnitInput } from '@/components/common/UnitInput'
import {
  AlertBadge,
  StatusBadge,
} from '@/components/common/StatusBadge'
import { UtilizationGauge } from '@/components/common/UtilizationGauge'
import { Topbar } from '@/components/layout/Topbar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useDebounce } from '@/hooks/useDebounce'
import {
  EMPTY_CASE,
  caseInputSchema,
  type CaseFormValues,
} from '@/lib/caseSchema'
import {
  cn,
  fmtAngleDeg,
  fmtMeters,
  fmtNumber,
  fmtPercent,
  resolveSeabedDepths,
} from '@/lib/utils'
import { fmtForce, fmtForcePair as fmtForcePairUnits } from '@/lib/units'
import { useUnitsStore } from '@/store/units'

/**
 * Layout vertical: form compacto no topo (3 blocos em grid) +
 * gráfico preenchendo o espaço restante + métricas em faixa no rodapé.
 * Preview live via POST /solve/preview, 600ms debounce.
 */
export function CaseFormPage() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: existing, isLoading: loadingExisting } = useQuery({
    queryKey: ['case', id],
    queryFn: () => getCase(Number(id)),
    enabled: isEdit,
  })

  const { data: profiles } = useQuery({
    queryKey: ['criteria-profiles'],
    queryFn: fetchCriteriaProfiles,
    staleTime: 5 * 60_000,
  })

  const form = useForm<CaseFormValues>({
    resolver: zodResolver(caseInputSchema) as never,
    defaultValues: EMPTY_CASE,
    mode: 'onChange',
  })
  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isValid, isSubmitting },
  } = form

  // Lista dinâmica de segmentos (F5.1). useFieldArray cuida do estado.
  const segmentsArray = useFieldArray({ control, name: 'segments' })
  // Lista dinâmica de attachments (F5.2): boias e clump weights nas junções.
  const attachmentsArray = useFieldArray({ control, name: 'attachments' })

  useEffect(() => {
    if (existing) {
      reset({
        name: existing.input.name,
        description: existing.input.description ?? '',
        segments: existing.input.segments,
        boundary: existing.input.boundary,
        seabed: {
          mu: existing.input.seabed?.mu ?? 0,
          slope_rad: existing.input.seabed?.slope_rad ?? 0,
        },
        criteria_profile: existing.input.criteria_profile,
        user_defined_limits: existing.input.user_defined_limits ?? null,
        attachments: existing.input.attachments ?? [],
      })
    }
  }, [existing, reset])

  const values = watch()
  const mode = values.boundary.mode
  const criteriaProfile = values.criteria_profile
  const [notesOpen, setNotesOpen] = useState(false)
  const hasNotes = (values.description?.trim().length ?? 0) > 0

  // Contadores por tipo para os badges das abas Boias/Clumps. useFieldArray
  // só nos dá `id`s e índices; a fonte da verdade do `kind` é o watch.
  const watchedAttachments = (values.attachments ?? []) as Array<{
    kind: 'buoy' | 'clump_weight'
  }>
  const buoyCount = watchedAttachments.filter((a) => a.kind === 'buoy').length
  const clumpCount = watchedAttachments.filter(
    (a) => a.kind === 'clump_weight',
  ).length

  const debouncedValues = useDebounce(values, 600)
  const previewKey = useMemo(
    () =>
      JSON.stringify({
        s: debouncedValues.segments,
        b: debouncedValues.boundary,
        se: debouncedValues.seabed,
        cp: debouncedValues.criteria_profile,
        u: debouncedValues.user_defined_limits,
        a: debouncedValues.attachments,
      }),
    [debouncedValues],
  )

  /**
   * Preview-ready: somente os campos que entram no solver. Evita que o
   * gráfico fique bloqueado só porque o usuário ainda não preencheu o
   * nome do caso (que é exigência só pra persistir).
   */
  const previewReady = useMemo(() => {
    const seg = debouncedValues.segments?.[0]
    const b = debouncedValues.boundary
    if (!seg || !b) return false
    if (!(seg.length > 0) || !(seg.w > 0) || !(seg.EA > 0) || !(seg.MBL > 0))
      return false
    if (!(b.h > 0) || !(b.input_value > 0)) return false
    if ((debouncedValues.seabed?.mu ?? -1) < 0) return false
    if (
      debouncedValues.criteria_profile === 'UserDefined' &&
      !debouncedValues.user_defined_limits
    )
      return false
    return true
  }, [debouncedValues])

  const previewQuery = useQuery<SolverResult, ApiError>({
    queryKey: ['solve-preview', previewKey],
    queryFn: () => {
      const payload = {
        ...debouncedValues,
        // Backend exige name não vazio mesmo no preview — usa placeholder.
        name: debouncedValues.name?.trim() || 'preview',
        description: debouncedValues.description?.trim() || null,
      }
      return previewSolve(payload as never)
    },
    enabled: previewReady,
    retry: false,
    staleTime: 30_000,
  })

  const saveMutation = useMutation({
    mutationFn: async (v: CaseFormValues) => {
      const payload = {
        ...v,
        description: v.description?.trim() || null,
      } as unknown as Parameters<typeof createCase>[0]
      return isEdit ? updateCase(Number(id), payload) : createCase(payload)
    },
    onSuccess: (out) => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      queryClient.invalidateQueries({ queryKey: ['case', String(out.id)] })
      return out
    },
    onError: (err) => {
      toast.error('Falha ao salvar caso', {
        description: err instanceof ApiError ? err.message : String(err),
      })
    },
  })

  async function onSubmit(v: CaseFormValues) {
    try {
      const saved = await saveMutation.mutateAsync(v)
      toast.success(isEdit ? 'Caso atualizado.' : 'Caso criado.')
      navigate(`/cases/${saved.id}`)
    } catch { /* noop */ }
  }

  async function onSubmitAndSolve(v: CaseFormValues) {
    try {
      const saved = await saveMutation.mutateAsync(v)
      toast.promise(solveCase(saved.id), {
        loading: 'Calculando…',
        success: 'Caso calculado com sucesso.',
        error: (err: unknown) => ({
          message:
            err instanceof ApiError ? `Solver: ${err.message}` : 'Erro no solver',
        }),
      })
      navigate(`/cases/${saved.id}`)
    } catch { /* noop */ }
  }

  if (isEdit && loadingExisting) {
    return (
      <>
        <Topbar />
        <div className="p-6 text-sm text-muted-foreground">Carregando caso…</div>
      </>
    )
  }

  const breadcrumbs = [
    { label: 'Casos', to: '/cases' },
    { label: isEdit ? `#${id} Editar` : 'Novo' },
  ]

  const actions = (
    <>
      <PreviewStatusChip
        isFetching={previewQuery.isFetching}
        result={previewQuery.data}
        previewReady={previewReady}
      />
      <Button variant="ghost" size="sm" asChild>
        <Link to={isEdit ? `/cases/${id}` : '/cases'}>Cancelar</Link>
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleSubmit(onSubmit)}
        disabled={isSubmitting || saveMutation.isPending || !isValid}
      >
        <Save className="h-4 w-4" />
        Salvar
      </Button>
      <Button
        size="sm"
        onClick={handleSubmit(onSubmitAndSolve)}
        disabled={isSubmitting || saveMutation.isPending || !isValid}
      >
        <Zap className="h-4 w-4" />
        Salvar e calcular
      </Button>
    </>
  )

  return (
    <>
      <Topbar breadcrumbs={breadcrumbs} actions={actions} />
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">
        {/* ───── Linha 1: Metadados (compacta) — Nome + Notas ───── */}
        <Card className="shrink-0 overflow-hidden">
          <CardContent className="grid grid-cols-[minmax(0,560px)_auto] items-end gap-3 p-3">
            <InlineField
              label="Nome do caso"
              required
              error={errors.name?.message}
            >
              <Input
                {...register('name')}
                placeholder="ex.: BC-01 catenária suspensa"
                className="h-8"
              />
            </InlineField>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setNotesOpen((v) => !v)}
              className="h-8 gap-1.5 text-[11px]"
              title={hasNotes ? 'Notas preenchidas' : 'Adicionar notas'}
            >
              <FileText
                className={cn(
                  'h-3.5 w-3.5',
                  hasNotes ? 'text-primary' : 'text-muted-foreground',
                )}
              />
              Notas
              {notesOpen ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </Button>
          </CardContent>
          {notesOpen && (
            <div className="border-t border-border/60 px-3 pb-3 pt-2">
              <Textarea
                {...register('description')}
                rows={2}
                placeholder="Notas sobre o caso, condições de projeto, premissas, datas…"
                className="resize-none text-sm"
              />
            </div>
          )}
        </Card>

        {/* ───── Linha 2: tabs com inputs físicos do problema ───── */}
        <Card className="shrink-0 overflow-hidden">
          <Tabs defaultValue="linha" className="flex flex-col">
            <TabsList className="mx-3 mt-2 w-fit">
              <TabsTrigger value="linha" className="gap-1.5">
                <Wrench className="h-3.5 w-3.5" />
                Linha
                {segmentsArray.fields.length > 1 && (
                  <Badge
                    variant="secondary"
                    className="ml-0.5 h-4 px-1 text-[10px]"
                  >
                    {segmentsArray.fields.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="boias" className="gap-1.5">
                <Waves className="h-3.5 w-3.5" />
                Boias
                {buoyCount > 0 && (
                  <Badge
                    variant="secondary"
                    className="ml-0.5 h-4 px-1 text-[10px]"
                  >
                    {buoyCount}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="clumps" className="gap-1.5">
                <Anchor className="h-3.5 w-3.5" />
                Clumps
                {clumpCount > 0 && (
                  <Badge
                    variant="secondary"
                    className="ml-0.5 h-4 px-1 text-[10px]"
                  >
                    {clumpCount}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="ambiente" className="gap-1.5">
                <Mountain className="h-3.5 w-3.5" />
                Ambiente
              </TabsTrigger>
              <TabsTrigger value="analise" className="gap-1.5">
                <Sigma className="h-3.5 w-3.5" />
                Análise
              </TabsTrigger>
            </TabsList>

            {/*
             * Stack das abas: todos os <TabsContent> são forceMount + grid
             * stacked (col/row-start-1) para que o card sempre tome a altura
             * do maior conteúdo (Linha). Inativas ficam invisíveis e sem
             * pointer events, mas continuam contribuindo p/ o layout. Isso
             * mantém a posição do gráfico estável ao trocar de aba.
             */}
            <div className="grid">
              {/* ───────── Aba Linha: só segmentos ───────── */}
              <TabsContent
                forceMount
                value="linha"
                className="col-start-1 row-start-1 m-0 px-3 pb-3 pt-2 data-[state=inactive]:invisible data-[state=inactive]:pointer-events-none"
              >
              <div className="flex flex-wrap gap-2">
                {segmentsArray.fields.map((field, idx) => (
                  <div
                    key={field.id}
                    className="min-w-[280px] max-w-[360px] flex-1"
                  >
                    <SegmentEditor
                      index={idx}
                      total={segmentsArray.fields.length}
                      control={control}
                      register={register}
                      watch={watch}
                      setValue={setValue}
                      onMoveUp={
                        idx > 0
                          ? () => segmentsArray.move(idx, idx - 1)
                          : undefined
                      }
                      onMoveDown={
                        idx < segmentsArray.fields.length - 1
                          ? () => segmentsArray.move(idx, idx + 1)
                          : undefined
                      }
                      onRemove={
                        segmentsArray.fields.length > 1
                          ? () => segmentsArray.remove(idx)
                          : undefined
                      }
                    />
                  </div>
                ))}
                {segmentsArray.fields.length < 10 && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-auto min-h-[44px] min-w-[280px] max-w-[360px] flex-1 gap-1.5 border-dashed text-[11px]"
                    onClick={() => {
                      const last = segmentsArray.fields[
                        segmentsArray.fields.length - 1
                      ] as unknown as CaseFormValues['segments'][number]
                      segmentsArray.append({ ...last, length: 100 })
                    }}
                  >
                    + Adicionar segmento (próximo do fairlead)
                  </Button>
                )}
              </div>
            </TabsContent>

              {/* ───────── Aba Boias ───────── */}
              <TabsContent
                forceMount
                value="boias"
                className="col-start-1 row-start-1 m-0 px-3 pb-3 pt-2 data-[state=inactive]:invisible data-[state=inactive]:pointer-events-none"
              >
                <AttachmentsEditor
                  control={control}
                  attachments={attachmentsArray}
                  segmentCount={segmentsArray.fields.length}
                  kind="buoy"
                />
              </TabsContent>

              {/* ───────── Aba Clumps ───────── */}
              <TabsContent
                forceMount
                value="clumps"
                className="col-start-1 row-start-1 m-0 px-3 pb-3 pt-2 data-[state=inactive]:invisible data-[state=inactive]:pointer-events-none"
              >
                <AttachmentsEditor
                  control={control}
                  attachments={attachmentsArray}
                  segmentCount={segmentsArray.fields.length}
                  kind="clump_weight"
                />
              </TabsContent>

              {/* ───────── Aba Ambiente: seabed + fairlead depth ───────── */}
              <TabsContent
                forceMount
                value="ambiente"
                className="col-start-1 row-start-1 m-0 px-3 pb-3 pt-2 data-[state=inactive]:invisible data-[state=inactive]:pointer-events-none"
              >
              <div className="flex max-w-[320px] flex-col gap-3">
                <InlineField
                  label="Lâmina d'água (sob âncora)"
                  unit="m"
                  tooltip="Profundidade do seabed na coluna da âncora, medida da superfície"
                >
                  <Input
                    type="number"
                    step="1"
                    {...register('boundary.h', { valueAsNumber: true })}
                    className="h-8 font-mono"
                  />
                </InlineField>
                <InlineField
                  label="Prof. do fairlead"
                  unit="m"
                  tooltip="Profundidade do fairlead abaixo da superfície. 0 = na superfície. Igual à lâmina = linha horizontal no fundo."
                >
                  <Input
                    type="number"
                    step="1"
                    min="0"
                    {...register('boundary.startpoint_depth', {
                      valueAsNumber: true,
                    })}
                    className="h-8 font-mono"
                  />
                </InlineField>
                <InlineField
                  label="μ (atrito do seabed)"
                  tooltip="Wire ~0,3 · Corrente ~0,7 · Poliéster ~0,25"
                >
                  <Input
                    type="number"
                    step="0.05"
                    min="0"
                    {...register('seabed.mu', { valueAsNumber: true })}
                    className="h-8 font-mono"
                  />
                </InlineField>
                <InlineField
                  label="Inclinação seabed"
                  unit="°"
                  tooltip={
                    '0° = horizontal. Positivo: seabed sobe em direção ao fairlead. ' +
                    'Use o ícone ao lado para calcular pela batimetria nos dois pontos.'
                  }
                >
                  <Controller
                    control={control}
                    name="seabed.slope_rad"
                    render={({ field }) => (
                      <div className="flex items-stretch overflow-hidden rounded-md border border-input bg-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1">
                        <input
                          type="number"
                          step={0.5}
                          min={-45}
                          max={45}
                          value={
                            field.value != null
                              ? ((field.value * 180) / Math.PI).toFixed(2)
                              : '0'
                          }
                          onChange={(e) => {
                            const deg = parseFloat(e.target.value)
                            field.onChange(
                              Number.isFinite(deg) ? (deg * Math.PI) / 180 : 0,
                            )
                          }}
                          className="min-w-0 flex-1 bg-transparent px-2 py-1 font-mono text-sm tabular-nums focus:outline-none"
                        />
                        <BathymetryPopover
                          currentSlopeRad={field.value ?? 0}
                          currentH={watch('boundary.h') ?? 0}
                          currentXTotal={
                            previewQuery.data?.total_horz_distance ?? undefined
                          }
                          onApplyRad={(rad) => field.onChange(rad)}
                        />
                      </div>
                    )}
                  />
                </InlineField>
              </div>
            </TabsContent>

              {/* ───────── Aba Análise: modo + input + critério ───────── */}
              <TabsContent
                forceMount
                value="analise"
                className="col-start-1 row-start-1 m-0 px-3 pb-3 pt-2 data-[state=inactive]:invisible data-[state=inactive]:pointer-events-none"
              >
              <div className="flex max-w-[320px] flex-col gap-3">
                <InlineField label="Modo de cálculo">
                  <Controller
                    control={control}
                    name="boundary.mode"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Tension">
                            Tension (T_fl → X)
                          </SelectItem>
                          <SelectItem value="Range">
                            Range (X → T_fl)
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  />
                </InlineField>
                <InlineField
                  label={mode === 'Tension' ? 'T_fl no fairlead' : 'X total'}
                  unit={mode === 'Tension' ? undefined : 'm'}
                  tooltip={
                    mode === 'Tension'
                      ? 'Tração total no fairlead. Solver computa X.'
                      : 'Distância horizontal fairlead → âncora. Solver computa T_fl.'
                  }
                >
                  {mode === 'Tension' ? (
                    <Controller
                      control={control}
                      name="boundary.input_value"
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
                  ) : (
                    <Input
                      type="number"
                      step="any"
                      {...register('boundary.input_value', {
                        valueAsNumber: true,
                      })}
                      className="h-8 font-mono"
                    />
                  )}
                </InlineField>
                <InlineField label="Critério de utilização">
                  <Controller
                    control={control}
                    name="criteria_profile"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {profiles?.map((p) => (
                            <SelectItem key={p.name} value={p.name}>
                              <span className="flex items-center gap-2">
                                <span>{p.name}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  y{fmtNumber(p.yellow_ratio, 2)} · r
                                  {fmtNumber(p.red_ratio, 2)} · b
                                  {fmtNumber(p.broken_ratio, 2)}
                                </span>
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </InlineField>
                {criteriaProfile === 'UserDefined' && (
                  <div className="flex flex-col gap-2">
                    {(
                      ['yellow_ratio', 'red_ratio', 'broken_ratio'] as const
                    ).map((k) => (
                      <InlineField
                        key={k}
                        label={`${k.replace('_ratio', '')} (limite)`}
                      >
                        <Input
                          type="number"
                          step="0.05"
                          defaultValue={
                            watch(`user_defined_limits.${k}`) ??
                            (k === 'yellow_ratio'
                              ? 0.5
                              : k === 'red_ratio'
                                ? 0.6
                                : 1.0)
                          }
                          onChange={(e) =>
                            setValue(
                              `user_defined_limits.${k}`,
                              parseFloat(e.target.value),
                              { shouldValidate: true },
                            )
                          }
                          className="h-8 font-mono"
                        />
                      </InlineField>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>
            </div>
          </Tabs>
        </Card>

        {/* ───── Middle: gráfico (esquerda) + métricas empilhadas (direita) ───── */}
        <div className="flex min-h-0 flex-1 gap-3">
          <Card className="min-h-0 flex-1 overflow-hidden">
            <CardContent className="h-full p-1">
              <PlotArea
                isFetching={previewQuery.isFetching}
                result={previewQuery.data}
                previewReady={previewReady}
                attachments={debouncedValues.attachments ?? []}
                seabedSlopeRad={debouncedValues.seabed?.slope_rad ?? 0}
              />
            </CardContent>
          </Card>
          <MetricsColumn
            result={previewQuery.data}
            previewReady={previewReady}
            fallbackH={debouncedValues.boundary?.h ?? 0}
            slopeRad={debouncedValues.seabed?.slope_rad ?? 0}
          />
        </div>
      </div>
    </>
  )
}

/* ───────────────────────── Helpers visuais ─────────────────────────── */

function InlineField({
  label,
  unit,
  required,
  error,
  className,
  tooltip,
  children,
}: {
  label: string
  unit?: string
  required?: boolean
  error?: string
  className?: string
  tooltip?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('flex flex-col gap-0.5', className)}>
      <Label className="flex items-center justify-between gap-1 text-[10px] font-medium text-muted-foreground">
        <span className="flex items-center gap-1 truncate">
          {label}
          {required && <span className="text-danger">*</span>}
          {tooltip && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-2.5 w-2.5 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-xs text-xs">
                {tooltip}
              </TooltipContent>
            </Tooltip>
          )}
        </span>
        {unit && (
          <span className="shrink-0 font-mono text-[9px] font-normal">{unit}</span>
        )}
      </Label>
      {children}
      {error && <p className="text-[10px] text-danger">{error}</p>}
    </div>
  )
}

function PreviewStatusChip({
  isFetching,
  result,
  previewReady,
}: {
  isFetching: boolean
  result?: SolverResult
  previewReady: boolean
}) {
  let variant: 'success' | 'warning' | 'danger' | 'secondary' = 'secondary'
  let icon: React.ReactNode = null
  let label = 'Aguardando'

  if (!previewReady) {
    label = 'Preencha os parâmetros'
    icon = <Info className="mr-1 h-3 w-3" />
  } else if (isFetching) {
    variant = 'warning'
    icon = <Loader2 className="mr-1 h-3 w-3 animate-spin" />
    label = 'Calculando'
  } else if (result) {
    if (result.alert_level === 'broken' || result.status === 'invalid_case') {
      variant = 'danger'
      icon = <AlertCircle className="mr-1 h-3 w-3" />
      label = 'Inviável'
    } else if (
      result.alert_level === 'red' ||
      result.status === 'ill_conditioned'
    ) {
      variant = 'warning'
      icon = <AlertCircle className="mr-1 h-3 w-3" />
      label = 'Atenção'
    } else {
      variant = 'success'
      icon = <CheckCircle2 className="mr-1 h-3 w-3" />
      label = 'Convergiu'
    }
  }

  return (
    <Badge variant={variant} className="h-7 px-2 text-[11px]">
      {icon}
      {label}
    </Badge>
  )
}

function PlotArea({
  isFetching,
  result,
  previewReady,
  attachments,
  seabedSlopeRad,
}: {
  isFetching: boolean
  result?: SolverResult
  previewReady: boolean
  attachments?: import('@/api/types').LineAttachment[]
  seabedSlopeRad?: number
}) {
  if (!previewReady && !result) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <Info className="h-6 w-6 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Preencha os parâmetros do segmento e contorno para ver o perfil
          calculado.
        </p>
      </div>
    )
  }
  if (!result && isFetching) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Calculando preview…</p>
      </div>
    )
  }
  if (!result) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Aguardando dados</p>
      </div>
    )
  }
  const hasGeom = (result.coords_x?.length ?? 0) > 1
  if (!hasGeom) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <AlertCircle className="h-6 w-6 text-danger" />
        <p className="text-sm font-medium text-danger">Sem geometria calculada</p>
        {result.message && (
          <p className="max-w-md text-xs text-muted-foreground">
            {result.message}
          </p>
        )}
      </div>
    )
  }
  return (
    <CatenaryPlot
      result={result}
      attachments={attachments}
      seabedSlopeRad={seabedSlopeRad}
    />
  )
}

function MetricsColumn({
  result,
  previewReady,
  fallbackH,
  slopeRad,
}: {
  result?: SolverResult
  previewReady: boolean
  fallbackH: number
  slopeRad: number
}) {
  const system = useUnitsStore((s) => s.system)

  if (!previewReady || !result) {
    return (
      <div className="flex w-[280px] shrink-0 flex-col gap-2 overflow-y-auto">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="shrink-0 bg-muted/10">
            <CardContent className="flex h-[156px] flex-col justify-center gap-1 p-3">
              <div className="h-2.5 w-16 rounded bg-muted/40" />
              <div className="h-5 w-24 rounded bg-muted/30" />
              <div className="h-2 w-20 rounded bg-muted/30" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }
  const hasTouchdown =
    result.dist_to_first_td != null && result.dist_to_first_td > 0
  const vFairlead = result.fairlead_tension
    ? Math.sqrt(
        Math.max(result.fairlead_tension ** 2 - result.H ** 2, 0),
      )
    : 0
  const vAnchor = result.anchor_tension
    ? Math.sqrt(Math.max(result.anchor_tension ** 2 - result.H ** 2, 0))
    : 0

  // Formatador "primário (te) + secundário (kN)" para o card principal de tração.
  const tFlPair = fmtForcePairUnits(result.fairlead_tension, system)
  // Compatibilidade legacy: para execuções persistidas antes da F5.3.z,
  // depth_at_anchor/depth_at_fairlead vinham 0. Recompõe via fórmula
  // do backend (h − tan(slope)·X_total).
  const seabedDepths = resolveSeabedDepths(result, fallbackH, slopeRad)

  // Auxiliares para abreviar dentro das linhas dos demais cards.
  const F = (v: number): string => fmtForce(v, system)
  const Fpair = (v: number): string => {
    const p = fmtForcePairUnits(v, system)
    return `${p.primary} · ${p.secondary}`
  }

  return (
    <div className="flex w-[280px] shrink-0 flex-col gap-2 overflow-y-auto pr-1">
      {/* Tração — primário com gauge */}
      <MetricCard
        label="Tração no fairlead"
        primary={tFlPair.primary}
        secondary={`≈ ${tFlPair.secondary}`}
        rows={[
          ['V vertical', F(vFairlead)],
          [
            'Ângulo (horiz.)',
            fmtAngleDeg(result.angle_wrt_horz_fairlead, 1),
          ],
        ]}
        extra={
          <UtilizationGauge
            value={result.utilization}
            alertLevel={result.alert_level}
            className="mt-1.5"
          />
        }
      />

      {/* Geometria — completa */}
      <MetricCard
        label="Geometria"
        rows={[
          ['X total', fmtMeters(result.total_horz_distance, 1)],
          ['L suspenso', fmtMeters(result.total_suspended_length, 1)],
          ['L apoiado', fmtMeters(result.total_grounded_length, 1)],
          hasTouchdown
            ? ['Dist. touchdown', fmtMeters(result.dist_to_first_td!, 1)]
            : ['Touchdown', '—'],
          ['L esticado', fmtMeters(result.stretched_length, 2)],
          ['ΔL', fmtMeters(result.elongation, 3)],
          // Batimetria: profundidades nos dois pontos críticos. Útil em
          // casos com seabed inclinado (slope_rad ≠ 0); para horizontal
          // ambos são iguais a h.
          ['Prof. seabed @ âncora', fmtMeters(seabedDepths.atAnchor, 1)],
          ['Prof. seabed @ fairlead', fmtMeters(seabedDepths.atFairlead, 1)],
        ]}
      />

      {/* Forças — primário + secundário juntos */}
      <MetricCard
        label="Forças"
        rows={[
          ['H (horizontal)', Fpair(result.H)],
          ['T âncora', Fpair(result.anchor_tension)],
          ['V âncora', Fpair(vAnchor)],
          [
            'Ângulo âncora',
            fmtAngleDeg(result.angle_wrt_horz_anchor, 1),
          ],
        ]}
      />

      {/* Status + critério */}
      <MetricCard
        label="Status do solver"
        extra={
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge status={result.status} />
            <AlertBadge level={result.alert_level} />
          </div>
        }
        rows={[
          ['Utilização', fmtPercent(result.utilization, 2) + ' MBL'],
          ['Iterações', String(result.iterations_used)],
          ['H (param.)', F(result.H)],
        ]}
        footer={result.message || undefined}
      />
    </div>
  )
}

function MetricCard({
  label,
  primary,
  secondary,
  rows,
  extra,
  footer,
}: {
  label: string
  primary?: string
  secondary?: string
  rows?: Array<[string, string]>
  extra?: React.ReactNode
  footer?: string
}) {
  return (
    <Card className="shrink-0">
      <CardContent className="flex h-[156px] flex-col gap-1.5 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {label}
        </p>
        {primary && (
          <div className="flex items-baseline gap-1.5 font-mono tabular-nums leading-none">
            <span className="text-[17px] font-semibold tracking-tight">
              {primary}
            </span>
            {secondary && (
              <span className="text-[10px] font-normal text-muted-foreground">
                {secondary}
              </span>
            )}
          </div>
        )}
        {extra}
        {rows && (
          <div className="mt-auto space-y-[2px] font-mono text-[10.5px] leading-tight tabular-nums">
            {rows.map(([k, v]) => (
              <div
                key={k}
                className="flex items-baseline justify-between gap-2"
              >
                <span className="shrink-0 text-muted-foreground">{k}</span>
                <span className="truncate text-right font-medium text-foreground">
                  {v}
                </span>
              </div>
            ))}
          </div>
        )}
        {footer && (
          <p
            className="mt-1 line-clamp-2 font-mono text-[9.5px] leading-tight text-muted-foreground"
            title={footer}
          >
            {footer}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

