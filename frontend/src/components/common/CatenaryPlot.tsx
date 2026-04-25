import { lazy, Suspense, useMemo } from 'react'
import type { SolverResult } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { useThemeStore, resolveTheme } from '@/store/theme'

/**
 * Plotly é pesado — lazy-load no client-side.
 *
 * Vite + React 19 + react-plotly.js (CJS) tem um interop ruim com
 * `lazy(() => import('react-plotly.js'))` direto: o `default` vem como
 * um Module Namespace Object em vez de React component. Usamos o
 * factory explícito para construir o componente a partir de plotly.js-dist-min.
 */
function resolveDefault<T>(mod: unknown): T {
  let cur: unknown = mod
  for (let i = 0; i < 3; i += 1) {
    if (typeof cur === 'function') return cur as T
    if (cur && typeof cur === 'object' && 'default' in cur) {
      cur = (cur as { default: unknown }).default
    } else break
  }
  return cur as T
}

const Plot = lazy(async () => {
  const [plotlyMod, factoryMod] = await Promise.all([
    import('plotly.js-dist-min'),
    import('react-plotly.js/factory'),
  ])
  const Plotly = resolveDefault<unknown>(plotlyMod)
  const factory = resolveDefault<(p: unknown) => unknown>(factoryMod)
  if (typeof factory !== 'function') {
    throw new Error(
      'react-plotly.js/factory não retornou uma função após interop. ' +
        `Tipo recebido: ${typeof factory}`,
    )
  }
  const Comp = factory(Plotly)
  return { default: Comp as unknown as React.ComponentType<Record<string, unknown>> }
})

/**
 * Passo "bonito" para eixo dado um range e nº alvo de ticks.
 * Retorna 1, 2, 5, 10, 20, 50, 100, 200, 500, ... (escala 1-2-5).
 */
function niceDtick(range: number, targetTicks = 8): number {
  if (range <= 0 || !Number.isFinite(range)) return 1
  const raw = range / targetTicks
  const exp = Math.floor(Math.log10(raw))
  const pow = 10 ** exp
  const mantissa = raw / pow
  let niceM: number
  if (mantissa < 1.5) niceM = 1
  else if (mantissa < 3.5) niceM = 2
  else if (mantissa < 7.5) niceM = 5
  else niceM = 10
  return niceM * pow
}

// ─────────────────────────────────────────────────────────────────────
// Ícones SVG inline (encoding em data URI). Cores via currentColor não
// funcionam em <img>, então geramos uma versão para light e outra para dark.
// ─────────────────────────────────────────────────────────────────────

function svgDataUri(svg: string): string {
  // encodeURIComponent é seguro para data:image/svg+xml utf-8
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function fairleadSvg(color: string): string {
  // Bloco do casco (semi-sub) com guia do cabo (fairlead chock).
  // Viewbox simétrico 64×64. Cabo sai pelo fairlead chock no canto inferior direito.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
    <rect x="6" y="14" width="52" height="22" rx="3" fill="${color}" opacity="0.85"/>
    <rect x="14" y="6" width="36" height="10" rx="2" fill="${color}"/>
    <circle cx="48" cy="40" r="6" fill="none" stroke="${color}" stroke-width="3"/>
    <line x1="48" y1="46" x2="48" y2="58" stroke="${color}" stroke-width="2"/>
  </svg>`
}

function anchorSvg(color: string): string {
  // Âncora náutica clássica simplificada.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
    <circle cx="32" cy="10" r="5" fill="none" stroke="${color}" stroke-width="3"/>
    <line x1="32" y1="15" x2="32" y2="50" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
    <line x1="22" y1="22" x2="42" y2="22" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
    <path d="M 12 42 Q 12 56 32 56 Q 52 56 52 42" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
  </svg>`
}

export interface CatenaryPlotProps {
  result: SolverResult
  /**
   * Altura em pixels. Se omitida, preenche 100% do container (o pai
   * deve ter altura explícita). Útil para layouts responsivos.
   */
  height?: number
  /** Força aspect ratio 1:1 (representação geométrica fiel). Default: false. */
  equalAspect?: boolean
}

/**
 * Perfil 2D da linha em sistema de coordenadas surface-relative:
 *   - X = 0 no FAIRLEAD (à esquerda); X cresce em direção à âncora.
 *   - Y = 0 na superfície da água; Y negativo desce.
 *   - Fairlead em (0, -startpoint_depth)
 *   - Âncora  em (total_horz_distance, -water_depth)
 *   - Seabed plotado como linha horizontal em y = -water_depth.
 *   - Superfície plotada como linha em y = 0.
 *
 * O solver entrega coords no frame anchor-fixo (âncora em (0,0), fairlead
 * em (X, h_drop)). Aqui aplicamos a transformação:
 *   plot_x = X − solver_x       (inverte: anchor à direita, fairlead à esquerda)
 *   plot_y = solver_y − water_depth  (translada para superfície em y=0)
 *
 * Trechos grounded e suspenso são separados visualmente. Marcadores e
 * ícones SVG identificam fairlead e âncora.
 */
export function CatenaryPlot({
  result,
  height,
  equalAspect = false,
}: CatenaryPlotProps) {
  const fillContainer = height == null
  const plotStyle: React.CSSProperties = fillContainer
    ? { width: '100%', height: '100%' }
    : { width: '100%', height }
  const theme = resolveTheme(useThemeStore((s) => s.theme))

  // Paleta theme-aware
  const palette = useMemo(() => {
    if (theme === 'dark') {
      return {
        seabed: '#475569',
        seabedFill: 'rgba(71, 85, 105, 0.18)',
        surface: '#3B82F6',
        surfaceFill: 'rgba(59, 130, 246, 0.06)',
        suspended: '#60A5FA',
        grounded: '#FBBF24',
        anchor: '#94A3B8',
        fairlead: '#60A5FA',
        grid: '#1E293B',
        zero: '#334155',
        text: '#CBD5E1',
        hoverBg: '#1E293B',
        hoverBorder: '#334155',
        iconColor: '#93C5FD',
        anchorIconColor: '#94A3B8',
      }
    }
    return {
      seabed: '#64748B',
      seabedFill: 'rgba(148, 163, 184, 0.15)',
      surface: '#0EA5E9',
      surfaceFill: 'rgba(14, 165, 233, 0.05)',
      suspended: '#1E3A5F',
      grounded: '#D97706',
      anchor: '#475569',
      fairlead: '#1E3A5F',
      grid: '#E2E8F0',
      zero: '#94A3B8',
      text: '#334155',
      hoverBg: '#FFFFFF',
      hoverBorder: '#E2E8F0',
      iconColor: '#1E3A5F',
      anchorIconColor: '#475569',
    }
  }, [theme])

  const xs = useMemo(() => result.coords_x ?? [], [result.coords_x])
  const ys = useMemo(() => result.coords_y ?? [], [result.coords_y])
  const ts = useMemo(
    () => result.tension_magnitude ?? [],
    [result.tension_magnitude],
  )

  const Xtotal = result.total_horz_distance ?? 0
  const waterDepth = result.water_depth ?? 0
  const startpointDepth = result.startpoint_depth ?? 0
  const fairleadY = -startpointDepth
  const anchorY = -waterDepth
  const td = result.dist_to_first_td ?? 0

  // Transforma cada ponto da curva do frame solver para o frame surface-relative.
  // plot_x = X − solver_x  (fairlead à esquerda, anchor à direita)
  // plot_y = solver_y − water_depth (Y=0 na superfície)
  const curve = useMemo(() => {
    const plotX: number[] = []
    const plotY: number[] = []
    const tensions: number[] = []
    const onGround: boolean[] = []
    // Caso laid_line: toda a linha está em y_solver=0 e total_grounded_length=L.
    // Tratamos todos os pontos como grounded para colorir corretamente.
    const allGrounded =
      (result.total_grounded_length ?? 0) > 0 &&
      (result.total_suspended_length ?? 0) < 1e-6
    for (let i = 0; i < xs.length; i += 1) {
      const sx = xs[i]!
      const sy = ys[i]!
      plotX.push(Xtotal - sx)
      plotY.push(sy - waterDepth)
      tensions.push(ts[i]!)
      // grounded se: (a) caso degenerado horizontal; ou (b) ponto no seabed
      // antes do touchdown na catenária com apoio.
      onGround.push(
        allGrounded || (td > 0 && sx <= td + 1e-6 && sy < 0.01),
      )
    }
    plotX.reverse()
    plotY.reverse()
    tensions.reverse()
    onGround.reverse()
    return { plotX, plotY, tensions, onGround }
  }, [xs, ys, ts, td, Xtotal, waterDepth, result.total_grounded_length, result.total_suspended_length])

  // Ranges para definir layout/ticks
  const ranges = useMemo(() => {
    const xMin = 0
    const xMax = Math.max(Xtotal, 1)
    const yMin = -Math.max(waterDepth, 1)
    const yMax = 0
    const xPad = (xMax - xMin) * 0.08
    const yPad = (yMax - yMin) * 0.18
    const xRange = [xMin - xPad, xMax + xPad]
    const yRange = [yMin - yPad, yMax + yPad]
    const xDtick = niceDtick(xRange[1]! - xRange[0]!, 8)
    const yDtick = niceDtick(yRange[1]! - yRange[0]!, 6)
    return { xRange, yRange, xDtick, yDtick }
  }, [Xtotal, waterDepth])

  const data = useMemo(() => {
    const traces: Plotly.Data[] = []

    // ── Faixa "água" (entre superfície y=0 e seabed y=-water_depth) ──
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: [ranges.xRange[0], ranges.xRange[1], ranges.xRange[1], ranges.xRange[0]],
      y: [0, 0, anchorY, anchorY],
      fill: 'toself',
      fillcolor: palette.surfaceFill,
      line: { width: 0 },
      hoverinfo: 'skip',
      showlegend: false,
    })

    // ── Linha da superfície (y=0) ──
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: [ranges.xRange[0], ranges.xRange[1]],
      y: [0, 0],
      line: { color: palette.surface, width: 1.5, dash: 'dash' },
      name: 'Superfície',
      hoverinfo: 'skip',
      showlegend: false,
    })

    // ── Seabed: linha sólida + faixa hachurada abaixo ──
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: [ranges.xRange[0], ranges.xRange[1], ranges.xRange[1], ranges.xRange[0]],
      y: [anchorY, anchorY, ranges.yRange[0], ranges.yRange[0]],
      fill: 'toself',
      fillcolor: palette.seabedFill,
      line: { width: 0 },
      hoverinfo: 'skip',
      showlegend: false,
    })
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: [ranges.xRange[0], ranges.xRange[1]],
      y: [anchorY, anchorY],
      line: { color: palette.seabed, width: 2 },
      name: 'Seabed',
      hoverinfo: 'skip',
      showlegend: false,
    })

    // ── Linha de mergulho do fairlead (vertical da superfície ao fairlead) ──
    if (startpointDepth > 0.5) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: [0, 0],
        y: [0, fairleadY],
        line: { color: palette.fairlead, width: 1, dash: 'dot' },
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    // ── Trechos: separar suspenso vs grounded ──
    const groundedX: number[] = []
    const groundedY: number[] = []
    const groundedT: number[] = []
    const suspendedX: number[] = []
    const suspendedY: number[] = []
    const suspendedT: number[] = []
    for (let i = 0; i < curve.plotX.length; i += 1) {
      if (curve.onGround[i]) {
        groundedX.push(curve.plotX[i]!)
        groundedY.push(curve.plotY[i]!)
        groundedT.push(curve.tensions[i]!)
      } else {
        suspendedX.push(curve.plotX[i]!)
        suspendedY.push(curve.plotY[i]!)
        suspendedT.push(curve.tensions[i]!)
      }
    }
    // Costura visual no touchdown: junta o último ponto suspenso ao primeiro grounded.
    if (suspendedX.length > 0 && groundedX.length > 0) {
      suspendedX.push(groundedX[0]!)
      suspendedY.push(groundedY[0]!)
      suspendedT.push(groundedT[0]!)
    }

    if (suspendedX.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: suspendedX,
        y: suspendedY,
        line: { color: palette.suspended, width: 3.5 },
        name: 'Trecho suspenso',
        text: suspendedT.map((t) => `|T| = ${(t / 1000).toFixed(1)} kN`),
        hovertemplate:
          'x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>',
      })
    }
    if (groundedX.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        x: groundedX,
        y: groundedY,
        line: { color: palette.grounded, width: 3.5 },
        name: 'Trecho apoiado',
        text: groundedT.map((t) => `|T| = ${(t / 1000).toFixed(1)} kN`),
        hovertemplate:
          'x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>',
      })
    }

    // ── Marker do fairlead (em x=0) ──
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: [0],
      y: [fairleadY],
      marker: {
        symbol: 'circle',
        size: 14,
        color: palette.fairlead,
        line: { color: '#FFFFFF', width: 2 },
      },
      name: 'Fairlead',
      hovertemplate:
        `Fairlead<br>x = 0<br>y = ${fairleadY.toFixed(2)} m<br>` +
        `T_fl = ${(result.fairlead_tension / 1000).toFixed(1)} kN<extra></extra>`,
    })

    // ── Marker da âncora (em x=Xtotal, y=-water_depth) ──
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: [Xtotal],
      y: [anchorY],
      marker: {
        symbol: 'triangle-up',
        size: 14,
        color: palette.anchor,
        line: { color: '#FFFFFF', width: 1.5 },
      },
      name: 'Âncora',
      hovertemplate:
        `Âncora<br>x = ${Xtotal.toFixed(2)} m<br>y = ${anchorY.toFixed(2)} m<br>` +
        `T_anc = ${(result.anchor_tension / 1000).toFixed(1)} kN<extra></extra>`,
    })

    // ── Marker do touchdown (na linha do seabed) ──
    if (td > 0.5) {
      traces.push({
        type: 'scatter',
        mode: 'markers',
        x: [Xtotal - td],
        y: [anchorY],
        marker: {
          symbol: 'diamond',
          size: 11,
          color: palette.grounded,
          line: { color: '#FFFFFF', width: 1.5 },
        },
        name: 'Touchdown',
        hovertemplate:
          `Touchdown<br>x = ${(Xtotal - td).toFixed(2)} m<extra></extra>`,
      })
    }

    return traces
  }, [
    curve,
    ranges,
    palette,
    anchorY,
    fairleadY,
    startpointDepth,
    td,
    Xtotal,
    result.fairlead_tension,
    result.anchor_tension,
  ])

  // ── Imagens SVG sobrepostas (fairlead + âncora) ──
  // Tamanho proporcional ao range do menor eixo, para não dominar o canvas.
  const images = useMemo(() => {
    const xSpan = ranges.xRange[1]! - ranges.xRange[0]!
    const ySpan = ranges.yRange[1]! - ranges.yRange[0]!
    // ícone de ~9% do menor span; assim ele não some quando a água é rasa nem
    // estoura quando o trecho horizontal é longo.
    const iconBase = Math.min(xSpan, ySpan) * 0.09
    return [
      {
        source: svgDataUri(fairleadSvg(palette.iconColor)),
        xref: 'x',
        yref: 'y',
        x: 0,
        y: fairleadY,
        sizex: iconBase,
        sizey: iconBase,
        xanchor: 'center',
        yanchor: 'middle',
        layer: 'above',
      },
      {
        source: svgDataUri(anchorSvg(palette.anchorIconColor)),
        xref: 'x',
        yref: 'y',
        x: Xtotal,
        y: anchorY,
        sizex: iconBase,
        sizey: iconBase,
        xanchor: 'center',
        yanchor: 'middle',
        layer: 'above',
      },
    ]
  }, [ranges, palette, fairleadY, anchorY, Xtotal])

  // ── Annotations: rótulos dos pontos ──
  const annotations = useMemo(
    () => [
      {
        x: 0,
        y: fairleadY,
        xref: 'x',
        yref: 'y',
        text: 'Fairlead',
        showarrow: false,
        xanchor: 'left',
        yanchor: 'top',
        xshift: 14,
        yshift: -8,
        font: { size: 11, color: palette.text, family: 'Inter' },
      },
      {
        x: Xtotal,
        y: anchorY,
        xref: 'x',
        yref: 'y',
        text: 'Âncora',
        showarrow: false,
        xanchor: 'right',
        yanchor: 'top',
        xshift: -14,
        yshift: -8,
        font: { size: 11, color: palette.text, family: 'Inter' },
      },
    ],
    [fairleadY, anchorY, Xtotal, palette.text],
  )

  const layout = useMemo(() => {
    const yAxis: Record<string, unknown> = {
      title: { text: 'Elevação (m) — superfície em y=0' },
      showgrid: true,
      gridcolor: palette.grid,
      zeroline: true,
      zerolinecolor: palette.surface,
      zerolinewidth: 1,
      range: ranges.yRange,
      dtick: ranges.yDtick,
      tickformat: ',.0f',
    }
    if (equalAspect) {
      yAxis.scaleanchor = 'x'
      yAxis.scaleratio = 1
    }

    return {
      autosize: true,
      ...(height != null ? { height } : {}),
      margin: { t: 18, r: 24, b: 48, l: 64 },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: {
        family: 'Inter, system-ui, sans-serif',
        size: 12,
        color: palette.text,
      },
      xaxis: {
        title: { text: 'Distância horizontal a partir do fairlead (m)' },
        showgrid: true,
        gridcolor: palette.grid,
        zerolinecolor: palette.zero,
        range: ranges.xRange,
        dtick: ranges.xDtick,
        tickformat: ',.0f',
      },
      yaxis: yAxis,
      hoverlabel: {
        bgcolor: palette.hoverBg,
        bordercolor: palette.hoverBorder,
        font: {
          family: 'Inter',
          color: theme === 'dark' ? '#F1F5F9' : '#0F172A',
          size: 12,
        },
        align: 'left',
      },
      showlegend: true,
      legend: {
        orientation: 'h' as const,
        yanchor: 'bottom' as const,
        y: 1.02,
        xanchor: 'center' as const,
        x: 0.5,
      },
      images,
      annotations,
    }
  }, [palette, ranges, equalAspect, height, images, annotations, theme])

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
    <Suspense fallback={<Skeleton style={plotStyle} />}>
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={plotStyle}
        useResizeHandler
      />
    </Suspense>
  )
}
