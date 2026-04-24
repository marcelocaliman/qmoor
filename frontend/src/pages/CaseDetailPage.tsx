import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  AlertCircle,
  CheckCircle2,
  Code2,
  Copy,
  Download,
  FileText,
  History,
  MoreHorizontal,
  Pencil,
  Play,
  RefreshCw,
  Table as TableIcon,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
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
import type { ExecutionOutput } from '@/api/types'
import { CatenaryPlot } from '@/components/common/CatenaryPlot'
import { EmptyState } from '@/components/common/EmptyState'
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
import { fmtForceKN, fmtMeters, fmtNumber, fmtPercent } from '@/lib/utils'

export function CaseDetailPage() {
  const { id } = useParams()
  const caseId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [selectedExecId, setSelectedExecId] = useState<number | null>(null)

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
  const result = execToShow?.result

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
          <DropdownMenuItem asChild>
            <a href={exportPdfUrl(caseId)} target="_blank" rel="noreferrer">
              <FileText className="h-4 w-4" />
              PDF (relatório)
            </a>
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
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Coluna principal */}
        <div className="flex-1 overflow-auto custom-scroll p-6">
          {/* Header do caso */}
          <header className="mb-5 flex flex-col gap-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {data.name}
                </h1>
                {data.description && (
                  <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                    {data.description}
                  </p>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <CategoryBadge category={caseInput.segments[0]?.category} />
              {caseInput.segments[0]?.line_type && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  {caseInput.segments[0].line_type}
                </Badge>
              )}
              <ModeBadge mode={caseInput.boundary.mode} />
              {result && <StatusBadge status={result.status} />}
              {result && <AlertBadge level={result.alert_level} />}
              <span className="ml-auto">
                Criado em{' '}
                {format(new Date(data.created_at), "dd 'de' MMM, yyyy", {
                  locale: ptBR,
                })}{' '}
                · Atualizado{' '}
                {format(new Date(data.updated_at), "dd 'de' MMM 'às' HH:mm", {
                  locale: ptBR,
                })}
              </span>
            </div>
          </header>

          {/* Sem execução ainda */}
          {!result && (
            <EmptyState
              icon={Play}
              title="Caso ainda não foi calculado"
              description="Execute o solver para ver resultados, perfil 2D e alert level."
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
          )}

          {result && (
            <>
              {/* Alert banner se status não é converged */}
              {result.status !== 'converged' && (
                <div className="mb-5 flex items-start gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
                  <AlertCircle className="mt-0.5 h-4 w-4 text-warning" />
                  <div>
                    <p className="font-medium text-warning-foreground">
                      Status do solver: {result.status}
                    </p>
                    <p className="text-muted-foreground">{result.message}</p>
                  </div>
                </div>
              )}

              {/* Gráfico */}
              <Card className="mb-4">
                <CardContent className="p-2">
                  <CatenaryPlot result={result} />
                </CardContent>
              </Card>

              {/* Grid de cards */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {/* Tração */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Tração no fairlead
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="font-mono text-2xl font-semibold tabular-nums">
                      {fmtNumber(result.fairlead_tension / 1000, 1)}
                      <span className="ml-1 text-sm font-normal text-muted-foreground">
                        kN
                      </span>
                    </div>
                    <UtilizationGauge
                      value={result.utilization}
                      alertLevel={result.alert_level}
                    />
                    <p className="text-[11px] text-muted-foreground">
                      T_fl / MBL = {fmtPercent(result.utilization, 1)}
                    </p>
                  </CardContent>
                </Card>

                {/* Geometria */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Geometria
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 font-mono text-sm tabular-nums">
                    <Row label="X total" value={fmtMeters(result.total_horz_distance, 2)} />
                    <Row label="Suspenso" value={fmtMeters(result.total_suspended_length, 2)} />
                    <Row label="Apoiado" value={fmtMeters(result.total_grounded_length, 2)} />
                    {result.dist_to_first_td != null && result.dist_to_first_td > 0 && (
                      <Row label="Touchdown" value={fmtMeters(result.dist_to_first_td, 2)} />
                    )}
                  </CardContent>
                </Card>

                {/* Forças secundárias */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Forças
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 font-mono text-sm tabular-nums">
                    <Row label="H (horiz.)" value={fmtForceKN(result.H, 1)} />
                    <Row label="T âncora" value={fmtForceKN(result.anchor_tension, 1)} />
                    <Row label="ΔL" value={fmtMeters(result.elongation, 3)} />
                    <Row
                      label="L esticado"
                      value={fmtMeters(result.stretched_length, 2)}
                    />
                  </CardContent>
                </Card>

                {/* Convergência */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Convergência
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex items-center gap-2">
                      {result.status === 'converged' ? (
                        <CheckCircle2 className="h-5 w-5 text-success" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-warning" />
                      )}
                      <StatusBadge status={result.status} />
                    </div>
                    <p className="font-mono text-xs tabular-nums text-muted-foreground">
                      {result.iterations_used} iterações
                    </p>
                    {execToShow && (
                      <p className="text-[11px] text-muted-foreground">
                        {format(
                          new Date(execToShow.executed_at),
                          "dd MMM, HH:mm",
                          { locale: ptBR },
                        )}
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>

        {/* Painel lateral com abas */}
        {result && (
          <aside className="hidden w-[380px] shrink-0 border-l border-border bg-card/40 lg:flex lg:flex-col">
            <Tabs defaultValue="points" className="flex flex-1 flex-col">
              <TabsList className="mx-3 mt-3 justify-start">
                <TabsTrigger value="points" className="gap-1.5">
                  <TableIcon className="h-3.5 w-3.5" />
                  Pontos
                </TabsTrigger>
                <TabsTrigger value="history" className="gap-1.5">
                  <History className="h-3.5 w-3.5" />
                  Histórico
                  {executions.length > 1 && (
                    <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                      {executions.length}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="json" className="gap-1.5">
                  <Code2 className="h-3.5 w-3.5" />
                  JSON
                </TabsTrigger>
              </TabsList>

              <TabsContent
                value="points"
                className="mt-0 flex-1 overflow-auto custom-scroll p-3"
              >
                <PointsTable result={result} />
              </TabsContent>

              <TabsContent
                value="history"
                className="mt-0 flex-1 overflow-auto custom-scroll p-3"
              >
                <HistoryList
                  executions={executions}
                  selectedId={selectedExecId ?? latest?.id ?? 0}
                  onSelect={setSelectedExecId}
                />
              </TabsContent>

              <TabsContent
                value="json"
                className="mt-0 flex-1 overflow-auto custom-scroll p-3"
              >
                <JsonSnippet data={caseInput} />
              </TabsContent>
            </Tabs>
          </aside>
        )}
      </div>

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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  )
}

function PointsTable({ result }: { result: import('@/api/types').SolverResult }) {
  const xs = result.coords_x ?? []
  const ys = result.coords_y ?? []
  const ts = result.tension_magnitude ?? []
  const n = Math.min(xs.length, ys.length, ts.length)

  function downloadCsv() {
    const rows = [['s (m)', 'x (m)', 'y (m)', '|T| (N)']]
    // s = arc length aproximado — soma de distâncias entre pontos consecutivos
    let arc = 0
    rows.push(['0.000', xs[0]!.toFixed(3), ys[0]!.toFixed(3), ts[0]!.toFixed(1)])
    for (let i = 1; i < n; i += 1) {
      const dx = xs[i]! - xs[i - 1]!
      const dy = ys[i]! - ys[i - 1]!
      arc += Math.sqrt(dx * dx + dy * dy)
      rows.push([
        arc.toFixed(3),
        xs[i]!.toFixed(3),
        ys[i]!.toFixed(3),
        ts[i]!.toFixed(1),
      ])
    }
    const csv = rows.map((r) => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'pontos.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Pontos discretizados ({n})
        </h3>
        <Button variant="outline" size="sm" onClick={downloadCsv}>
          <Download className="h-3.5 w-3.5" />
          CSV
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead className="text-right">x (m)</TableHead>
            <TableHead className="text-right">y (m)</TableHead>
            <TableHead className="text-right">|T| kN</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: n }).map((_, i) => (
            <TableRow key={i}>
              <TableCell className="font-mono text-xs">{i}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {xs[i]!.toFixed(2)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {ys[i]!.toFixed(2)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {(ts[i]! / 1000).toFixed(2)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  )
}

function HistoryList({
  executions,
  selectedId,
  onSelect,
}: {
  executions: ExecutionOutput[]
  selectedId: number
  onSelect: (id: number) => void
}) {
  if (executions.length === 0) {
    return (
      <p className="px-2 py-6 text-center text-sm text-muted-foreground">
        Nenhuma execução ainda.
      </p>
    )
  }
  return (
    <div className="space-y-1.5">
      <p className="mb-2 text-[11px] text-muted-foreground">
        Últimas {executions.length} execuções. Click para visualizar.
      </p>
      {executions.map((e) => (
        <button
          key={e.id}
          type="button"
          onClick={() => onSelect(e.id)}
          className={`flex w-full flex-col items-start gap-1 rounded-md border border-transparent p-2.5 text-left text-sm transition-colors hover:bg-muted/60 ${
            e.id === selectedId ? 'border-primary/30 bg-primary/5' : ''
          }`}
        >
          <div className="flex w-full items-center gap-2">
            <StatusBadge status={e.result.status} />
            <AlertBadge level={e.result.alert_level} />
            <span className="ml-auto font-mono text-xs text-muted-foreground">
              {format(new Date(e.executed_at), 'HH:mm:ss', { locale: ptBR })}
            </span>
          </div>
          <div className="flex w-full items-baseline justify-between gap-2 font-mono text-xs text-muted-foreground">
            <span>T_fl {fmtNumber(e.result.fairlead_tension / 1000, 1)} kN</span>
            <span>X {fmtNumber(e.result.total_horz_distance, 1)} m</span>
          </div>
        </button>
      ))}
    </div>
  )
}

function JsonSnippet({ data }: { data: unknown }) {
  const json = JSON.stringify(data, null, 2)
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Input do caso</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            navigator.clipboard.writeText(json)
            toast.success('JSON copiado')
          }}
        >
          <Copy className="h-3.5 w-3.5" />
          Copiar
        </Button>
      </div>
      <pre className="max-h-96 overflow-auto custom-scroll rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
        {json}
      </pre>
    </div>
  )
}
