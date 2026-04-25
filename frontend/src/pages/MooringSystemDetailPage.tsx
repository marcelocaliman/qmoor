import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  AlertCircle,
  CheckCircle2,
  Edit3,
  Loader2,
  Zap,
} from 'lucide-react'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { getMooringSystem, solveMooringSystem } from '@/api/endpoints'
import type { MooringSystemResult } from '@/api/types'
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
import { fmtAngleDeg, fmtMeters, fmtNumber, fmtPercent } from '@/lib/utils'

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
          {/* Plan view */}
          <Card className="overflow-hidden">
            <CardContent className="aspect-square p-3">
              <MooringSystemPlanView
                result={latestResult}
                platformRadius={data.input.platform_radius}
                previewLines={previewLines}
              />
            </CardContent>
          </Card>

          {/* Aggregate metrics */}
          <Card>
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
        </div>

        {/* Lines table */}
        <Card className="mt-4 overflow-hidden">
          <div className="border-b border-border/60 bg-muted/20 px-4 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Linhas ({data.input.lines.length})
            </span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead className="text-right">Azimuth</TableHead>
                <TableHead className="text-right">Raio</TableHead>
                <TableHead className="text-right">T_fl / X (input)</TableHead>
                <TableHead className="text-right">H</TableHead>
                <TableHead className="text-right">Utilização</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.input.lines.map((line, idx) => {
                const lr = latestResult?.lines[idx]
                const sr = lr?.solver_result
                const inputLabel =
                  line.boundary.mode === 'Tension'
                    ? `${(line.boundary.input_value / 1000).toFixed(1)} kN`
                    : fmtMeters(line.boundary.input_value, 1)
                return (
                  <TableRow key={line.name}>
                    <TableCell className="font-medium">{line.name}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {fmtAngleDeg((line.fairlead_azimuth_deg * Math.PI) / 180, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {fmtMeters(line.fairlead_radius, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {inputLabel}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {sr ? `${(sr.H / 1000).toFixed(1)} kN` : '—'}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {sr ? fmtPercent(sr.utilization, 1) : '—'}
                    </TableCell>
                    <TableCell>
                      {sr ? (
                        <StatusChip
                          status={sr.status}
                          alertLevel={sr.alert_level}
                        />
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          —
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
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
                  <TableHead className="text-right">Direção</TableHead>
                  <TableHead className="text-right">Convergiram</TableHead>
                  <TableHead>Pior alerta</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.latest_executions.map((ex) => {
                  const r = ex.result
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

function StatusChip({
  status,
  alertLevel,
}: {
  status: string
  alertLevel: string | null | undefined
}) {
  if (status !== 'converged') {
    return (
      <Badge variant="danger" className="gap-1 text-[10px]">
        <AlertCircle className="h-3 w-3" />
        {status}
      </Badge>
    )
  }
  return <AlertChip level={alertLevel ?? 'ok'} />
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
