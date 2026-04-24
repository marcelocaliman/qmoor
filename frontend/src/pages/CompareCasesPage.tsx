import { useQueries } from '@tanstack/react-query'
import { ArrowLeft, AlertCircle } from 'lucide-react'
import { lazy, Suspense, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getCase } from '@/api/endpoints'
import type { CaseOutput } from '@/api/types'
import { EmptyState } from '@/components/common/EmptyState'
import {
  AlertBadge,
  ModeBadge,
  StatusBadge,
} from '@/components/common/StatusBadge'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn, fmtForceKN, fmtMeters, fmtPercent } from '@/lib/utils'
import { useThemeStore, resolveTheme } from '@/store/theme'

const Plot = lazy(() => import('react-plotly.js'))

const COLORS = ['#1E3A5F', '#B91C1C', '#059669']
const COLORS_DARK = ['#60A5FA', '#F87171', '#34D399']

export function CompareCasesPage() {
  const [params] = useSearchParams()
  const idsRaw = params.get('ids') ?? ''
  const theme = resolveTheme(useThemeStore((s) => s.theme))

  const ids = useMemo(
    () =>
      Array.from(
        new Set(
          idsRaw
            .split(',')
            .map((s) => parseInt(s.trim(), 10))
            .filter((n) => !Number.isNaN(n) && n > 0),
        ),
      ).slice(0, 3),
    [idsRaw],
  )

  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['case', String(id)],
      queryFn: () => getCase(id),
    })),
  })

  const anyLoading = queries.some((q) => q.isLoading)
  const cases = queries
    .map((q) => q.data)
    .filter((c): c is CaseOutput => Boolean(c))

  const breadcrumbs = [
    { label: 'Casos', to: '/cases' },
    { label: 'Comparar' },
  ]

  if (ids.length < 2) {
    return (
      <>
        <Topbar breadcrumbs={breadcrumbs} />
        <div className="flex-1 p-6">
          <EmptyState
            icon={AlertCircle}
            title="Informe ao menos 2 casos para comparar"
            description={
              'Adicione ids à URL, ex: /cases/compare?ids=1,2,3 (máx 3).'
            }
            action={
              <Button asChild>
                <Link to="/cases">
                  <ArrowLeft className="h-4 w-4" />
                  Voltar para Casos
                </Link>
              </Button>
            }
          />
        </div>
      </>
    )
  }

  if (anyLoading) {
    return (
      <>
        <Topbar breadcrumbs={breadcrumbs} />
        <div className="space-y-4 p-6">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </>
    )
  }

  const palette = theme === 'dark' ? COLORS_DARK : COLORS
  const traces = cases
    .map((c, i) => {
      const exec = c.latest_executions?.[0]
      if (!exec) return null
      return {
        type: 'scatter' as const,
        mode: 'lines' as const,
        x: exec.result.coords_x ?? [],
        y: exec.result.coords_y ?? [],
        name: c.name,
        line: { color: palette[i % palette.length], width: 2.5 },
        hovertemplate:
          `${c.name}<br>x=%{x:.1f} m, y=%{y:.1f} m<extra></extra>`,
      }
    })
    .filter(Boolean) as Plotly.Data[]

  const casesWithoutExec = cases.filter(
    (c) => !c.latest_executions?.[0],
  )

  return (
    <>
      <Topbar breadcrumbs={breadcrumbs} />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">
            Comparação
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {cases.length} caso(s)
            </span>
          </h1>
          <Button variant="outline" size="sm" asChild>
            <Link to="/cases">
              <ArrowLeft className="h-4 w-4" />
              Voltar para listagem
            </Link>
          </Button>
        </div>

        {casesWithoutExec.length > 0 && (
          <div className="mb-4 flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
            <AlertCircle className="mt-0.5 h-4 w-4 text-warning" />
            <div>
              <p className="font-medium">
                {casesWithoutExec.length} caso(s) ainda não calculados:
              </p>
              <ul className="ml-4 list-disc text-xs text-muted-foreground">
                {casesWithoutExec.map((c) => (
                  <li key={c.id}>{c.name}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <Card className="mb-5">
          <CardHeader>
            <CardTitle className="text-base">Perfis sobrepostos</CardTitle>
          </CardHeader>
          <CardContent>
            {traces.length < 2 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Pelo menos 2 casos precisam ter execuções para sobrepor.
              </p>
            ) : (
              <Suspense fallback={<Skeleton className="h-96 w-full" />}>
                <Plot
                  data={traces}
                  layout={{
                    autosize: true,
                    height: 420,
                    margin: { t: 20, r: 20, b: 50, l: 60 },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: {
                      family: 'Inter, system-ui, sans-serif',
                      size: 12,
                      color: theme === 'dark' ? '#cbd5e1' : '#334155',
                    },
                    xaxis: {
                      title: { text: 'x (m)' },
                      gridcolor: theme === 'dark' ? '#334155' : '#e2e8f0',
                    },
                    yaxis: {
                      title: { text: 'y (m)' },
                      gridcolor: theme === 'dark' ? '#334155' : '#e2e8f0',
                      scaleanchor: 'x' as const,
                      scaleratio: 1,
                    },
                    legend: {
                      orientation: 'h' as const,
                      yanchor: 'bottom' as const,
                      y: 1.02,
                      xanchor: 'center' as const,
                      x: 0.5,
                    },
                  }}
                  config={{ displaylogo: false, responsive: true }}
                  style={{ width: '100%', height: 420 }}
                  useResizeHandler
                />
              </Suspense>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Saídas lado a lado</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[180px]">Grandeza</TableHead>
                  {cases.map((c, i) => (
                    <TableHead key={c.id}>
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ background: palette[i % palette.length] }}
                          aria-hidden
                        />
                        <Link
                          to={`/cases/${c.id}`}
                          className="font-medium text-foreground hover:underline"
                        >
                          {c.name}
                        </Link>
                      </div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <ComparisonRow
                  label="Status"
                  cases={cases}
                  render={(c) => {
                    const r = c.latest_executions?.[0]?.result
                    return r ? <StatusBadge status={r.status} /> : '—'
                  }}
                />
                <ComparisonRow
                  label="Alert"
                  cases={cases}
                  render={(c) => {
                    const r = c.latest_executions?.[0]?.result
                    return r ? <AlertBadge level={r.alert_level} /> : '—'
                  }}
                />
                <ComparisonRow
                  label="Modo"
                  cases={cases}
                  render={(c) => <ModeBadge mode={c.input.boundary.mode} />}
                />
                <ComparisonRow
                  label="Lâmina"
                  cases={cases}
                  render={(c) => fmtMeters(c.input.boundary.h, 1)}
                />
                <ComparisonNumericRow
                  label="Comprimento"
                  cases={cases}
                  value={(c) => c.input.segments[0]?.length ?? 0}
                  format={(v) => fmtMeters(v, 2)}
                />
                <ComparisonNumericRow
                  label="X total"
                  cases={cases}
                  value={(c) =>
                    c.latest_executions?.[0]?.result.total_horz_distance ?? 0
                  }
                  format={(v) => fmtMeters(v, 2)}
                />
                <ComparisonNumericRow
                  label="T_fl"
                  cases={cases}
                  value={(c) =>
                    c.latest_executions?.[0]?.result.fairlead_tension ?? 0
                  }
                  format={(v) => fmtForceKN(v, 1)}
                />
                <ComparisonNumericRow
                  label="H (horiz)"
                  cases={cases}
                  value={(c) => c.latest_executions?.[0]?.result.H ?? 0}
                  format={(v) => fmtForceKN(v, 1)}
                />
                <ComparisonNumericRow
                  label="T âncora"
                  cases={cases}
                  value={(c) =>
                    c.latest_executions?.[0]?.result.anchor_tension ?? 0
                  }
                  format={(v) => fmtForceKN(v, 1)}
                />
                <ComparisonNumericRow
                  label="L apoiado"
                  cases={cases}
                  value={(c) =>
                    c.latest_executions?.[0]?.result.total_grounded_length ?? 0
                  }
                  format={(v) => fmtMeters(v, 2)}
                />
                <ComparisonNumericRow
                  label="Utilização"
                  cases={cases}
                  value={(c) =>
                    c.latest_executions?.[0]?.result.utilization ?? 0
                  }
                  format={(v) => fmtPercent(v, 2)}
                />
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </>
  )
}

function ComparisonRow({
  label,
  cases,
  render,
}: {
  label: string
  cases: CaseOutput[]
  render: (c: CaseOutput) => React.ReactNode
}) {
  return (
    <TableRow>
      <TableCell className="text-xs font-medium text-muted-foreground">
        {label}
      </TableCell>
      {cases.map((c) => (
        <TableCell key={c.id}>{render(c)}</TableCell>
      ))}
    </TableRow>
  )
}

function ComparisonNumericRow({
  label,
  cases,
  value,
  format,
}: {
  label: string
  cases: CaseOutput[]
  value: (c: CaseOutput) => number
  format: (v: number) => string
}) {
  const values = cases.map(value)
  const base = values[0] ?? 0
  return (
    <TableRow>
      <TableCell className="text-xs font-medium text-muted-foreground">
        {label}
      </TableCell>
      {cases.map((c, i) => {
        const v = values[i]!
        const diff = i === 0 || base === 0 ? 0 : ((v - base) / base) * 100
        return (
          <TableCell key={c.id} className="font-mono tabular-nums">
            <div className="flex items-baseline gap-2">
              <span className="font-medium">{format(v)}</span>
              {i > 0 && Math.abs(diff) > 0.01 && (
                <span
                  className={cn(
                    'text-[10px]',
                    diff > 0 ? 'text-success' : 'text-danger',
                  )}
                >
                  {diff > 0 ? '+' : ''}
                  {diff.toFixed(2)}%
                </span>
              )}
            </div>
          </TableCell>
        )
      })}
    </TableRow>
  )
}
