import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  AlertCircle,
  Code2,
  Copy,
  Download,
  FileText,
  Gauge,
  History,
  LineChart as LineChartIcon,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Play,
  RefreshCw,
  Table as TableIcon,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import {
  deleteCase,
  exportJsonUrl,
  exportMoorUrl,
  exportPdfUrl,
  getCase,
  solveCase,
} from '@/api/endpoints'
import type { ExecutionOutput, SolverResult } from '@/api/types'
import { CatenaryPlot } from '@/components/common/CatenaryPlot'
import { EmptyState } from '@/components/common/EmptyState'
import { SensitivityPanel } from '@/components/common/SensitivityPanel'
import {
  AlertBadge,
  CategoryBadge,
  ModeBadge,
  StatusBadge,
} from '@/components/common/StatusBadge'
import { UtilizationGauge } from '@/components/common/UtilizationGauge'
import { Topbar } from '@/components/layout/Topbar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  fmtAngleDeg,
  fmtMeters,
  fmtNumber,
  fmtPercent,
  resolveSeabedDepths,
} from '@/lib/utils'
import { fmtForce, fmtForcePair, fmtForcePerM } from '@/lib/units'
import { useUnitsStore } from '@/store/units'

export function CaseDetailPage() {
  const { id } = useParams()
  const caseId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const system = useUnitsStore((s) => s.system)

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [jsonOpen, setJsonOpen] = useState(false)
  const [selectedExecId, setSelectedExecId] = useState<number | null>(null)
  // Resultado live do painel de sensibilidade. Quando setado, sobrescreve
  // visualmente o resultado salvo nos cards/gráfico/tabelas. As entradas
  // de Histórico continuam refletindo as runs persistidas.
  const [liveResult, setLiveResult] = useState<SolverResult | null>(null)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['case', String(caseId)],
    queryFn: () => getCase(caseId),
    enabled: !Number.isNaN(caseId),
  })

  const solveMutation = useMutation({
    mutationFn: () => solveCase(caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['case', String(caseId)] })
      toast.success('Caso recalculado com sucesso.')
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        toast.error('Falha no solver', { description: err.message })
      } else {
        toast.error('Erro inesperado ao calcular')
      }
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteCase(caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      toast.success('Caso excluído.')
      navigate('/cases')
    },
    onError: (err: unknown) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao excluir', { description: msg })
    },
  })

  if (isLoading) {
    return (
      <>
        <Topbar />
        <div className="flex-1 space-y-4 p-6">
          <Skeleton className="h-16 w-full" />
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          <Skeleton className="h-96 w-full" />
        </div>
      </>
    )
  }

  if (isError || !data) {
    return (
      <>
        <Topbar />
        <div className="flex-1 p-6">
          <EmptyState
            icon={AlertCircle}
            title="Caso não encontrado"
            description={
              error instanceof ApiError
                ? error.message
                : 'Verifique o id ou volte para a listagem.'
            }
            action={
              <Button asChild>
                <Link to="/cases">Voltar para Casos</Link>
              </Button>
            }
          />
        </div>
      </>
    )
  }

  const caseInput = data.input
  const executions = data.latest_executions ?? []
  const latest = executions[0]
  const selectedExec =
    selectedExecId != null
      ? executions.find((e) => e.id === selectedExecId)
      : null
  const execToShow = selectedExec ?? latest
  const savedResult = execToShow?.result
  // displayResult é o que efetivamente alimenta os cards/gráfico/tabelas.
  // Quando há preview ao vivo (sensibilidade), sobrescreve o salvo.
  const result = liveResult ?? savedResult

  const breadcrumbs = [
    { label: 'Casos', to: '/cases' },
    { label: data.name },
  ]

  const actions = (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => solveMutation.mutate()}
        disabled={solveMutation.isPending}
      >
        {solveMutation.isPending ? (
          <RefreshCw className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {solveMutation.isPending ? 'Calculando…' : 'Recalcular'}
      </Button>
      <Button variant="outline" size="sm" asChild>
        <Link to={`/cases/${caseId}/edit`}>
          <Pencil className="h-4 w-4" />
          Editar
        </Link>
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setJsonOpen(true)}
        title="Ver JSON do input + última execução"
      >
        <Code2 className="h-4 w-4" />
        JSON
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" aria-label="Mais ações">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Exportar</DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <a href={exportMoorUrl(caseId, 'metric')} download>
              <Download className="h-4 w-4" />
              .moor (métrico)
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href={exportMoorUrl(caseId, 'imperial')} download>
              <Download className="h-4 w-4" />
              .moor (imperial)
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href={exportJsonUrl(caseId)} download>
              <Download className="h-4 w-4" />
              JSON
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem
            asChild={!!latest}
            disabled={!latest}
            onSelect={(e) => {
              if (!latest) {
                e.preventDefault()
                toast.warning('Caso sem execução', {
                  description:
                    'Calcule o caso pelo menos uma vez antes de exportar o PDF.',
                })
              }
            }}
          >
            {latest ? (
              <a href={exportPdfUrl(caseId)} target="_blank" rel="noreferrer">
                <FileText className="h-4 w-4" />
                PDF (relatório)
              </a>
            ) : (
              <span className="flex items-center gap-2 opacity-60">
                <FileText className="h-4 w-4" />
                PDF (calcule primeiro)
              </span>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-danger focus:text-danger"
            onSelect={() => setDeleteOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            Excluir caso
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  )

  return (
    <>
      <Topbar breadcrumbs={breadcrumbs} actions={actions} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* ─────────── Cabeçalho do caso ─────────── */}
        <header className="shrink-0 border-b border-border bg-background/60 px-6 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-semibold tracking-tight">
                {data.name}
              </h1>
              {data.description && (
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                  {data.description}
                </p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <CategoryBadge category={caseInput.segments[0]?.category} />
                {caseInput.segments[0]?.line_type && (
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {caseInput.segments[0].line_type}
                  </Badge>
                )}
                <ModeBadge mode={caseInput.boundary.mode} />
                {result && <StatusBadge status={result.status} />}
                {result && <AlertBadge level={result.alert_level} />}
              </div>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <p>
                Criado em{' '}
                {format(new Date(data.created_at), "dd 'de' MMM, yyyy", {
                  locale: ptBR,
                })}
              </p>
              <p>
                Atualizado{' '}
                {format(new Date(data.updated_at), "dd 'de' MMM 'às' HH:mm", {
                  locale: ptBR,
                })}
              </p>
              {executions.length > 0 && (
                <p className="mt-0.5">
                  {executions.length}{' '}
                  {executions.length === 1 ? 'execução' : 'execuções'} ·
                  {' '}última: Run #{latest!.id}
                </p>
              )}
            </div>
          </div>
        </header>

        {/* Sem execução */}
        {!result ? (
          <div className="flex-1 overflow-auto p-6">
            <EmptyState
              icon={Play}
              title="Caso ainda não foi calculado"
              description="Execute o solver para ver resultados, perfil 2D e classificação."
              action={
                <Button
                  onClick={() => solveMutation.mutate()}
                  disabled={solveMutation.isPending}
                >
                  <Play className="h-4 w-4" />
                  Calcular agora
                </Button>
              }
            />
          </div>
        ) : (
          <Tabs
            defaultValue="overview"
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="shrink-0 border-b border-border/60 px-6 pt-3">
              <TabsList className="w-fit">
                <TabsTrigger value="overview" className="gap-1.5">
                  <LineChartIcon className="h-3.5 w-3.5" />
                  Visão geral
                </TabsTrigger>
                <TabsTrigger value="results" className="gap-1.5">
                  <ListChecks className="h-3.5 w-3.5" />
                  Resultados detalhados
                </TabsTrigger>
                <TabsTrigger value="points" className="gap-1.5">
                  <TableIcon className="h-3.5 w-3.5" />
                  Pontos discretizados
                </TabsTrigger>
                <TabsTrigger value="history" className="gap-1.5">
                  <History className="h-3.5 w-3.5" />
                  Histórico
                  {executions.length > 1 && (
                    <Badge
                      variant="secondary"
                      className="ml-1 h-4 px-1 text-[10px]"
                    >
                      {executions.length}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>
            </div>

            {/* Único container de scroll — envelopa todas as TabsContent.
                Cada TabsContent tem display:block (sem flex), com altura
                natural; o overflow vertical fica neste wrapper. */}
            <div className="min-h-0 flex-1 overflow-auto custom-scroll">
              {/* Aba 1: Visão geral */}
              <TabsContent
                value="overview"
                className="m-0 px-6 pb-6 pt-4 data-[state=inactive]:hidden"
              >
                {result.status !== 'converged' && (
                  <AlertBanner result={result} />
                )}
                {/* Banner: execução antiga com slope ≠ 0 → coords salvas
                    sem o caminho de touchdown em rampa. Sugere recalcular. */}
                {isStaleSolverForSlope(result, caseInput.seabed?.slope_rad ?? 0) && (
                  <StaleSolverBanner
                    onRecalculate={() => solveMutation.mutate()}
                    pending={solveMutation.isPending}
                  />
                )}
                <Card className="mb-4">
                  <CardContent className="h-[480px] p-2">
                    <CatenaryPlot
                      result={result}
                      attachments={caseInput.attachments ?? []}
                      seabedSlopeRad={caseInput.seabed?.slope_rad ?? 0}
                      segments={caseInput.segments ?? []}
                    />
                  </CardContent>
                </Card>
                <div className="mb-4">
                  <SensitivityPanel
                    caseId={caseId}
                    baseInput={caseInput}
                    onPreview={setLiveResult}
                    onApplied={() => {
                      queryClient.invalidateQueries({
                        queryKey: ['case', String(caseId)],
                      })
                    }}
                  />
                </div>
                <OverviewCards
                  result={result}
                  input={caseInput}
                  executedAt={
                    liveResult ? undefined : execToShow?.executed_at
                  }
                  system={system}
                />
              </TabsContent>

              {/* Aba 2: Resultados detalhados */}
              <TabsContent
                value="results"
                className="m-0 px-6 pb-6 pt-4 data-[state=inactive]:hidden"
              >
                <ResultsTables
                  result={result}
                  input={caseInput}
                  system={system}
                />
              </TabsContent>

              {/* Aba 3: Pontos discretizados */}
              <TabsContent
                value="points"
                className="m-0 px-6 pb-6 pt-4 data-[state=inactive]:hidden"
              >
                <PointsTable result={result} system={system} />
              </TabsContent>

              {/* Aba 4: Histórico */}
              <TabsContent
                value="history"
                className="m-0 px-6 pb-6 pt-4 data-[state=inactive]:hidden"
              >
                <HistoryGrid
                  executions={executions}
                  selectedId={selectedExecId ?? latest?.id ?? 0}
                  onSelect={setSelectedExecId}
                  system={system}
                />
              </TabsContent>
            </div>
          </Tabs>
        )}
      </div>

      {/* JSON modal */}
      <JsonDialog
        open={jsonOpen}
        onOpenChange={setJsonOpen}
        input={caseInput}
        latestExecution={latest}
      />

      {/* Confirmação de exclusão */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir este caso?</DialogTitle>
            <DialogDescription>
              Todas as execuções serão removidas em cascata. Ação irreversível.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
              Excluir permanentemente
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * Aba 1 — Visão geral
 * ═══════════════════════════════════════════════════════════════════════ */

function OverviewCards({
  result,
  input,
  executedAt,
  system,
}: {
  result: SolverResult
  input: import('@/api/types').CaseInput
  executedAt?: string
  system: 'metric' | 'si'
}) {
  const segment = input.segments[0]!
  const tFlPair = fmtForcePair(result.fairlead_tension, system)
  const hasTouchdown =
    result.dist_to_first_td != null && result.dist_to_first_td > 0
  const drop = (result.water_depth ?? 0) - (result.startpoint_depth ?? 0)

  // Margem para próximo nível (utilization atual vs limites do perfil ativo).
  // Perfil é guardado no input, mas os limites efetivos vêm dos badges. Usamos
  // os defaults conservadores aqui — a UI do critério é informativa.
  const utilPct = result.utilization

  // Fallback de batimetria: execuções salvas antes da F5.3.z não têm
  // depth_at_*; recomputamos a partir de h e slope_rad.
  const seabedDepths = resolveSeabedDepths(
    result,
    input.boundary.h,
    input.seabed?.slope_rad ?? 0,
  )

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {/* Tração no fairlead — destaque */}
      <Card className="xl:col-span-1">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Tração no fairlead
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-baseline gap-2 font-mono tabular-nums leading-none">
            <span className="text-3xl font-semibold tracking-tight">
              {tFlPair.primary}
            </span>
            <span className="text-sm text-muted-foreground">
              ≈ {tFlPair.secondary}
            </span>
          </div>
          <UtilizationGauge
            value={utilPct}
            alertLevel={result.alert_level}
            className="mt-3"
          />
          <div className="flex justify-between font-mono text-[11px] tabular-nums text-muted-foreground">
            <span>T_fl / MBL = {fmtPercent(utilPct, 2)}</span>
            <span>MBL = {fmtForce(segment.MBL, system)}</span>
          </div>
        </CardContent>
      </Card>

      {/* Geometria principal */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Geometria
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 font-mono text-[12px] tabular-nums">
          <Row label="X total (fairlead → âncora)" value={fmtMeters(result.total_horz_distance, 2)} />
          <Row label="Prof. seabed @ âncora" value={fmtMeters(seabedDepths.atAnchor, 1)} />
          <Row label="Prof. seabed @ fairlead" value={fmtMeters(seabedDepths.atFairlead, 1)} />
          <Row label="Prof. do fairlead (vessel)" value={fmtMeters(result.startpoint_depth ?? 0, 1)} />
          <Row label="Drop vertical" value={fmtMeters(drop, 1)} />
          {hasTouchdown && (
            <Row
              label="Touchdown (do fairlead)"
              value={fmtMeters(
                result.total_horz_distance - result.dist_to_first_td!,
                2,
              )}
            />
          )}
        </CardContent>
      </Card>

      {/* Comprimentos */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Comprimentos
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 font-mono text-[12px] tabular-nums">
          <Row label="L total (unstretched)" value={fmtMeters(segment.length, 2)} />
          <Row label="L esticado" value={fmtMeters(result.stretched_length, 2)} />
          <Row label="L suspenso" value={fmtMeters(result.total_suspended_length, 2)} />
          <Row label="L apoiado" value={fmtMeters(result.total_grounded_length, 2)} />
          <Row label="ΔL" value={fmtMeters(result.elongation, 3)} />
          <Row
            label="Strain"
            value={fmtPercent(
              segment.length > 0 ? result.elongation / segment.length : 0,
              3,
            )}
          />
        </CardContent>
      </Card>

      {/* Forças */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Forças
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 font-mono text-[12px] tabular-nums">
          <Row label="H (horizontal)" value={fmtForce(result.H, system)} />
          <Row label="T_fairlead" value={fmtForce(result.fairlead_tension, system)} />
          <Row label="T_anchor" value={fmtForce(result.anchor_tension, system)} />
          <Row
            label="V_fairlead"
            value={fmtForce(
              vertical(result.fairlead_tension, result.H),
              system,
            )}
          />
          <Row
            label="V_anchor"
            value={fmtForce(
              vertical(result.anchor_tension, result.H),
              system,
            )}
          />
          <Row label="ΔT (atrito)" value={fmtForce(result.fairlead_tension - result.anchor_tension, system)} />
        </CardContent>
      </Card>

      {/* Ângulos */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Ângulos
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 font-mono text-[12px] tabular-nums">
          <Row
            label="Fairlead (vs horizontal)"
            value={fmtAngleDeg(result.angle_wrt_horz_fairlead, 2)}
          />
          <Row
            label="Fairlead (vs vertical)"
            value={fmtAngleDeg(result.angle_wrt_vert_fairlead, 2)}
          />
          <Row
            label="Âncora (vs horizontal)"
            value={fmtAngleDeg(result.angle_wrt_horz_anchor, 2)}
          />
          <Row
            label="Âncora (vs vertical)"
            value={fmtAngleDeg(result.angle_wrt_vert_anchor, 2)}
          />
        </CardContent>
      </Card>

      {/* Convergência */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
            <Gauge className="h-3 w-3" />
            Convergência
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={result.status} />
            <AlertBadge level={result.alert_level} />
          </div>
          <div className="space-y-1 font-mono text-[12px] tabular-nums text-muted-foreground">
            <Row
              label="Iterações"
              value={String(result.iterations_used)}
            />
            {executedAt && (
              <Row
                label="Calculado em"
                value={format(new Date(executedAt), 'dd MMM, HH:mm', {
                  locale: ptBR,
                })}
              />
            )}
          </div>
          {result.message && (
            <p
              className="rounded-md border border-border/60 bg-muted/20 p-2 font-mono text-[10.5px] leading-relaxed text-muted-foreground"
              title={result.message}
            >
              {result.message}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function AlertBanner({ result }: { result: SolverResult }) {
  const isError =
    result.status === 'invalid_case' || result.status === 'numerical_error'
  return (
    <div
      className={`mb-4 flex items-start gap-3 rounded-lg border p-4 text-sm ${
        isError
          ? 'border-danger/40 bg-danger/10'
          : 'border-warning/40 bg-warning/10'
      }`}
    >
      <AlertCircle
        className={`mt-0.5 h-4 w-4 ${isError ? 'text-danger' : 'text-warning'}`}
      />
      <div className="min-w-0">
        <p className="font-medium">
          Status do solver: {result.status.replace(/_/g, ' ')}
        </p>
        <p className="text-muted-foreground">{result.message}</p>
      </div>
    </div>
  )
}

/**
 * Detecta execuções calculadas em versão do solver anterior à F5.3.x
 * (sem suporte a touchdown em rampa). Quando existe slope no caso atual
 * mas a run salva é dessa época, as coords da curva ficam horizontais
 * e o gráfico fica visualmente errado.
 */
function isStaleSolverForSlope(
  result: SolverResult,
  slopeRad: number,
): boolean {
  if (Math.abs(slopeRad) < 1e-6) return false
  const sv = result.solver_version || ''
  if (!sv) return true
  const parts = sv.split('.').map((p) => parseInt(p, 10))
  // Antes de 1.4.1 não havia touchdown em rampa
  if (parts[0]! < 1) return true
  if (parts[0] === 1 && (parts[1] ?? 0) < 4) return true
  if (parts[0] === 1 && parts[1] === 4 && (parts[2] ?? 0) < 1) return true
  return false
}

function StaleSolverBanner({
  onRecalculate,
  pending,
}: {
  onRecalculate: () => void
  pending: boolean
}) {
  return (
    <div className="mb-4 flex items-start gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 text-warning" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">Execução em versão antiga do solver</p>
        <p className="text-muted-foreground">
          Esta run foi calculada antes da v1.4.1 (sem suporte a touchdown
          em seabed inclinado). A curva no gráfico foi salva como
          horizontal — geometria atualizada exige recalcular.
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={onRecalculate}
        disabled={pending}
      >
        {pending ? (
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
        Recalcular agora
      </Button>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * Aba 2 — Resultados detalhados (tabelas categorizadas)
 * ═══════════════════════════════════════════════════════════════════════ */

function ResultsTables({
  result,
  input,
  system,
}: {
  result: SolverResult
  input: import('@/api/types').CaseInput
  system: 'metric' | 'si'
}) {
  const segment = input.segments[0]!
  const drop = (result.water_depth ?? 0) - (result.startpoint_depth ?? 0)
  const vFairlead = vertical(result.fairlead_tension, result.H)
  const vAnchor = vertical(result.anchor_tension, result.H)
  const tMean = (result.fairlead_tension + result.anchor_tension) / 2
  const strain =
    segment.length > 0 ? result.elongation / segment.length : 0
  const friction = result.fairlead_tension - result.anchor_tension
  const seabedDepths = resolveSeabedDepths(
    result, input.boundary.h, input.seabed?.slope_rad ?? 0,
  )

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Forças */}
      <SectionTable title="Forças" subtitle="Tensões nos extremos e diferenças">
        <KeyValueTable
          rows={[
            ['T_fairlead (total)', fmtForce(result.fairlead_tension, system)],
            ['T_anchor (total)', fmtForce(result.anchor_tension, system)],
            ['H (horizontal, constante)', fmtForce(result.H, system)],
            ['V_fairlead (vertical)', fmtForce(vFairlead, system)],
            ['V_anchor (vertical)', fmtForce(vAnchor, system)],
            ['ΔT fairlead − âncora (atrito)', fmtForce(friction, system)],
            ['T_média (correção elástica)', fmtForce(tMean, system)],
          ]}
        />
      </SectionTable>

      {/* Geometria */}
      <SectionTable
        title="Geometria"
        subtitle="Posições, lâmina d'água e comprimentos"
      >
        <KeyValueTable
          rows={[
            ['X total (fairlead → âncora)', fmtMeters(result.total_horz_distance, 3)],
            ['Prof. seabed @ âncora', fmtMeters(seabedDepths.atAnchor, 2)],
            ['Prof. seabed @ fairlead', fmtMeters(seabedDepths.atFairlead, 2)],
            ['Profundidade do fairlead (vessel)', fmtMeters(result.startpoint_depth ?? 0, 2)],
            ['Drop vertical efetivo', fmtMeters(drop, 2)],
            ['L total (unstretched)', fmtMeters(segment.length, 3)],
            ['L esticado', fmtMeters(result.stretched_length, 3)],
            ['L suspenso', fmtMeters(result.total_suspended_length, 3)],
            ['L apoiado no seabed', fmtMeters(result.total_grounded_length, 3)],
            ['Elongação ΔL', fmtMeters(result.elongation, 4)],
            ['Strain (ΔL / L)', fmtPercent(strain, 4)],
            result.dist_to_first_td != null && result.dist_to_first_td > 0
              ? [
                  'Distância ao touchdown (a partir do fairlead)',
                  fmtMeters(
                    result.total_horz_distance - result.dist_to_first_td,
                    3,
                  ),
                ]
              : ['Touchdown', '— (sem trecho apoiado)'],
          ]}
        />
      </SectionTable>

      {/* Ângulos */}
      <SectionTable
        title="Ângulos"
        subtitle="Inclinações nos pontos de fixação"
      >
        <KeyValueTable
          rows={[
            ['Fairlead — vs horizontal', fmtAngleDeg(result.angle_wrt_horz_fairlead, 3)],
            ['Fairlead — vs vertical', fmtAngleDeg(result.angle_wrt_vert_fairlead, 3)],
            ['Âncora — vs horizontal (departure)', fmtAngleDeg(result.angle_wrt_horz_anchor, 3)],
            ['Âncora — vs vertical', fmtAngleDeg(result.angle_wrt_vert_anchor, 3)],
          ]}
        />
      </SectionTable>

      {/* Critério de utilização */}
      <SectionTable
        title="Critério de utilização"
        subtitle={`Perfil ativo: ${input.criteria_profile}`}
      >
        <KeyValueTable
          rows={[
            ['T_fl / MBL atual', fmtPercent(result.utilization, 3)],
            ['Alert level', result.alert_level.toUpperCase()],
            ['MBL', fmtForce(segment.MBL, system)],
            [
              'Margem até atingir 100% MBL',
              fmtForce(
                Math.max(segment.MBL - result.fairlead_tension, 0),
                system,
              ),
            ],
            input.user_defined_limits
              ? [
                  'Limites custom (yellow / red / broken)',
                  `${fmtNumber(input.user_defined_limits.yellow_ratio, 2)} / ${fmtNumber(input.user_defined_limits.red_ratio, 2)} / ${fmtNumber(input.user_defined_limits.broken_ratio, 2)}`,
                ]
              : ['Limites do perfil', 'padrão'],
          ]}
        />
      </SectionTable>

      {/* Material / Segmento */}
      <SectionTable
        title="Material e segmento"
        subtitle="Propriedades físicas do cabo (sempre em SI no estado interno)"
      >
        <KeyValueTable
          rows={[
            ['Tipo de linha', segment.line_type ?? '—'],
            ['Categoria', segment.category ?? '—'],
            segment.diameter
              ? ['Diâmetro nominal', `${fmtNumber(segment.diameter * 1000, 1)} mm`]
              : ['Diâmetro', '—'],
            ['Peso submerso', fmtForcePerM(segment.w, system)],
            segment.dry_weight
              ? ['Peso seco', fmtForcePerM(segment.dry_weight, system)]
              : ['Peso seco', '—'],
            ['EA (rigidez axial)', fmtForce(segment.EA, system)],
            ['MBL', fmtForce(segment.MBL, system)],
            segment.modulus
              ? ['Módulo aparente', `${fmtNumber(segment.modulus / 1e9, 2)} GPa`]
              : ['Módulo', '—'],
            ['Atrito do seabed (μ)', fmtNumber(input.seabed?.mu ?? 0, 2)],
          ]}
        />
      </SectionTable>

      {/* Diagnóstico */}
      <SectionTable title="Diagnóstico do solver" subtitle="Convergência e mensagens">
        <KeyValueTable
          rows={[
            ['Status', result.status.replace(/_/g, ' ')],
            ['Iterações', String(result.iterations_used)],
            ['Modo', input.boundary.mode],
            [
              'Input do modo',
              input.boundary.mode === 'Tension'
                ? `T_fl = ${fmtForce(input.boundary.input_value, system)}`
                : `X = ${fmtMeters(input.boundary.input_value, 2)}`,
            ],
            ['Mensagem', result.message || '—'],
          ]}
        />
      </SectionTable>
    </div>
  )
}

function SectionTable({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        {subtitle && (
          <p className="text-[11px] text-muted-foreground">{subtitle}</p>
        )}
      </CardHeader>
      <CardContent className="px-2 pb-3">{children}</CardContent>
    </Card>
  )
}

function KeyValueTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <Table>
      <TableBody>
        {rows.map(([k, v]) => (
          <TableRow key={k} className="border-border/40">
            <TableCell className="py-1.5 text-[12px] text-muted-foreground">
              {k}
            </TableCell>
            <TableCell className="py-1.5 text-right font-mono text-[12px] font-medium tabular-nums">
              {v}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * Aba 3 — Pontos discretizados (tabela completa)
 * ═══════════════════════════════════════════════════════════════════════ */

function PointsTable({
  result,
  system,
}: {
  result: SolverResult
  system: 'metric' | 'si'
}) {
  // Constrói linhas no frame surface-relative + arc length acumulado +
  // ângulo via atan2(T_y, T_x) + estado (suspended/grounded).
  const rows = useMemo(() => buildPointRows(result), [result])
  const xtotal = result.total_horz_distance ?? 0
  const waterDepth = result.water_depth ?? 0
  const td = result.dist_to_first_td ?? 0

  // Paginação simples: mostra primeiros 200 pontos, com botão para expandir.
  // 5000 linhas em uma tabela HTML escala mal; CSV cobre o caso completo.
  const [showAll, setShowAll] = useState(false)
  const display = showAll ? rows : rows.slice(0, 200)

  function downloadCsv() {
    const header = [
      '#',
      's_unstretched_m',
      'x_plot_m',
      'y_plot_m',
      'profundidade_m',
      'T_total_N',
      'T_horz_N',
      'T_vert_N',
      'angulo_horz_deg',
      'estado',
    ]
    const lines = [header.join(',')]
    for (const r of rows) {
      lines.push(
        [
          r.idx,
          r.s.toFixed(4),
          r.xPlot.toFixed(4),
          r.yPlot.toFixed(4),
          r.depth.toFixed(4),
          r.T.toFixed(2),
          r.Tx.toFixed(2),
          r.Ty.toFixed(2),
          (r.angleRad * 180) / Math.PI,
          r.state,
        ].join(','),
      )
    }
    const blob = new Blob([lines.join('\n')], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pontos-${rows.length}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
        <div className="min-w-0">
          <CardTitle className="text-sm font-semibold">
            Pontos discretizados
          </CardTitle>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {rows.length.toLocaleString('pt-BR')} pontos · frame surface-relative
            (fairlead em x=0, superfície em y=0). X total = {fmtMeters(xtotal, 2)},
            lâmina = {fmtMeters(waterDepth, 1)}, touchdown a {fmtMeters(td, 1)}{' '}
            da âncora.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={downloadCsv}>
          <Download className="h-3.5 w-3.5" />
          CSV completo ({rows.length.toLocaleString('pt-BR')})
        </Button>
      </CardHeader>
      <CardContent className="px-0">
        <div className="overflow-auto custom-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead className="text-right">s (m)</TableHead>
                <TableHead className="text-right">x (m)</TableHead>
                <TableHead className="text-right">y (m)</TableHead>
                <TableHead className="text-right">prof. (m)</TableHead>
                <TableHead className="text-right">|T|</TableHead>
                <TableHead className="text-right">T_h</TableHead>
                <TableHead className="text-right">T_v</TableHead>
                <TableHead className="text-right">θ (°)</TableHead>
                <TableHead>estado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {display.map((r) => (
                <TableRow key={r.idx} className="border-border/40">
                  <TableCell className="font-mono text-[11px] text-muted-foreground">
                    {r.idx}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {r.s.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {r.xPlot.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {r.yPlot.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {r.depth.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {fmtForceCompact(r.T, system)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {fmtForceCompact(r.Tx, system)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {fmtForceCompact(r.Ty, system)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-[11px] tabular-nums">
                    {((r.angleRad * 180) / Math.PI).toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={r.state === 'suspended' ? 'secondary' : 'outline'}
                      className="text-[10px]"
                    >
                      {r.state === 'suspended' ? 'suspenso' : 'apoiado'}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {!showAll && rows.length > 200 && (
          <div className="border-t border-border/40 bg-muted/10 px-4 py-2 text-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAll(true)}
            >
              Mostrar todos os {rows.length.toLocaleString('pt-BR')} pontos
            </Button>
            <p className="mt-1 text-[10px] text-muted-foreground">
              (primeiros 200 exibidos para performance — CSV traz a tabela
              completa)
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * Aba 4 — Histórico (versionamento)
 * ═══════════════════════════════════════════════════════════════════════ */

function HistoryGrid({
  executions,
  selectedId,
  onSelect,
  system,
}: {
  executions: ExecutionOutput[]
  selectedId: number
  onSelect: (id: number) => void
  system: 'metric' | 'si'
}) {
  if (executions.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="Sem execuções registradas"
        description="Cada Recalcular cria uma nova entrada nesta lista."
      />
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">
          Últimas {executions.length} execuções
        </h3>
        <p className="text-[11px] text-muted-foreground">
          O backend mantém as 10 últimas. Clique em uma run para ver o gráfico
          e os números nas outras abas.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {executions.map((e, i) => {
          const prev = executions[i + 1]?.result
          const cur = e.result
          const dT = prev
            ? cur.fairlead_tension - prev.fairlead_tension
            : 0
          const dX = prev
            ? cur.total_horz_distance - prev.total_horz_distance
            : 0
          const dUtil = prev ? cur.utilization - prev.utilization : 0
          const isSelected = e.id === selectedId
          const isLatest = i === 0
          return (
            <button
              key={e.id}
              type="button"
              onClick={() => onSelect(e.id)}
              className={`flex flex-col gap-2 rounded-lg border p-3 text-left transition-colors ${
                isSelected
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-border hover:border-border hover:bg-muted/40'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold">
                    Run #{e.id}
                  </span>
                  {isLatest && (
                    <Badge variant="success" className="h-5 text-[10px]">
                      atual
                    </Badge>
                  )}
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {format(new Date(e.executed_at), "dd MMM, HH:mm:ss", {
                    locale: ptBR,
                  })}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <StatusBadge status={cur.status} />
                <AlertBadge level={cur.alert_level} />
              </div>
              <div className="space-y-0.5 font-mono text-[11px] tabular-nums">
                <Row
                  label="T_fairlead"
                  value={fmtForce(cur.fairlead_tension, system)}
                  delta={prev ? dT : null}
                  deltaUnit="force"
                  system={system}
                />
                <Row
                  label="X total"
                  value={fmtMeters(cur.total_horz_distance, 1)}
                  delta={prev ? dX : null}
                  deltaUnit="m"
                />
                <Row
                  label="Utilização"
                  value={fmtPercent(cur.utilization, 2)}
                  delta={prev ? dUtil : null}
                  deltaUnit="pct"
                />
                <Row label="Iterações" value={String(cur.iterations_used)} />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * JSON Dialog
 * ═══════════════════════════════════════════════════════════════════════ */

function JsonDialog({
  open,
  onOpenChange,
  input,
  latestExecution,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  input: import('@/api/types').CaseInput
  latestExecution?: ExecutionOutput
}) {
  const [tab, setTab] = useState<'input' | 'result'>('input')
  const payload = tab === 'input' ? input : latestExecution?.result ?? null
  const json = JSON.stringify(payload, null, 2)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>JSON do caso</DialogTitle>
          <DialogDescription>
            Visualizar/copiar o input do caso ou o resultado da última execução.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={tab === 'input' ? 'default' : 'outline'}
            onClick={() => setTab('input')}
          >
            Input
          </Button>
          <Button
            size="sm"
            variant={tab === 'result' ? 'default' : 'outline'}
            onClick={() => setTab('result')}
            disabled={!latestExecution}
          >
            Resultado
          </Button>
          <div className="ml-auto" />
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(json)
              toast.success('JSON copiado')
            }}
          >
            <Copy className="h-3.5 w-3.5" />
            Copiar
          </Button>
        </div>
        <pre className="max-h-[60vh] overflow-auto custom-scroll rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
          {json}
        </pre>
      </DialogContent>
    </Dialog>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
 * Helpers
 * ═══════════════════════════════════════════════════════════════════════ */

interface PointRow {
  idx: number
  s: number          // arc length acumulado a partir do fairlead (frame plot)
  xPlot: number      // x no frame plot (fairlead em 0)
  yPlot: number      // y no frame plot (superfície em 0)
  depth: number      // |yPlot| — profundidade do ponto
  T: number          // |T| total (N)
  Tx: number         // T horizontal (N)
  Ty: number         // T vertical (N)
  angleRad: number   // ângulo da tangente vs horizontal (rad)
  state: 'suspended' | 'grounded'
}

function buildPointRows(result: SolverResult): PointRow[] {
  const xs = result.coords_x ?? []
  const ys = result.coords_y ?? []
  const ts = result.tension_magnitude ?? []
  const txs = result.tension_x ?? []
  const tys = result.tension_y ?? []
  const xtotal = result.total_horz_distance ?? 0
  const waterDepth = result.water_depth ?? 0
  const td = result.dist_to_first_td ?? 0
  const allGrounded =
    (result.total_grounded_length ?? 0) > 0 &&
    (result.total_suspended_length ?? 0) < 1e-6

  const n = Math.min(xs.length, ys.length, ts.length)
  const rows: PointRow[] = []
  // O solver entrega anchor-first; queremos fairlead-first para `s` ser
  // medido a partir do fairlead (convenção offshore: fairlead = 0, âncora = L).
  let prevX = xtotal // primeiro ponto: fairlead em x_plot=0
  let prevY = -result.startpoint_depth + 0
  let s = 0
  for (let i = n - 1; i >= 0; i -= 1) {
    const sx = xs[i]!
    const sy = ys[i]!
    const xPlot = xtotal - sx
    const yPlot = sy - waterDepth
    const depth = waterDepth - sy
    const T = ts[i]!
    const Tx = txs[i] ?? 0
    const Ty = tys[i] ?? 0
    const grounded = allGrounded || (td > 0 && sx <= td + 1e-6 && sy < 0.01)
    if (rows.length > 0) {
      const dx = xPlot - prevX
      const dy = yPlot - prevY
      s += Math.sqrt(dx * dx + dy * dy)
    } else {
      s = 0
    }
    rows.push({
      idx: rows.length,
      s,
      xPlot,
      yPlot,
      depth,
      T,
      Tx,
      Ty,
      angleRad: Math.atan2(Ty, Math.abs(Tx) > 1e-9 ? Tx : 1e-9),
      state: grounded ? 'grounded' : 'suspended',
    })
    prevX = xPlot
    prevY = yPlot
  }
  return rows
}

function fmtForceCompact(siValue: number, system: 'metric' | 'si'): string {
  // Para tabela densa: força sempre em uma unidade compacta (te ou kN).
  if (system === 'metric') {
    const te = siValue / 9806.65
    if (Math.abs(te) >= 0.01) return `${te.toFixed(2)} te`
    return `${(siValue / 1000).toFixed(2)} kN`
  }
  return `${(siValue / 1000).toFixed(2)} kN`
}

function vertical(total: number, h: number): number {
  return Math.sqrt(Math.max(total * total - h * h, 0))
}

function Row({
  label,
  value,
  delta,
  deltaUnit,
  system,
}: {
  label: string
  value: string
  delta?: number | null
  deltaUnit?: 'force' | 'm' | 'pct'
  system?: 'metric' | 'si'
}) {
  const showDelta = delta != null && Math.abs(delta) > 1e-6
  const positive = (delta ?? 0) > 0
  let deltaText = ''
  if (showDelta && delta != null) {
    if (deltaUnit === 'force' && system) {
      deltaText = `${positive ? '+' : ''}${fmtForce(delta, system)}`
    } else if (deltaUnit === 'pct') {
      deltaText = `${positive ? '+' : ''}${(delta * 100).toFixed(2)} pp`
    } else if (deltaUnit === 'm') {
      deltaText = `${positive ? '+' : ''}${delta.toFixed(2)} m`
    }
  }
  return (
    <div className="flex items-baseline justify-between gap-2 text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-baseline gap-1.5">
        {showDelta && (
          <span
            className={`text-[9.5px] ${positive ? 'text-warning' : 'text-success'}`}
          >
            {deltaText}
          </span>
        )}
        <span className="font-medium text-foreground">{value}</span>
      </span>
    </div>
  )
}
