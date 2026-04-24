import { lazy, Suspense, useMemo } from 'react'
import type { SolverResult } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { useThemeStore, resolveTheme } from '@/store/theme'

// Plotly é pesado — lazy-load no client-side.
const Plot = lazy(() => import('react-plotly.js'))

export interface CatenaryPlotProps {
  result: SolverResult
  height?: number
}

/**
 * Perfil 2D da linha. Separa visualmente trecho grounded (seabed) do
 * trecho suspenso (catenária). Markers em âncora, touchdown e fairlead.
 * Hover exibe x/y/|T| em kN.
 */
export function CatenaryPlot({ result, height = 360 }: CatenaryPlotProps) {
  const theme = resolveTheme(useThemeStore((s) => s.theme))

  const layout = useMemo(
    () => ({
      autosize: true,
      height,
      margin: { t: 20, r: 20, b: 50, l: 60 },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: {
        family: 'Inter, system-ui, sans-serif',
        size: 12,
        color: theme === 'dark' ? '#cbd5e1' : '#334155',
      },
      xaxis: {
        title: { text: 'x — Distância horizontal (m)' },
        showgrid: true,
        gridcolor: theme === 'dark' ? '#334155' : '#e2e8f0',
        zerolinecolor: theme === 'dark' ? '#475569' : '#94a3b8',
      },
      yaxis: {
        title: { text: 'y — Elevação (m)' },
        showgrid: true,
        gridcolor: theme === 'dark' ? '#334155' : '#e2e8f0',
        zerolinecolor: theme === 'dark' ? '#475569' : '#94a3b8',
        scaleanchor: 'x' as const, // 1:1 aspect ratio — mantém proporção geométrica
        scaleratio: 1,
      },
      hoverlabel: {
        bgcolor: theme === 'dark' ? '#1e293b' : '#ffffff',
        bordercolor: theme === 'dark' ? '#334155' : '#e2e8f0',
        font: { family: 'Inter' },
      },
      showlegend: true,
      legend: {
        orientation: 'h' as const,
        yanchor: 'bottom' as const,
        y: 1.02,
        xanchor: 'center' as const,
        x: 0.5,
      },
    }),
    [theme, height],
  )

  const data = useMemo(() => {
    const xs = result.coords_x ?? []
    const ys = result.coords_y ?? []
    const ts = result.tension_magnitude ?? []

    // Divide em dois arrays: grounded (y~0 e tensão puramente horizontal) e suspended
    // Critério: se y > 0.01 OU se já passamos do touchdown (dist_to_first_td)
    const td = result.dist_to_first_td ?? 0
    const groundedX: number[] = []
    const groundedY: number[] = []
    const groundedT: number[] = []
    const suspendedX: number[] = []
    const suspendedY: number[] = []
    const suspendedT: number[] = []

    for (let i = 0; i < xs.length; i += 1) {
      const x = xs[i]!
      const y = ys[i]!
      const t = ts[i]!
      if (td > 0 && x <= td + 1e-6 && y < 0.01) {
        groundedX.push(x)
        groundedY.push(y)
        groundedT.push(t)
      } else {
        suspendedX.push(x)
        suspendedY.push(y)
        suspendedT.push(t)
      }
    }

    // Inclui ponto de transição (touchdown) em ambos os traces para continuidade visual
    if (groundedX.length > 0 && suspendedX.length > 0) {
      suspendedX.unshift(groundedX[groundedX.length - 1]!)
      suspendedY.unshift(groundedY[groundedY.length - 1]!)
      suspendedT.unshift(groundedT[groundedT.length - 1]!)
    }

    const traces: Plotly.Data[] = []

    // Seabed line
    if (td > 0 || groundedX.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: [0, Math.max(...xs) * 1.02],
        y: [0, 0],
        line: { color: theme === 'dark' ? '#64748B' : '#94A3B8', width: 1, dash: 'dot' },
        name: 'Seabed',
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    if (groundedX.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: groundedX,
        y: groundedY,
        line: {
          color: theme === 'dark' ? '#FBBF24' : '#D97706',
          width: 3,
        },
        name: 'Trecho apoiado',
        text: groundedT.map((t) => `|T| = ${(t / 1000).toFixed(1)} kN`),
        hovertemplate:
          'x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>',
      })
    }

    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: suspendedX.length > 0 ? suspendedX : xs,
      y: suspendedX.length > 0 ? suspendedY : ys,
      line: {
        color: theme === 'dark' ? '#60A5FA' : '#1E3A5F',
        width: 3,
      },
      name: suspendedX.length > 0 ? 'Trecho suspenso' : 'Linha',
      text: (suspendedX.length > 0 ? suspendedT : ts).map(
        (t) => `|T| = ${(t / 1000).toFixed(1)} kN`,
      ),
      hovertemplate: 'x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>',
    })

    // Marcador: Âncora
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: [0],
      y: [0],
      marker: {
        symbol: 'triangle-up',
        size: 12,
        color: theme === 'dark' ? '#94A3B8' : '#475569',
      },
      name: 'Âncora',
      hovertemplate: 'Âncora<br>x = 0<br>y = 0<extra></extra>',
    })

    // Marcador: Touchdown
    if (td > 0.5) {
      traces.push({
        type: 'scatter',
        mode: 'markers',
        x: [td],
        y: [0],
        marker: {
          symbol: 'diamond',
          size: 11,
          color: theme === 'dark' ? '#FBBF24' : '#D97706',
        },
        name: 'Touchdown',
        hovertemplate:
          'Touchdown<br>x = %{x:.2f} m<br>y = 0<extra></extra>',
      })
    }

    // Marcador: Fairlead
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: [result.total_horz_distance],
      y: [result.endpoint_depth],
      marker: {
        symbol: 'circle',
        size: 12,
        color: theme === 'dark' ? '#60A5FA' : '#1E3A5F',
      },
      name: 'Fairlead',
      hovertemplate:
        `Fairlead<br>x = %{x:.2f} m<br>y = %{y:.2f} m<br>T_fl = ${(result.fairlead_tension / 1000).toFixed(1)} kN<extra></extra>`,
    })

    return traces
  }, [result, theme])

  const config = useMemo<Partial<Plotly.Config>>(
    () => ({
      displaylogo: false,
      responsive: true,
      modeBarButtonsToRemove: [
        'lasso2d',
        'select2d',
        'autoScale2d',
      ] as Plotly.ModeBarDefaultButtons[],
    }),
    [],
  )

  return (
    <Suspense
      fallback={<Skeleton style={{ width: '100%', height }} />}
    >
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={{ width: '100%', height }}
        useResizeHandler
      />
    </Suspense>
  )
}
