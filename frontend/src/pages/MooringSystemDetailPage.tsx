import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Compass,
  Download,
  Edit3,
  FileText,
  Loader2,
  Minus,
  Pause,
  Play,
  RotateCcw,
  Target,
  Wind,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import {
  computeWatchcircle,
  exportMooringSystemJsonUrl,
  exportMooringSystemPdfUrl,
  getMooringSystem,
  solveEquilibrium,
  solveMooringSystem,
} from '@/api/endpoints'
import type {
  MooringSystemResult,
  PlatformEquilibriumResult,
  WatchcircleResult,
} from '@/api/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MooringLineMetricsCard } from '@/components/common/MooringLineMetricsCard'
import { MooringSystemPlanView } from '@/components/common/MooringSystemPlanView'
import { Topbar } from '@/components/layout/Topbar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fmtNumber, fmtPercent } from '@/lib/utils'

export function MooringSystemDetailPage() {
  const { id } = useParams()
  const msysId = Number(id)
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['mooring-system', msysId],
    queryFn: () => getMooringSystem(msysId),
    enabled: Number.isFinite(msysId),
  })

  const solveMutation = useMutation({
    mutationFn: () => solveMooringSystem(msysId),
    onSuccess: (out) => {
      queryClient.invalidateQueries({ queryKey: ['mooring-system', msysId] })
      const r = out.result
      toast.success(
        `Resolvido — ${r.n_converged}/${r.lines.length} convergiram`,
        {
          description:
            r.aggregate_force_magnitude > 0
              ? `Resultante ${(r.aggregate_force_magnitude / 1000).toFixed(1)} kN @ ${r.aggregate_force_azimuth_deg.toFixed(1)}°`
              : 'Resultante ≈ 0 (spread balanceado)',
        },
      )
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao resolver', { description: msg })
    },
  })

  // F5.5 — Equilíbrio de plataforma sob carga ambiental.
  // Inputs em kN para usabilidade; convertemos para N só ao chamar a API.
  const [envFxKn, setEnvFxKn] = useState<number>(0)
  const [envFyKn, setEnvFyKn] = useState<number>(0)
  const [equilibrium, setEquilibrium] = useState<
    PlatformEquilibriumResult | null
  >(null)

  const equilibriumMutation = useMutation({
    mutationFn: () =>
      solveEquilibrium(msysId, {
        Fx: envFxKn * 1000,
        Fy: envFyKn * 1000,
      }),
    onSuccess: (res) => {
      setEquilibrium(res)
      if (res.converged) {
        toast.success(
          `Equilíbrio em ${res.offset_magnitude.toFixed(2)} m @ ` +
            `${res.offset_azimuth_deg.toFixed(1)}°`,
          {
            description: `${res.iterations} iterações · resíduo ${res.residual_magnitude.toFixed(1)} N`,
          },
        )
      } else {
        toast.warning('Equilíbrio não convergiu plenamente.', {
          description: res.message,
        })
      }
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha no equilíbrio', { description: msg })
    },
  })

  function resetEquilibrium() {
    setEnvFxKn(0)
    setEnvFyKn(0)
    setEquilibrium(null)
  }

  // F5.6 — Watchcircle (varredura azimutal de carga ambiental).
  const [wcMagnitudeKn, setWcMagnitudeKn] = useState<number>(50)
  const [wcSteps, setWcSteps] = useState<number>(36)
  const [watchcircle, setWatchcircle] = useState<WatchcircleResult | null>(
    null,
  )
  // Animação: índice do ponto da varredura sendo "tocado" (também
  // dirige o equilíbrio mostrado na plan view).
  const [wcAnimIdx, setWcAnimIdx] = useState<number>(0)
  const [wcPlaying, setWcPlaying] = useState<boolean>(false)

  const watchcircleMutation = useMutation({
    mutationFn: () =>
      computeWatchcircle(msysId, wcMagnitudeKn * 1000, wcSteps),
    onSuccess: (res) => {
      setWatchcircle(res)
      setWcAnimIdx(0)
      // Sincroniza equilíbrio inicial com o ponto 0 da varredura
      if (res.points[0]) setEquilibrium(res.points[0].equilibrium)
      toast.success(
        `Watchcircle calculado em ${res.n_steps} passos`,
        {
          description: `Offset máximo ${res.max_offset_magnitude.toFixed(2)} m @ ${res.max_offset_load_azimuth_deg.toFixed(0)}° · ${res.n_failed} falhas`,
        },
      )
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha no watchcircle', { description: msg })
    },
  })

  // Animação automática (play/pause): avança 1 passo a cada 250 ms
  useEffect(() => {
    if (!wcPlaying || !watchcircle) return
    const id = setInterval(() => {
      setWcAnimIdx((prev) => {
        const next = (prev + 1) % watchcircle.points.length
        const nextEq = watchcircle.points[next]?.equilibrium
        if (nextEq) setEquilibrium(nextEq)
        return next
      })
    }, 250)
    return () => clearInterval(id)
  }, [wcPlaying, watchcircle])

  function resetWatchcircle() {
    setWatchcircle(null)
    setWcPlaying(false)
    setWcAnimIdx(0)
  }

  const breadcrumbs = [
    { label: 'Sistemas', to: '/mooring-systems' },
    { label: data?.name ?? `#${msysId}` },
  ]

  const latestResult = data?.latest_executions?.[0]?.result as
    | MooringSystemResult
    | undefined

  const previewLines = useMemo(
    () =>
      data?.input.lines.map((l) => ({
        name: l.name,
        fairlead_azimuth_deg: l.fairlead_azimuth_deg,
        fairlead_radius: l.fairlead_radius,
      })) ?? [],
    [data],
  )

  const actions = (
    <>
      <Button asChild variant="outline" size="sm">
        <a
          href={exportMooringSystemJsonUrl(msysId)}
          target="_blank"
          rel="noreferrer"
        >
          <Download className="h-4 w-4" />
          JSON
        </a>
      </Button>
      <Button asChild variant="outline" size="sm">
        <a
          href={exportMooringSystemPdfUrl(msysId)}
          target="_blank"
          rel="noreferrer"
        >
          <FileText className="h-4 w-4" />
          PDF
        </a>
      </Button>
      <Button asChild variant="outline" size="sm">
        <Link to={`/mooring-systems/${msysId}/edit`}>
          <Edit3 className="h-4 w-4" />
          Editar
        </Link>
      </Button>
      <Button
        size="sm"
        onClick={() => solveMutation.mutate()}
        disabled={solveMutation.isPending}
      >
        {solveMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Zap className="h-4 w-4" />
        )}
        Resolver
      </Button>
    </>
  )

  if (isLoading) {
    return (
      <>
        <Topbar breadcrumbs={breadcrumbs} />
        <div className="p-6 text-sm text-muted-foreground">Carregando…</div>
      </>
    )
  }

  if (isError || !data) {
    return (
      <>
        <Topbar breadcrumbs={breadcrumbs} />
        <div className="p-6 text-sm text-danger">
          {error instanceof ApiError
            ? error.message
            : 'Sistema não encontrado.'}
        </div>
      </>
    )
  }

  return (
    <>
      <Topbar breadcrumbs={breadcrumbs} actions={actions} />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          {/* Plan view — altura limitada (700px) em vez de aspect-
              square, evita ocupar todo o espaço vertical e libera a
              coluna direita para acomodar agregado + cards de linha. */}
          <Card className="overflow-hidden">
            <CardContent className="h-[700px] p-3">
              <MooringSystemPlanView
                result={latestResult}
                platformRadius={data.input.platform_radius}
                previewLines={previewLines}
                equilibrium={equilibrium ?? undefined}
                watchcircle={watchcircle ?? undefined}
              />
            </CardContent>
          </Card>

          {/* Coluna direita: agregado + cards de linha empilhados.
              A coluna inteira tem altura 700px (mesma do plan view)
              com overflow vertical, mantendo lado a lado. */}
          <div className="flex h-[700px] flex-col gap-3 overflow-y-auto pr-1">
            <Card className="shrink-0">
              <CardContent className="space-y-3 p-4">
                <h3 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Resultado agregado
                </h3>
                {latestResult ? (
                  <AggregateMetrics result={latestResult} />
                ) : (
                  <div className="flex flex-col items-start gap-2 text-sm text-muted-foreground">
                    <p>
                      Nenhuma execução registrada. Clique em{' '}
                      <strong>Resolver</strong> para calcular.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Cards por linha empilhados (1 coluna, coluna direita
                é estreita). Sincronizados com equilibrium quando
                aplicado — engenheiro vê todas as linhas mudando ao
                mover o slider do watchcircle ou aplicar carga. */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  Linhas ({data.input.lines.length})
                </span>
                {equilibrium && (
                  <span className="text-[10px] text-primary">
                    valores do equilíbrio
                  </span>
                )}
              </div>
              <div className="space-y-3">
                {data.input.lines.map((line, idx) => {
                  const sourceLines =
                    equilibrium?.lines ?? latestResult?.lines
                  const lr = sourceLines?.[idx]
                  return (
                    <MooringLineMetricsCard
                      key={line.name}
                      lineSpec={
                        line as unknown as import('@/api/types').SystemLineSpec
                      }
                      result={lr ?? undefined}
                      paletteIndex={idx}
                    />
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* F5.5 — Equilíbrio de plataforma sob carga ambiental */}
        <Card className="mt-4 overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/20 px-4 py-2">
            <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              <Wind className="h-3 w-3" />
              Equilíbrio sob carga ambiental
            </span>
            {equilibrium && (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetEquilibrium}
                className="h-7 gap-1 text-[11px]"
              >
                <RotateCcw className="h-3 w-3" />
                Resetar
              </Button>
            )}
          </div>
          <CardContent className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_1fr]">
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Aplique uma carga horizontal sobre a plataforma (vento +
                corrente + onda média). O solver acha o offset (Δx, Δy)
                tal que a soma das forças restauradoras das linhas
                cancele a carga.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-0.5">
                  <Label className="text-[10px] font-medium text-muted-foreground">
                    F<sub>x</sub> (kN) — proa positivo
                  </Label>
                  <Input
                    type="number"
                    step="5"
                    value={envFxKn}
                    onChange={(e) => setEnvFxKn(Number(e.target.value) || 0)}
                    className="h-8 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-0.5">
                  <Label className="text-[10px] font-medium text-muted-foreground">
                    F<sub>y</sub> (kN) — bombordo positivo
                  </Label>
                  <Input
                    type="number"
                    step="5"
                    value={envFyKn}
                    onChange={(e) => setEnvFyKn(Number(e.target.value) || 0)}
                    className="h-8 font-mono"
                  />
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => equilibriumMutation.mutate()}
                disabled={equilibriumMutation.isPending}
                className="w-full"
              >
                {equilibriumMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Compass className="h-4 w-4" />
                )}
                Calcular equilíbrio
              </Button>
            </div>

            <div className="border-l border-border/40 pl-4">
              {equilibrium ? (
                <EquilibriumResultPanel result={equilibrium} />
              ) : (
                <p className="text-xs text-muted-foreground">
                  Nenhum equilíbrio calculado ainda. Defina F<sub>x</sub> e
                  F<sub>y</sub> e clique em <strong>Calcular</strong>. O
                  plan view mostrará a plataforma na posição deslocada.
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* F5.6 — Watchcircle (envelope de offsets sob carga rotacionada) */}
        <Card className="mt-4 overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/20 px-4 py-2">
            <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              <Target className="h-3 w-3" />
              Watchcircle — envelope de offset
            </span>
            {watchcircle && (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetWatchcircle}
                className="h-7 gap-1 text-[11px]"
              >
                <RotateCcw className="h-3 w-3" />
                Resetar
              </Button>
            )}
          </div>
          <CardContent className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[1fr_1fr]">
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Varre a direção da carga em 360° com magnitude fixa,
                gerando o envelope de offsets que a plataforma traça.
                Identifica direções de fragilidade do sistema.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-0.5">
                  <Label className="text-[10px] font-medium text-muted-foreground">
                    Magnitude (kN)
                  </Label>
                  <Input
                    type="number"
                    step="5"
                    min="0"
                    value={wcMagnitudeKn}
                    onChange={(e) =>
                      setWcMagnitudeKn(Number(e.target.value) || 0)
                    }
                    className="h-8 font-mono"
                  />
                </div>
                <div className="flex flex-col gap-0.5">
                  <Label className="text-[10px] font-medium text-muted-foreground">
                    Passos (n_steps)
                  </Label>
                  <Input
                    type="number"
                    step="4"
                    min="4"
                    max="180"
                    value={wcSteps}
                    onChange={(e) =>
                      setWcSteps(
                        Math.min(180, Math.max(4, Number(e.target.value) || 4)),
                      )
                    }
                    className="h-8 font-mono"
                  />
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => watchcircleMutation.mutate()}
                disabled={watchcircleMutation.isPending || wcMagnitudeKn <= 0}
                className="w-full"
              >
                {watchcircleMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Target className="h-4 w-4" />
                )}
                Calcular watchcircle
              </Button>
            </div>

            <div className="border-l border-border/40 pl-4">
              {watchcircle ? (
                <div className="space-y-2 font-mono text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-muted-foreground">Magnitude</span>
                    <span className="font-medium">
                      {(watchcircle.magnitude_n / 1000).toFixed(1)} kN
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-muted-foreground">Offset máx</span>
                    <span className="font-medium">
                      {watchcircle.max_offset_magnitude.toFixed(2)} m @{' '}
                      {watchcircle.max_offset_load_azimuth_deg.toFixed(0)}°
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-muted-foreground">
                      Máx. utilização
                    </span>
                    <span className="font-medium">
                      {fmtPercent(watchcircle.max_utilization, 1)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-muted-foreground">Falhas</span>
                    <span
                      className={`font-medium ${
                        watchcircle.n_failed > 0
                          ? 'text-warning'
                          : 'text-success'
                      }`}
                    >
                      {watchcircle.n_failed} / {watchcircle.n_steps}
                    </span>
                  </div>

                  {/* Animation controls */}
                  <div className="space-y-2 border-t border-border/40 pt-2">
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setWcPlaying((p) => !p)}
                        className="h-7 gap-1 px-2 text-[11px]"
                      >
                        {wcPlaying ? (
                          <Pause className="h-3 w-3" />
                        ) : (
                          <Play className="h-3 w-3" />
                        )}
                        {wcPlaying ? 'Pausar' : 'Animar'}
                      </Button>
                      <span className="text-[10px] text-muted-foreground">
                        Direção da carga:{' '}
                        <span className="font-mono text-foreground">
                          {watchcircle.points[wcAnimIdx]?.azimuth_deg.toFixed(
                            0,
                          )}
                          °
                        </span>
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={watchcircle.points.length - 1}
                      step={1}
                      value={wcAnimIdx}
                      onChange={(e) => {
                        const idx = Number(e.target.value)
                        setWcAnimIdx(idx)
                        const eq = watchcircle.points[idx]?.equilibrium
                        if (eq) setEquilibrium(eq)
                        setWcPlaying(false)
                      }}
                      className="w-full"
                    />
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Defina magnitude (kN) e passos (default 36 = passo de
                  10°) e clique em <strong>Calcular watchcircle</strong>.
                  O plan view mostrará o envelope (curva fechada
                  conectando os offsets de cada azimuth).
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Execution history */}
        {data.latest_executions && data.latest_executions.length > 0 && (
          <Card className="mt-4 overflow-hidden">
            <div className="border-b border-border/60 bg-muted/20 px-4 py-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Histórico ({data.latest_executions.length})
              </span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead className="text-right">Resultante</TableHead>
                  <TableHead className="text-right">Δ vs anterior</TableHead>
                  <TableHead className="text-right">Direção</TableHead>
                  <TableHead className="text-right">Convergiram</TableHead>
                  <TableHead>Pior alerta</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.latest_executions.map((ex, idx, arr) => {
                  const r = ex.result
                  // Lista vem mais-recente-primeiro; "anterior" é o
                  // próximo índice na lista (mais antigo).
                  const prev = arr[idx + 1]?.result
                  return (
                    <TableRow key={ex.id}>
                      <TableCell className="text-xs text-muted-foreground">
                        {format(
                          new Date(ex.executed_at),
                          "dd MMM yyyy 'às' HH:mm:ss",
                          { locale: ptBR },
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {(r.aggregate_force_magnitude / 1000).toFixed(1)} kN
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        <DeltaCell
                          current={r.aggregate_force_magnitude}
                          previous={prev?.aggregate_force_magnitude}
                          unit="kN"
                          divisor={1000}
                          digits={1}
                        />
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {r.aggregate_force_magnitude > 0
                          ? `${r.aggregate_force_azimuth_deg.toFixed(1)}°`
                          : '—'}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {r.n_converged}/{r.lines.length}
                      </TableCell>
                      <TableCell>
                        <AlertChip level={r.worst_alert_level} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </>
  )
}

function AggregateMetrics({ result }: { result: MooringSystemResult }) {
  return (
    <div className="space-y-2 font-mono text-xs">
      <Metric
        label="Resultante"
        value={`${(result.aggregate_force_magnitude / 1000).toFixed(2)} kN`}
        secondary={
          result.aggregate_force_magnitude > 0
            ? `≈ ${(result.aggregate_force_magnitude * 0.0001019716).toFixed(2)} tf`
            : undefined
        }
      />
      {result.aggregate_force_magnitude > 0 && (
        <Metric
          label="Direção"
          value={`${result.aggregate_force_azimuth_deg.toFixed(1)}°`}
        />
      )}
      <Metric
        label="Linhas convergidas"
        value={`${result.n_converged} / ${result.lines.length}`}
      />
      {result.n_invalid > 0 && (
        <Metric
          label="Inválidas"
          value={String(result.n_invalid)}
          tone="danger"
        />
      )}
      <Metric
        label="Máx. utilização"
        value={fmtPercent(result.max_utilization, 1)}
      />
      <Metric
        label="Pior alerta"
        value={result.worst_alert_level}
        tone={
          result.worst_alert_level === 'broken'
            ? 'danger'
            : result.worst_alert_level === 'red'
              ? 'danger'
              : result.worst_alert_level === 'yellow'
                ? 'warning'
                : 'success'
        }
      />
      {result.solver_version && (
        <p className="pt-2 text-[10px] text-muted-foreground">
          Solver v{result.solver_version}
        </p>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  secondary,
  tone,
}: {
  label: string
  value: string
  secondary?: string
  tone?: 'success' | 'warning' | 'danger'
}) {
  const toneCls =
    tone === 'danger'
      ? 'text-danger'
      : tone === 'warning'
        ? 'text-warning'
        : tone === 'success'
          ? 'text-success'
          : 'text-foreground'
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={`text-right font-medium ${toneCls}`}>
        {value}
        {secondary && (
          <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">
            {secondary}
          </span>
        )}
      </span>
    </div>
  )
}

function DeltaCell({
  current,
  previous,
  unit,
  divisor = 1,
  digits = 1,
}: {
  current: number
  previous: number | undefined
  unit: string
  divisor?: number
  digits?: number
}) {
  if (previous == null) {
    return <span className="text-muted-foreground">—</span>
  }
  const delta = (current - previous) / divisor
  // Threshold: variação menor que 0.05 unidade é "estável" (Minus).
  const epsilon = 0.05
  if (Math.abs(delta) < epsilon) {
    return (
      <span className="inline-flex items-center gap-0.5 text-muted-foreground">
        <Minus className="h-3 w-3" />
        0,0 {unit}
      </span>
    )
  }
  const sign = delta > 0 ? '+' : ''
  const Icon = delta > 0 ? ArrowUp : ArrowDown
  const color = delta > 0 ? 'text-warning' : 'text-success'
  return (
    <span className={`inline-flex items-center gap-0.5 ${color}`}>
      <Icon className="h-3 w-3" />
      {sign}
      {delta.toFixed(digits)} {unit}
    </span>
  )
}

function AlertChip({ level }: { level: string | null | undefined }) {
  const lv = level ?? 'ok'
  if (lv === 'broken') {
    return (
      <Badge variant="danger" className="gap-1 text-[10px]">
        broken
      </Badge>
    )
  }
  if (lv === 'red') {
    return (
      <Badge variant="danger" className="gap-1 text-[10px]">
        red
      </Badge>
    )
  }
  if (lv === 'yellow') {
    return (
      <Badge variant="warning" className="gap-1 text-[10px]">
        yellow
      </Badge>
    )
  }
  return (
    <Badge variant="success" className="gap-1 text-[10px]">
      <CheckCircle2 className="h-3 w-3" />
      ok
    </Badge>
  )
}

// Suppress unused import warning since fmtNumber is referenced in helpers.
void fmtNumber

/**
 * F5.5 — Painel compacto de resultado do equilíbrio: offset, resíduo,
 * iterações + mini-tabela com tração e Δ% por linha vs baseline.
 */
function EquilibriumResultPanel({
  result,
}: {
  result: PlatformEquilibriumResult
}) {
  return (
    <div className="space-y-2 font-mono text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Offset</span>
        <span className="font-medium">
          {result.offset_magnitude.toFixed(2)} m @{' '}
          {result.offset_magnitude > 0.01
            ? `${result.offset_azimuth_deg.toFixed(1)}°`
            : '—'}
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Δx, Δy</span>
        <span className="font-medium">
          {result.offset_xy[0].toFixed(2)},{' '}
          {result.offset_xy[1].toFixed(2)} m
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Resíduo</span>
        <span
          className={`font-medium ${
            result.converged ? 'text-success' : 'text-warning'
          }`}
        >
          {result.residual_magnitude.toFixed(1)} N
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Iterações</span>
        <span className="font-medium">{result.iterations}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Convergidas</span>
        <span className="font-medium">
          {result.n_converged} / {result.lines.length}
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground">Máx. utilização</span>
        <span className="font-medium">
          {fmtPercent(result.max_utilization, 1)}
        </span>
      </div>
      {result.message && (
        <p className="border-t border-border/40 pt-2 text-[10px] text-muted-foreground">
          {result.message}
        </p>
      )}
    </div>
  )
}
