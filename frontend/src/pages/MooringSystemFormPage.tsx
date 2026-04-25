import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Loader2,
  Plus,
  Save,
  Trash2,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  Controller,
  useFieldArray,
  useForm,
} from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import {
  createMooringSystem,
  getMooringSystem,
  previewSolveMooringSystem,
  solveMooringSystem,
  updateMooringSystem,
} from '@/api/endpoints'
import type { MooringSystemInput, MooringSystemResult } from '@/api/types'
import { AttachmentsEditor } from '@/components/common/AttachmentsEditor'
import { MooringLineMetricsCard } from '@/components/common/MooringLineMetricsCard'
import { MooringSystemPlanView } from '@/components/common/MooringSystemPlanView'
import { SegmentEditor } from '@/components/common/SegmentEditor'
import { UnitInput } from '@/components/common/UnitInput'
import { Topbar } from '@/components/layout/Topbar'
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
import { Textarea } from '@/components/ui/textarea'
import { useDebounce } from '@/hooks/useDebounce'

const EMPTY_LINE = {
  name: 'L1',
  fairlead_azimuth_deg: 0,
  fairlead_radius: 30,
  segments: [
    {
      length: 800,
      w: 1100,
      EA: 5.83e8,
      MBL: 5.57e6,
      category: 'StuddedChain' as const,
      line_type: null as string | null,
    },
  ],
  boundary: {
    h: 300,
    mode: 'Tension' as const,
    input_value: 1_200_000,
    startpoint_depth: 0,
    endpoint_grounded: true,
  },
  seabed: { mu: 0.6, slope_rad: 0 },
  criteria_profile: 'MVP_Preliminary' as const,
  user_defined_limits: null,
  attachments: [] as never[],
}

function makeLine(idx: number, total: number): typeof EMPTY_LINE {
  const az = (360 / total) * idx
  return {
    ...EMPTY_LINE,
    name: `L${idx + 1}`,
    fairlead_azimuth_deg: az,
  }
}

export function MooringSystemFormPage() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const msysId = isEdit ? Number(id) : null
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: existing, isLoading: loadingExisting } = useQuery({
    queryKey: ['mooring-system', msysId],
    queryFn: () => getMooringSystem(msysId!),
    enabled: isEdit && Number.isFinite(msysId),
  })

  const form = useForm<MooringSystemInput>({
    defaultValues: {
      name: '',
      description: null,
      platform_radius: 30,
      lines: [makeLine(0, 4), makeLine(1, 4), makeLine(2, 4), makeLine(3, 4)],
    },
  })
  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { isSubmitting },
  } = form
  const linesArray = useFieldArray({ control, name: 'lines' })

  const [activeLine, setActiveLine] = useState(0)

  useEffect(() => {
    if (existing) {
      reset(existing.input as MooringSystemInput)
    }
  }, [existing, reset])

  const values = watch()
  const debouncedValues = useDebounce(values, 600)

  const previewQuery = useQuery<MooringSystemResult, ApiError>({
    queryKey: ['msys-preview', JSON.stringify(debouncedValues)],
    queryFn: () => previewSolveMooringSystem(debouncedValues),
    enabled:
      debouncedValues.lines.length > 0 &&
      debouncedValues.platform_radius > 0,
    retry: false,
    staleTime: 30_000,
  })

  const saveMutation = useMutation({
    mutationFn: async (v: MooringSystemInput) => {
      return isEdit
        ? updateMooringSystem(msysId!, v)
        : createMooringSystem(v)
    },
    onSuccess: (out) => {
      queryClient.invalidateQueries({ queryKey: ['mooring-systems'] })
      queryClient.invalidateQueries({ queryKey: ['mooring-system', out.id] })
      return out
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao salvar', { description: msg })
    },
  })

  async function onSubmit(v: MooringSystemInput) {
    const saved = await saveMutation.mutateAsync(v)
    toast.success(isEdit ? 'Sistema atualizado.' : 'Sistema criado.')
    navigate(`/mooring-systems/${saved.id}`)
  }

  async function onSubmitAndSolve(v: MooringSystemInput) {
    const saved = await saveMutation.mutateAsync(v)
    // Aguarda o solve antes de navegar para que o detail page já
    // mostre a execução nova (caso contrário, fica com a anterior até
    // o usuário clicar em Resolver manualmente).
    const solvePromise = solveMooringSystem(saved.id)
    toast.promise(solvePromise, {
      loading: 'Calculando…',
      success: 'Sistema calculado.',
      error: (err: unknown) => ({
        message: err instanceof ApiError ? err.message : 'Erro no solver',
      }),
    })
    try {
      await solvePromise
    } catch {
      // Se o solve falhar, navega assim mesmo — usuário verá o sistema
      // salvo + última execução anterior + toast de erro do solver.
    }
    queryClient.invalidateQueries({ queryKey: ['mooring-system', saved.id] })
    queryClient.invalidateQueries({ queryKey: ['mooring-systems'] })
    navigate(`/mooring-systems/${saved.id}`)
  }

  const breadcrumbs = [
    { label: 'Sistemas', to: '/mooring-systems' },
    { label: isEdit ? `#${msysId} Editar` : 'Novo' },
  ]

  const actions = (
    <>
      <Button variant="ghost" size="sm" asChild>
        <Link to={isEdit ? `/mooring-systems/${msysId}` : '/mooring-systems'}>
          Cancelar
        </Link>
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleSubmit(onSubmit)}
        disabled={isSubmitting || saveMutation.isPending}
      >
        <Save className="h-4 w-4" />
        Salvar
      </Button>
      <Button
        size="sm"
        onClick={handleSubmit(onSubmitAndSolve)}
        disabled={isSubmitting || saveMutation.isPending}
      >
        <Zap className="h-4 w-4" />
        Salvar e calcular
      </Button>
    </>
  )

  if (isEdit && loadingExisting) {
    return (
      <>
        <Topbar />
        <div className="p-6 text-sm text-muted-foreground">Carregando…</div>
      </>
    )
  }

  const previewLines = useMemo(
    () =>
      values.lines.map((l) => ({
        name: l.name,
        fairlead_azimuth_deg: l.fairlead_azimuth_deg,
        fairlead_radius: l.fairlead_radius,
      })),
    [values.lines],
  )

  return (
    <>
      <Topbar breadcrumbs={breadcrumbs} actions={actions} />
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {/* Metadata */}
        <Card className="shrink-0">
          <CardContent className="grid grid-cols-1 gap-3 p-3 md:grid-cols-[2fr_1fr_2fr]">
            <div className="flex flex-col gap-0.5">
              <Label className="text-[10px] font-medium text-muted-foreground">
                Nome do sistema *
              </Label>
              <Input
                {...register('name', { required: true })}
                placeholder="ex.: Spread 4× FPSO turret"
                className="h-8"
              />
            </div>
            <div className="flex flex-col gap-0.5">
              <Label className="text-[10px] font-medium text-muted-foreground">
                Raio plataforma (m)
              </Label>
              <Input
                type="number"
                step="0.5"
                {...register('platform_radius', { valueAsNumber: true })}
                className="h-8 font-mono"
              />
            </div>
            <div className="flex flex-col gap-0.5">
              <Label className="text-[10px] font-medium text-muted-foreground">
                Descrição
              </Label>
              <Textarea
                {...register('description')}
                placeholder="Notas sobre o sistema (opcional)"
                rows={1}
                className="min-h-8 resize-none text-sm"
              />
            </div>
          </CardContent>
        </Card>

        {/* Body: lines + plan view */}
        <div className="flex min-h-0 flex-1 gap-3">
          {/* Left: line tabs + form */}
          <Card className="min-h-0 flex-1 overflow-hidden">
            <div className="flex items-center gap-1 border-b border-border/60 bg-muted/20 px-2 py-1.5">
              <span className="px-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Linhas ({linesArray.fields.length})
              </span>
              <div className="flex flex-wrap items-center gap-1">
                {linesArray.fields.map((f, idx) => (
                  <button
                    key={f.id}
                    type="button"
                    className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                      activeLine === idx
                        ? 'bg-primary/15 text-primary'
                        : 'text-muted-foreground hover:bg-muted'
                    }`}
                    onClick={() => setActiveLine(idx)}
                  >
                    {values.lines[idx]?.name || `L${idx + 1}`}
                  </button>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 gap-1 px-2 text-[10px]"
                  onClick={() => {
                    const next = linesArray.fields.length
                    linesArray.append(makeLine(next, next + 1))
                    setActiveLine(next)
                  }}
                  disabled={linesArray.fields.length >= 16}
                >
                  <Plus className="h-3 w-3" />
                  Adicionar
                </Button>
                {linesArray.fields.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 gap-1 px-2 text-[10px] text-danger hover:bg-danger/10 hover:text-danger"
                    onClick={() => {
                      linesArray.remove(activeLine)
                      setActiveLine(Math.max(0, activeLine - 1))
                    }}
                  >
                    <Trash2 className="h-3 w-3" />
                    Remover
                  </Button>
                )}
              </div>
            </div>

            <div className="overflow-y-auto p-3">
              {linesArray.fields.map((field, idx) => (
                <div
                  key={field.id}
                  className={idx === activeLine ? '' : 'hidden'}
                >
                  <LineForm
                    index={idx}
                    control={control}
                    register={register}
                    watch={watch}
                    setValue={setValue}
                  />
                </div>
              ))}
            </div>
          </Card>

          {/* Right: plan view + aggregate */}
          <Card className="min-h-0 w-[420px] shrink-0 overflow-hidden">
            <CardContent className="flex h-full flex-col gap-3 p-3">
              <div className="aspect-square shrink-0">
                <MooringSystemPlanView
                  result={previewQuery.data}
                  platformRadius={values.platform_radius}
                  previewLines={previewLines}
                />
              </div>
              <div className="space-y-1.5 border-t border-border/60 pt-2 text-xs">
                {previewQuery.isFetching && (
                  <p className="flex items-center gap-1.5 text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" /> Calculando preview…
                  </p>
                )}
                {previewQuery.data && (
                  <>
                    <Row
                      label="Resultante"
                      value={`${(previewQuery.data.aggregate_force_magnitude / 1000).toFixed(2)} kN`}
                    />
                    {previewQuery.data.aggregate_force_magnitude > 0 && (
                      <Row
                        label="Direção"
                        value={`${previewQuery.data.aggregate_force_azimuth_deg.toFixed(1)}°`}
                      />
                    )}
                    <Row
                      label="Convergiram"
                      value={`${previewQuery.data.n_converged} / ${previewQuery.data.lines.length}`}
                    />
                    {previewQuery.data.n_invalid > 0 && (
                      <p className="text-danger">
                        {previewQuery.data.n_invalid} linha(s) sem convergência —
                        verifique a aba correspondente.
                      </p>
                    )}
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Cards de análise por linha (preview live). Atualiza
            conforme o usuário edita campos. Útil pra ver lado-a-lado
            como cada linha responde aos parâmetros. */}
        {values.lines.length > 0 && (
          <div className="shrink-0 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Análise por linha (preview ao vivo)
              </span>
              {previewQuery.isFetching && (
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  recalculando…
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {values.lines.map((line, idx) => (
                <MooringLineMetricsCard
                  key={`${idx}-${line.name}`}
                  lineSpec={line as unknown as import('@/api/types').SystemLineSpec}
                  result={previewQuery.data?.lines[idx] ?? undefined}
                  paletteIndex={idx}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between font-mono">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  )
}

function LineForm({
  index,
  control,
  register,
  watch,
  setValue,
}: {
  index: number
  control: import('react-hook-form').Control<MooringSystemInput>
  register: import('react-hook-form').UseFormRegister<MooringSystemInput>
  watch: import('react-hook-form').UseFormWatch<MooringSystemInput>
  setValue: import('react-hook-form').UseFormSetValue<MooringSystemInput>
}) {
  const base = `lines.${index}` as const
  // useFieldArray nested: cada linha tem seu próprio array de
  // `segments` e `attachments` dentro de `lines.${index}`.
  const segArray = useFieldArray({
    control,
    name: `${base}.segments` as const,
  })
  const attArray = useFieldArray({
    control,
    name: `${base}.attachments` as const,
  })
  return (
    <div className="space-y-4">
      {/* Identidade + posição */}
      <Card>
        <div className="border-b border-border/60 bg-muted/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Identidade & posição
        </div>
        <CardContent className="grid grid-cols-1 gap-3 p-3 md:grid-cols-3">
          <Field label="Nome">
            <Input
              {...register(`${base}.name` as const)}
              className="h-8"
              placeholder="L1"
            />
          </Field>
          <Field label="Azimuth (°)">
            <Input
              type="number"
              step="1"
              min="0"
              max="359.999"
              {...register(`${base}.fairlead_azimuth_deg` as const, {
                valueAsNumber: true,
              })}
              className="h-8 font-mono"
            />
          </Field>
          <Field label="Raio do fairlead (m)">
            <Input
              type="number"
              step="0.5"
              min="0.01"
              {...register(`${base}.fairlead_radius` as const, {
                valueAsNumber: true,
              })}
              className="h-8 font-mono"
            />
          </Field>
        </CardContent>
      </Card>

      {/* Segmentos da linha (multi-segmento, mesmo padrão da CaseFormPage) */}
      <Card>
        <div className="flex items-center gap-2 border-b border-border/60 bg-muted/10 px-3 py-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Segmentos ({segArray.fields.length})
          </span>
        </div>
        <CardContent className="space-y-3 p-3">
          <div className="flex flex-wrap gap-2">
            {segArray.fields.map((field, segIdx) => (
              <div
                key={field.id}
                className="min-w-[280px] max-w-[360px] flex-1"
              >
                <SegmentEditor<MooringSystemInput>
                  index={segIdx}
                  total={segArray.fields.length}
                  control={control}
                  register={register}
                  watch={watch}
                  setValue={setValue}
                  basePath={`${base}.segments`}
                  onMoveUp={
                    segIdx > 0
                      ? () => segArray.move(segIdx, segIdx - 1)
                      : undefined
                  }
                  onMoveDown={
                    segIdx < segArray.fields.length - 1
                      ? () => segArray.move(segIdx, segIdx + 1)
                      : undefined
                  }
                  onRemove={
                    segArray.fields.length > 1
                      ? () => segArray.remove(segIdx)
                      : undefined
                  }
                />
              </div>
            ))}
            {segArray.fields.length < 10 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-auto min-h-[44px] min-w-[280px] max-w-[360px] flex-1 gap-1.5 border-dashed text-[11px]"
                onClick={() => {
                  const last = segArray.fields[
                    segArray.fields.length - 1
                  ] as unknown as MooringSystemInput['lines'][number]['segments'][number]
                  segArray.append({ ...last, length: 100 })
                }}
              >
                + Adicionar segmento
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Boias e Clumps na linha */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AttachmentsEditor<MooringSystemInput>
          control={control}
          attachments={
            attArray as unknown as import('react-hook-form').UseFieldArrayReturn<
              MooringSystemInput,
              never,
              'id'
            >
          }
          segmentCount={segArray.fields.length}
          setValue={setValue}
          totalLength={segArray.fields.reduce(
            (acc, _f, idx) => {
              const len = (segArray.fields[idx] as unknown as { length?: number })
                .length
              return acc + (len ?? 0)
            },
            0,
          )}
          kind="buoy"
          basePath={`${base}.attachments`}
        />
        <AttachmentsEditor<MooringSystemInput>
          control={control}
          attachments={
            attArray as unknown as import('react-hook-form').UseFieldArrayReturn<
              MooringSystemInput,
              never,
              'id'
            >
          }
          segmentCount={segArray.fields.length}
          setValue={setValue}
          totalLength={segArray.fields.reduce(
            (acc, _f, idx) => {
              const len = (segArray.fields[idx] as unknown as { length?: number })
                .length
              return acc + (len ?? 0)
            },
            0,
          )}
          kind="clump_weight"
          basePath={`${base}.attachments`}
        />
      </div>

      {/* Boundary + seabed */}
      <Card>
        <div className="border-b border-border/60 bg-muted/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Contorno & ambiente
        </div>
        <CardContent className="grid grid-cols-1 gap-2 p-3 md:grid-cols-4">
          <Field label="Lâmina (m)">
            <Input
              type="number"
              step="1"
              {...register(`${base}.boundary.h` as const, {
                valueAsNumber: true,
              })}
              className="h-8 font-mono"
            />
          </Field>
          <Field label="Modo">
            <Controller
              control={control}
              name={`${base}.boundary.mode` as const}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Tension">Tension</SelectItem>
                    <SelectItem value="Range">Range</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </Field>
          <Field label="Input value">
            <Controller
              control={control}
              name={`${base}.boundary.input_value` as const}
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
          </Field>
          <Field label="μ atrito">
            <Input
              type="number"
              step="0.05"
              min="0"
              {...register(`${base}.seabed.mu` as const, {
                valueAsNumber: true,
              })}
              className="h-8 font-mono"
            />
          </Field>
        </CardContent>
      </Card>
    </div>
  )
}

function Field({
  label,
  className,
  children,
}: {
  label: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={`flex flex-col gap-0.5 ${className ?? ''}`}>
      <Label className="text-[10px] font-medium text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  )
}
