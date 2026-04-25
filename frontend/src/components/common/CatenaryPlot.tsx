import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { LineAttachment, SolverResult } from '@/api/types'
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

function buoySvg(color: string): string {
  // Boia esférica de amarração — corpo NA PARTE DE CIMA, manilha
  // EMBAIXO. Convenção física: a boia flutua para cima e o pendant
  // desce dela até a linha principal abaixo, então o ponto de
  // conexão (manilha) fica na base da boia.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
    <circle cx="32" cy="28" r="18" fill="${color}" opacity="0.85"/>
    <line x1="14" y1="28" x2="50" y2="28" stroke="#FFFFFF" stroke-width="1.5" opacity="0.55"/>
    <line x1="32" y1="46" x2="32" y2="54" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="32" cy="57" r="3.5" fill="none" stroke="${color}" stroke-width="2.5"/>
  </svg>`
}

function clumpSvg(color: string): string {
  // Bloco de peso (concreto/aço) com manilha de içamento no topo.
  // Pequenos chanfros nos cantos para sugerir massa pesada.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
    <circle cx="32" cy="10" r="3.5" fill="none" stroke="${color}" stroke-width="2.5"/>
    <line x1="32" y1="13.5" x2="32" y2="22" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M 14 24 L 50 24 L 52 50 Q 32 56 12 50 Z" fill="${color}" opacity="0.85"/>
    <line x1="20" y1="34" x2="44" y2="34" stroke="#FFFFFF" stroke-width="1" opacity="0.55"/>
    <line x1="20" y1="42" x2="44" y2="42" stroke="#FFFFFF" stroke-width="1" opacity="0.55"/>
  </svg>`
}

/**
 * Replica a estrutura pós-split do resolver de attachments do backend
 * (`backend/solver/attachment_resolver.py`). Quando uma boia/clump é
 * informada via `position_s_from_anchor` e cai no meio de um segmento,
 * o solver divide aquele segmento em dois sub-segmentos do mesmo
 * material para usar a matemática clássica de junções.
 *
 * O frontend precisa replicar a mesma lógica para:
 *   1. Atribuir cores corretas a cada sub-segmento (mapeando ao
 *      segmento original do usuário) → `userIdxOf`.
 *   2. Localizar precisamente onde cada attachment está na curva
 *      renderizada → `attachmentJunctionIdx` (índice em
 *      segment_boundaries).
 *
 * Retorna:
 *   - userIdxOf[k]: índice do user-segment (0..N_user-1) que contém
 *     o sub-segmento pós-split k (0..N_post-1, anchor-first).
 *   - postCum: arc length cumulativo nas junções pós-split, em metros
 *     (frame anchor-first). postCum[j] é o arc length da âncora até
 *     a junção j; postCum[0]=0, postCum[N_post]=L_total.
 *   - attachmentJunctionIdx[i]: para attachment i, qual junção da
 *     pós-estrutura ele ocupa (1..N_post-1), ou null se posição
 *     inválida.
 */
function buildPostSplitStructure(
  userSegments: Array<{ length?: number }>,
  attachments?: Array<{
    position_index?: number | null
    position_s_from_anchor?: number | null
  }>,
): {
  userIdxOf: number[]
  postCum: number[]
  attachmentJunctionIdx: Array<number | null>
} {
  const lengths = userSegments.map((s) => s.length ?? 0)
  const cum: number[] = [0]
  for (const L of lengths) cum.push(cum[cum.length - 1]! + L)
  const totalLen = cum[cum.length - 1]!
  const TOL = 1e-6

  // 1. Calcula a posição canônica (s_from_anchor) de cada attachment.
  const attsCanonical: Array<number | null> = (attachments ?? []).map((a) => {
    if (a.position_s_from_anchor != null) return a.position_s_from_anchor
    if (a.position_index != null) return cum[a.position_index + 1] ?? null
    return null
  })

  // 2. Coleta posições que disparam split (não coincidem com junção).
  const splits = new Set<number>()
  for (const s of attsCanonical) {
    if (s == null || s <= TOL || s >= totalLen - TOL) continue
    const isAtJunction = cum.some((c) => Math.abs(c - s) < TOL)
    if (!isAtJunction) splits.add(s)
  }
  const splitArr = Array.from(splits).sort((a, b) => a - b)

  // 3. Constrói lista de sub-segmentos pós-split com mapeamento ao user.
  const userIdxOf: number[] = []
  const postCum: number[] = [0]
  for (let k = 0; k < userSegments.length; k += 1) {
    const a = cum[k]!
    const b = cum[k + 1]!
    const internal = splitArr.filter((s) => s > a + TOL && s < b - TOL)
    const breakpoints = [a, ...internal, b]
    for (let i = 0; i < breakpoints.length - 1; i += 1) {
      userIdxOf.push(k)
      postCum.push(breakpoints[i + 1]!)
    }
  }

  // 4. Para cada attachment, encontra sua junção na pós-estrutura por
  //    matching de arc length.
  const attachmentJunctionIdx: Array<number | null> = attsCanonical.map(
    (s) => {
      if (s == null) return null
      // junção j em segment_boundaries está em postCum[j] (j=0 é a âncora,
      // j=N_post é o fairlead; junções intermediárias são 1..N_post-1).
      for (let j = 1; j < postCum.length - 1; j += 1) {
        if (Math.abs(postCum[j]! - s) < TOL) return j
      }
      return null
    },
  )

  return { userIdxOf, postCum, attachmentJunctionIdx }
}

// Estilo visual por categoria de cabo. Dash + largura comunicam o tipo
// de material (corrente x cabo de aço x sintético) mesmo em B&W. A cor
// fica por conta de uma paleta indexada pelo segmento (ver `segPalette`).
type CableDash = 'solid' | 'dash' | 'dot' | 'dashdot'
const CATEGORY_STYLE: Record<
  string,
  { dash: CableDash; width: number; label: string }
> = {
  Wire: { dash: 'solid', width: 3, label: 'Wire' },
  StuddedChain: { dash: 'solid', width: 5, label: 'Studded chain' },
  StudlessChain: { dash: 'dash', width: 4.5, label: 'Studless chain' },
  Polyester: { dash: 'dot', width: 3, label: 'Poliéster' },
}

export interface SegmentMeta {
  category?: 'Wire' | 'StuddedChain' | 'StudlessChain' | 'Polyester' | null
  line_type?: string | null
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
  /**
   * Attachments aplicados (boias e clumps). F5.2. Renderizados como
   * ícones SVG nas junções entre segmentos (markers transparentes só
   * para hover).
   */
  attachments?: LineAttachment[]
  /**
   * Inclinação do seabed em radianos. F5.3. 0 = horizontal (default).
   * Positivo = seabed sobe em direção ao fairlead.
   */
  seabedSlopeRad?: number
  /**
   * Metadados dos segmentos (na mesma ordem do solver: idx 0 = junto à
   * âncora). Quando informado em modo multi-segmento, controla o estilo
   * visual da linha por categoria (dash/largura) e exibe o `line_type`
   * na legenda.
   */
  segments?: SegmentMeta[]
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
  attachments = [],
  seabedSlopeRad = 0,
  segments = [],
}: CatenaryPlotProps) {
  const fillContainer = height == null
  const plotStyle: React.CSSProperties = fillContainer
    ? { width: '100%', height: '100%' }
    : { width: '100%', height }
  const theme = resolveTheme(useThemeStore((s) => s.theme))

  // Hover highlight bidirecional (legenda ↔ traço): quando o usuário
  // passa o mouse sobre um chip da legenda OU sobre um segmento no plot,
  // aquele segmento "acende" (linha mais grossa) e os demais ficam
  // dimmed para reforçar o foco. Só aplicável em multi-segmento.
  const [hoveredUserIdx, setHoveredUserIdx] = useState<number | null>(null)
  // Mapeamento traceIndex (curveNumber do Plotly) → userIdx do segmento
  // do form. Ref em vez de state pra não disparar re-render quando o
  // useMemo de data atualiza (já estamos no mesmo ciclo).
  const traceUserIdxRef = useRef<Array<number | null>>([])

  // Mede o canvas do plot para que os ícones SVG (fairlead, âncora,
  // boia, clump) tenham tamanho **constante em pixels** independente do
  // range dos eixos. Sem isso, em catenárias longas (X grande) os
  // ícones encolhem porque sizex/sizey são em unidades de dado.
  const plotContainerRef = useRef<HTMLDivElement>(null)
  const [plotPx, setPlotPx] = useState<{ w: number; h: number } | null>(null)
  useEffect(() => {
    const el = plotContainerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      const e = entries[0]
      if (!e) return
      const { width, height } = e.contentRect
      if (width > 0 && height > 0) setPlotPx({ w: width, h: height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Paleta theme-aware
  const palette = useMemo(() => {
    if (theme === 'dark') {
      return {
        seabed: '#475569',
        seabedFill: 'rgba(71, 85, 105, 0.18)',
        surface: '#3B82F6',
        surfaceFill: 'rgba(59, 130, 246, 0.06)',
        suspended: '#60A5FA',
        // Trecho apoiado (e marcador touchdown) propositalmente em
        // vermelho — destaca o ponto crítico onde a linha encontra o
        // seabed e a porção apoiada que pode estar arrastando. Antes era
        // amarelo, mas conflitava com cores cíclicas de multi-segmento.
        grounded: '#EF4444',
        anchor: '#94A3B8',
        fairlead: '#60A5FA',
        grid: '#1E293B',
        zero: '#334155',
        text: '#CBD5E1',
        hoverBg: '#1E293B',
        hoverBorder: '#334155',
        iconColor: '#93C5FD',
        anchorIconColor: '#94A3B8',
        buoyIconColor: '#3B82F6',
        clumpIconColor: '#FBBF24',
        // Touchdown propositalmente vermelho para destacar dos
        // demais marcadores e cores de segmento (multi-segmento usa
        // paleta cíclica que pode incluir amarelo/laranja).
        touchdown: '#EF4444',
      }
    }
    return {
      seabed: '#64748B',
      seabedFill: 'rgba(148, 163, 184, 0.15)',
      surface: '#0EA5E9',
      surfaceFill: 'rgba(14, 165, 233, 0.05)',
      suspended: '#1E3A5F',
      grounded: '#DC2626',
      anchor: '#475569',
      fairlead: '#1E3A5F',
      grid: '#E2E8F0',
      zero: '#94A3B8',
      text: '#334155',
      hoverBg: '#FFFFFF',
      hoverBorder: '#E2E8F0',
      iconColor: '#1E3A5F',
      anchorIconColor: '#475569',
      buoyIconColor: '#0EA5E9',
      clumpIconColor: '#D97706',
      touchdown: '#DC2626',
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
    // F5.7.1 — para casos com arches no grounded (boia levantando o
    // cabo no meio da zona apoiada), `td > 0 && sx <= td` é insuficiente:
    // pontos no PICO do arco têm sx < td mas y_solver > seabed (não estão
    // apoiados). Detectamos grounded ponto-a-ponto por proximidade ao
    // seabed line (sy ≈ m·sx).
    const m = Math.tan(seabedSlopeRad)
    // Tolerância: 1% da water_depth ou 0.5m, o que for maior. Suficiente
    // pra discriminar pontos colados no seabed dos picos dos arches
    // (que tipicamente medem 0.5–5m em catenárias offshore reais).
    const yTol = Math.max(0.5, (waterDepth || 1) * 0.01)
    for (let i = 0; i < xs.length; i += 1) {
      const sx = xs[i]!
      const sy = ys[i]!
      plotX.push(Xtotal - sx)
      plotY.push(sy - waterDepth)
      tensions.push(ts[i]!)
      // F5.7.1 — `sy ≈ m·sx`: ponto está sobre a rampa (apoiado).
      // Para slope=0, isso é simplesmente `sy ≈ 0`. Substitui o teste
      // antigo `sx ≤ td` que era incorreto na presença de arches.
      const seabedYLocal = m * sx
      const isOnSeabedByY = Math.abs(sy - seabedYLocal) < yTol
      // Sanity: também precisa estar antes (ou aproximadamente em) do
      // touchdown principal — depois do main_td, o cabo entra no
      // suspended principal (não pode estar grounded). Para cases sem
      // touchdown (td=0), nenhum ponto está apoiado a menos que seja
      // laid line.
      const beforeMainTd = td > 0 && sx <= td + 1e-6
      onGround.push(
        allGrounded || (beforeMainTd && isOnSeabedByY),
      )
    }
    plotX.reverse()
    plotY.reverse()
    tensions.reverse()
    onGround.reverse()
    return { plotX, plotY, tensions, onGround }
  }, [xs, ys, ts, td, Xtotal, waterDepth, seabedSlopeRad, result.total_grounded_length, result.total_suspended_length])

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
    // Acumula em paralelo qual user-segment cada trace representa.
    // null para traces que não correspondem a nenhum segmento (água,
    // seabed, fairlead/âncora, attachments). Sincronizado com `traces`.
    const userIdxList: Array<number | null> = []
    const pushTrace = (t: Plotly.Data, uIdx: number | null = null) => {
      traces.push(t)
      userIdxList.push(uIdx)
    }

    // ── Faixa "água" (entre superfície y=0 e seabed y=-water_depth) ──
    pushTrace({
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
    pushTrace({
      type: 'scatter',
      mode: 'lines',
      x: [ranges.xRange[0], ranges.xRange[1]],
      y: [0, 0],
      line: { color: palette.surface, width: 1.5, dash: 'dash' },
      name: 'Superfície',
      hoverinfo: 'skip',
      showlegend: false,
    })

    // ── Seabed: linha (horizontal ou inclinada conforme slope) + faixa abaixo ──
    // No frame surface-relative do plot, anchor está em (Xtotal, -water_depth).
    // Seabed no frame anchor (solver): y_solver = m·x_solver. Conversão:
    //   plot_y_seabed(plot_x) = -water_depth + m·(Xtotal − plot_x)
    const m = Math.tan(seabedSlopeRad)
    function seabedY(plotX: number): number {
      return anchorY + m * (Xtotal - plotX)
    }
    const seabedXLo = ranges.xRange[0]!
    const seabedXHi = ranges.xRange[1]!
    const seabedYLo = seabedY(seabedXLo)
    const seabedYHi = seabedY(seabedXHi)
    pushTrace({
      type: 'scatter',
      mode: 'lines',
      x: [seabedXLo, seabedXHi, seabedXHi, seabedXLo],
      y: [seabedYLo, seabedYHi, ranges.yRange[0], ranges.yRange[0]],
      fill: 'toself',
      fillcolor: palette.seabedFill,
      line: { width: 0 },
      hoverinfo: 'skip',
      showlegend: false,
    })
    pushTrace({
      type: 'scatter',
      mode: 'lines',
      x: [seabedXLo, seabedXHi],
      y: [seabedYLo, seabedYHi],
      line: { color: palette.seabed, width: 2 },
      name:
        Math.abs(seabedSlopeRad) > 1e-4
          ? `Seabed (${((seabedSlopeRad * 180) / Math.PI).toFixed(1)}°)`
          : 'Seabed',
      hoverinfo: 'skip',
      showlegend: false,
    })

    // ── Linha de mergulho do fairlead (vertical da superfície ao fairlead) ──
    if (startpointDepth > 0.5) {
      pushTrace({
        type: 'scatter',
        mode: 'lines',
        x: [0, 0],
        y: [0, fairleadY],
        line: { color: palette.fairlead, width: 1, dash: 'dot' },
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    // ── Trechos da linha ──
    // Com multi-segmento (F5.1, segment_boundaries com mais de 2 entradas),
    // colorimos por segmento. Caso contrário, mantemos split suspenso vs
    // apoiado (single-segmento ou laid line).
    const segBounds = result.segment_boundaries ?? []
    const isMulti = segBounds.length > 2

    if (isMulti) {
      // Boundaries vêm do solver em frame anchor-first. Após o reverse() em
      // `curve`, índices ficam fairlead-first → remappeamos.
      const N = curve.plotX.length
      const segPalette = theme === 'dark'
        ? ['#60A5FA', '#FBBF24', '#34D399', '#A78BFA', '#F472B6']
        : ['#1E3A5F', '#D97706', '#047857', '#7C3AED', '#BE185D']

      // Quando o resolver divide segmentos por causa de attachments
      // mid-segment, segBounds tem MAIS entradas do que `segments`
      // (input do usuário). buildPostSplitStructure replica a lógica
      // do resolver e devolve `userIdxOf[k]` (mapeia sub-segmento k
      // ao segmento original) e `attachmentJunctionIdx[i]` (junção
      // da pós-estrutura onde o attachment i está).
      const { userIdxOf } = buildPostSplitStructure(
        (segments ?? []).map((s) => ({
          length: (s as { length?: number }).length,
        })),
        (attachments ?? []).map((a) => ({
          position_index: a.position_index,
          position_s_from_anchor: (a as { position_s_from_anchor?: number | null })
            .position_s_from_anchor,
        })),
      )

      for (let s = 0; s < segBounds.length - 1; s += 1) {
        const startA = segBounds[s]!
        const endA = segBounds[s + 1]!
        // mapeia para fairlead-first
        const startF = N - 1 - endA
        const endF = N - 1 - startA
        const sx = curve.plotX.slice(startF, endF + 1)
        const sy = curve.plotY.slice(startF, endF + 1)
        const st = curve.tensions.slice(startF, endF + 1)
        // userIdxOf é anchor-first; s itera anchor-first; mapeamento direto.
        // Fallback `s % segments.length` se o tamanho não bate (defesa
        // contra divergência entre input e result em cases legados).
        const userIdx =
          userIdxOf.length > s
            ? userIdxOf[s]!
            : s % Math.max(1, (segments ?? []).length)
        const meta = (segments ?? [])[userIdx]
        const catStyle =
          (meta?.category && CATEGORY_STYLE[meta.category]) ||
          { dash: 'solid', width: 3.5, label: 'Cabo' }
        const labelParts = [`Seg ${userIdx + 1}`]
        if (meta?.line_type) labelParts.push(meta.line_type)
        if (meta?.category && CATEGORY_STYLE[meta.category]) {
          labelParts.push(CATEGORY_STYLE[meta.category]!.label)
        }
        const traceName = labelParts.join(' · ')
        // Hover highlight: este segmento "acende" (largura ↑) quando é
        // o user-segment hovereado; outros user-segments ficam dimmed
        // (opacity ↓) pra criar contraste e direcionar o foco.
        const isHovered = hoveredUserIdx === userIdx
        const isOther = hoveredUserIdx != null && hoveredUserIdx !== userIdx
        pushTrace({
          type: 'scatter',
          mode: 'lines',
          x: sx,
          y: sy,
          line: {
            color: segPalette[userIdx % segPalette.length]!,
            width: isHovered ? catStyle.width * 1.7 : catStyle.width,
            dash: catStyle.dash,
          },
          opacity: isOther ? 0.3 : 1,
          name: traceName,
          text: st.map((t) => `|T| = ${(t / 1000).toFixed(1)} kN`),
          showlegend: false, // legenda HTML dedupa por user-segment
          hovertemplate:
            `${traceName}<br>x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>`,
        }, userIdx)
      }

      // Overlay do trecho apoiado em vermelho (sobrepõe a cor do
      // segmento na porção que está em contato com o seabed). Drawn
      // depois dos traces dos segmentos para ficar por cima na ordem
      // de empilhamento. Sem touchdown, onGround é tudo false e nada
      // é renderizado.
      //
      // F5.7.1 — quando o trecho apoiado tem GAPS (e.g., um arco de
      // boia no meio que levanta o cabo), inserimos `null` entre as
      // zonas para que Plotly QUEBRE a linha. Sem isso, plotly
      // conecta as zonas com uma reta horizontal por baixo do arco,
      // criando um overlay vermelho falso embaixo da seção lifted.
      const gXm: (number | null)[] = []
      const gYm: (number | null)[] = []
      const gTm: (number | null)[] = []
      let prevWasGrounded = false
      for (let i = 0; i < curve.plotX.length; i += 1) {
        if (curve.onGround[i]) {
          gXm.push(curve.plotX[i]!)
          gYm.push(curve.plotY[i]!)
          gTm.push(curve.tensions[i]!)
          prevWasGrounded = true
        } else if (prevWasGrounded) {
          // Saiu da zona apoiada — insere null pra quebrar a linha
          gXm.push(null)
          gYm.push(null)
          gTm.push(null)
          prevWasGrounded = false
        }
      }
      if (gXm.length > 0) {
        // Overlay do trecho apoiado: dimmed quando outro segmento está
        // sendo hovereado pra não competir com o destaque do segmento.
        pushTrace({
          type: 'scatter',
          mode: 'lines',
          x: gXm,
          y: gYm,
          line: { color: palette.grounded, width: 4 },
          opacity: hoveredUserIdx != null ? 0.5 : 1,
          connectgaps: false,
          name: 'Trecho apoiado',
          text: gTm.map((t) =>
            t == null ? '' : `|T| = ${(t / 1000).toFixed(1)} kN`,
          ),
          hovertemplate:
            'Apoiado<br>x = %{x:.2f} m<br>y = %{y:.2f} m<br>%{text}<extra></extra>',
        })
      }
    } else {
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
      if (suspendedX.length > 0 && groundedX.length > 0) {
        suspendedX.push(groundedX[0]!)
        suspendedY.push(groundedY[0]!)
        suspendedT.push(groundedT[0]!)
      }
      if (suspendedX.length > 0) {
        pushTrace({
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
        pushTrace({
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
    }

    // ── Hover invisível em fairlead/âncora ──
    // Os ícones SVG ficam por cima via layout.images. Aqui só deixamos
    // markers transparentes para o hover funcionar (Plotly não captura
    // hover em images). showlegend=false: a legenda usa os SVGs num
    // componente HTML separado, não os markers Plotly.
    pushTrace({
      type: 'scatter',
      mode: 'markers',
      x: [0],
      y: [fairleadY],
      marker: { size: 22, color: 'rgba(0,0,0,0)' },
      name: 'Fairlead',
      showlegend: false,
      hovertemplate:
        `Fairlead<br>x = 0<br>y = ${fairleadY.toFixed(2)} m<br>` +
        `T_fl = ${(result.fairlead_tension / 1000).toFixed(1)} kN<extra></extra>`,
    })
    pushTrace({
      type: 'scatter',
      mode: 'markers',
      x: [Xtotal],
      y: [anchorY],
      marker: { size: 22, color: 'rgba(0,0,0,0)' },
      name: 'Âncora',
      showlegend: false,
      hovertemplate:
        `Âncora<br>x = ${Xtotal.toFixed(2)} m<br>y = ${anchorY.toFixed(2)} m<br>` +
        `T_anc = ${(result.anchor_tension / 1000).toFixed(1)} kN<extra></extra>`,
    })

    // ── Hover invisível em attachments (boias e clumps, F5.2) ──
    // Posições computadas aqui; ícones SVG são adicionados via layout.images
    // (mesmo esquema da âncora/fairlead) para terem aparência gráfica
    // consistente. Plotly não captura hover em images, então deixamos
    // markers transparentes no mesmo ponto.
    if (attachments.length > 0 && segBounds.length >= 2) {
      const N = curve.plotX.length
      // F5.6.7 — usa a estrutura pós-split do resolver para localizar
      // attachments PRECISAMENTE em segBounds. Cada attachment com
      // `position_s_from_anchor` cria um split que vira uma junção
      // exata em segment_boundaries — mapeamos via essa junção em vez
      // de aproximação proporcional (que era imprecisa quando segmentos
      // tinham densidades de sampling diferentes).
      const { attachmentJunctionIdx: attJunctions } = buildPostSplitStructure(
        (segments ?? []).map((s) => ({
          length: (s as { length?: number }).length,
        })),
        attachments.map((a) => ({
          position_index: a.position_index,
          position_s_from_anchor: (a as { position_s_from_anchor?: number | null })
            .position_s_from_anchor,
        })),
      )
      const buoyX: number[] = []
      const buoyY: number[] = []
      const buoyText: string[] = []
      const clumpX: number[] = []
      const clumpY: number[] = []
      const clumpText: string[] = []
      for (let i = 0; i < attachments.length; i += 1) {
        const att = attachments[i]!
        let idxPlot: number | null = null
        if (att.position_index != null) {
          // Modo legacy: junção pré-existente. position_index aqui já é
          // o índice da junção em segments do INPUT — usamos o
          // attachmentJunctionIdx para obter a junção pós-resolver
          // equivalente.
          const junction = attJunctions[i]
          if (junction != null && junction < segBounds.length) {
            const idxAnchorFrame = segBounds[junction]!
            idxPlot = N - 1 - idxAnchorFrame
          }
        } else if (att.position_s_from_anchor != null) {
          // Modo distância (F5.4.6a): a junção foi criada pelo split
          // EXATAMENTE nessa posição.
          const junction = attJunctions[i]
          if (junction != null && junction < segBounds.length) {
            const idxAnchorFrame = segBounds[junction]!
            idxPlot = N - 1 - idxAnchorFrame
          }
        }
        if (idxPlot == null) continue
        const px = curve.plotX[idxPlot]
        const py = curve.plotY[idxPlot]
        if (px == null || py == null) continue
        // F5.6.7 — Tether (pendant): boia fica deslocada PARA CIMA
        // da linha pelo comprimento do pendant; clump fica DESCIDO.
        // Hover marker fica na posição do CORPO (não do ponto de
        // conexão) para o tooltip aparecer onde o ícone está.
        const tetherLen =
          (att as { tether_length?: number | null }).tether_length ?? 0
        const dy =
          tetherLen > 0
            ? (att.kind === 'buoy' ? +tetherLen : -tetherLen)
            : 0
        const bodyY = py + dy
        const label = att.name
          ? `${att.name} (${(att.submerged_force / 1000).toFixed(1)} kN)` +
            (tetherLen > 0 ? ` · pendant ${tetherLen.toFixed(1)} m` : '')
          : `${att.kind === 'buoy' ? 'Boia' : 'Clump'} ` +
            `(${(att.submerged_force / 1000).toFixed(1)} kN)` +
            (tetherLen > 0 ? ` · pendant ${tetherLen.toFixed(1)} m` : '')
        if (att.kind === 'buoy') {
          buoyX.push(px)
          buoyY.push(bodyY)
          buoyText.push(label)
        } else {
          clumpX.push(px)
          clumpY.push(bodyY)
          clumpText.push(label)
        }
        // Linha do pendant (cabo de conexão) — só desenhada quando
        // tether_length > 0; conecta o ponto na linha ao corpo.
        if (tetherLen > 0) {
          pushTrace({
            type: 'scatter',
            mode: 'lines',
            x: [px, px],
            y: [py, bodyY],
            line: {
              color:
                att.kind === 'buoy'
                  ? palette.buoyIconColor
                  : palette.clumpIconColor,
              width: 1.2,
              dash: 'dot',
            },
            showlegend: false,
            hoverinfo: 'skip',
          })
        }
      }
      if (buoyX.length > 0) {
        pushTrace({
          type: 'scatter',
          mode: 'markers',
          x: buoyX,
          y: buoyY,
          marker: { size: 22, color: 'rgba(0,0,0,0)' },
          name: 'Boia',
          text: buoyText,
          showlegend: false,
          hovertemplate: '%{text}<br>x = %{x:.2f} m<br>y = %{y:.2f} m<extra></extra>',
        })
      }
      if (clumpX.length > 0) {
        pushTrace({
          type: 'scatter',
          mode: 'markers',
          x: clumpX,
          y: clumpY,
          marker: { size: 22, color: 'rgba(0,0,0,0)' },
          name: 'Clump weight',
          text: clumpText,
          showlegend: false,
          hovertemplate: '%{text}<br>x = %{x:.2f} m<br>y = %{y:.2f} m<extra></extra>',
        })
      }
    }

    // ── Markers de touchdown (todos os pontos de transição) ──
    // F5.7.5 — com arches no grounded, há MÚLTIPLOS touchdowns: o
    // touchdown principal vindo do fairlead + 2 touchdowns por arco
    // (um em cada extremidade onde o cabo descola/encosta no seabed).
    // Detecta percorrendo onGround[]: cada transição true↔false é um
    // touchdown. Mantém o `td` (dist_to_first_td) como auxiliar para
    // o caso single-grounded sem arches (compat).
    const tdMarkersX: number[] = []
    const tdMarkersY: number[] = []
    for (let i = 1; i < curve.onGround.length; i += 1) {
      if (curve.onGround[i] !== curve.onGround[i - 1]) {
        // Transição — usa o ponto que está NO seabed (on-ground side)
        // pra garantir que o marker fique exatamente em y=seabed.
        const groundIdx = curve.onGround[i] ? i : i - 1
        tdMarkersX.push(curve.plotX[groundIdx]!)
        tdMarkersY.push(curve.plotY[groundIdx]!)
      }
    }
    // Fallback: se não detectou nenhum mas td>0 está no result (single
    // grounded sem arches em sampling esparso), usa o ponto canônico.
    if (tdMarkersX.length === 0 && td > 0.5) {
      const tdPlotX = Xtotal - td
      tdMarkersX.push(tdPlotX)
      tdMarkersY.push(seabedY(tdPlotX))
    }
    if (tdMarkersX.length > 0) {
      pushTrace({
        type: 'scatter',
        mode: 'markers',
        x: tdMarkersX,
        y: tdMarkersY,
        marker: {
          symbol: 'diamond',
          size: 11,
          color: palette.touchdown,
          line: { color: '#FFFFFF', width: 1.5 },
        },
        name: 'Touchdown',
        hovertemplate:
          'Touchdown<br>x = %{x:.2f} m<br>y = %{y:.2f} m<extra></extra>',
      })
    }

    // Persiste o map traceIdx → userIdx pro handler onHover do Plotly.
    // O ref é lido do callback onHover (estável), enquanto o data fica
    // no rendering do Plot (passado por value). Mantemos os dois em sync
    // ao escrever aqui no mesmo ciclo do useMemo.
    traceUserIdxRef.current = userIdxList
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
    result.segment_boundaries,
    attachments,
    seabedSlopeRad,
    segments,
    theme,
    hoveredUserIdx,
  ])

  // ── Imagens SVG sobrepostas (fairlead + âncora + attachments) ──
  // Tamanho **fixo em pixels** na tela: medimos o canvas via ResizeObserver
  // e convertemos targetPx → unidades de dado usando os ranges atuais.
  // Assim ancor/fairlead aparecem com o mesmo tamanho visual seja qual
  // for o range horizontal (linha curta ou longa).
  const images = useMemo(() => {
    // Margens (devem casar com layout.margin abaixo).
    const margin = { t: 18, r: 24, b: 48, l: 64 }
    // Fallback enquanto o ResizeObserver não disparou (primeira render).
    const containerW = plotPx?.w ?? 800
    const containerH = plotPx?.h ?? 480
    const plotW = Math.max(containerW - margin.l - margin.r, 80)
    const plotH = Math.max(containerH - margin.t - margin.b, 80)

    const xSpan = ranges.xRange[1]! - ranges.xRange[0]!
    const ySpan = ranges.yRange[1]! - ranges.yRange[0]!
    // Tamanho-alvo em pixels; calculamos sizex/sizey em unidades de dado
    // tais que o ícone meça `targetPx` em cada eixo na tela. Como xSpan
    // e ySpan podem ter aspect ratio bem diferente, calcular separado
    // mantém o ícone visualmente quadrado (não distorcido).
    const fairleadTargetPx = 32
    const attTargetPx = 24 // ~75% do ícone principal
    const fxData = (fairleadTargetPx / plotW) * xSpan
    const fyData = (fairleadTargetPx / plotH) * ySpan
    const axData = (attTargetPx / plotW) * xSpan
    const ayData = (attTargetPx / plotH) * ySpan

    const imgs: Record<string, unknown>[] = [
      {
        source: svgDataUri(fairleadSvg(palette.iconColor)),
        xref: 'x',
        yref: 'y',
        x: 0,
        y: fairleadY,
        sizex: fxData,
        sizey: fyData,
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
        sizex: fxData,
        sizey: fyData,
        xanchor: 'center',
        yanchor: 'middle',
        layer: 'above',
      },
    ]

    const segBounds = result.segment_boundaries ?? []
    if (attachments.length > 0 && segBounds.length >= 2) {
      const N = curve.plotX.length
      const { attachmentJunctionIdx: attJunctionsImg } =
        buildPostSplitStructure(
          (segments ?? []).map((s) => ({
            length: (s as { length?: number }).length,
          })),
          attachments.map((a) => ({
            position_index: a.position_index,
            position_s_from_anchor: (a as {
              position_s_from_anchor?: number | null
            }).position_s_from_anchor,
          })),
        )
      for (let i = 0; i < attachments.length; i += 1) {
        const att = attachments[i]!
        const junction = attJunctionsImg[i]
        if (junction == null || junction >= segBounds.length) continue
        const idxAnchorFrame = segBounds[junction]!
        const idxPlot = N - 1 - idxAnchorFrame
        const px = curve.plotX[idxPlot]
        const py = curve.plotY[idxPlot]
        if (px == null || py == null) continue
        // F5.6.7 — Tether (pendant) opcional. Quando informado,
        // desloca o ícone do corpo VERTICALMENTE pelo comprimento
        // do pendant: boia sobe (em direção à superfície), clump
        // desce (em direção ao seabed). Linha principal continua
        // no ponto de conexão; só o ícone do corpo é deslocado.
        const tetherLen =
          (att as { tether_length?: number | null }).tether_length ?? 0
        const dy =
          tetherLen > 0
            ? (att.kind === 'buoy' ? +tetherLen : -tetherLen)
            : 0
        const iconY = py + dy
        const svg =
          att.kind === 'buoy'
            ? buoySvg(palette.buoyIconColor)
            : clumpSvg(palette.clumpIconColor)
        imgs.push({
          source: svgDataUri(svg),
          xref: 'x',
          yref: 'y',
          x: px,
          y: iconY,
          sizex: axData,
          sizey: ayData,
          xanchor: 'center',
          yanchor: 'middle',
          layer: 'above',
        })
      }
    }
    return imgs
  }, [
    ranges,
    palette,
    fairleadY,
    anchorY,
    Xtotal,
    attachments,
    curve,
    result.segment_boundaries,
    plotPx,
  ])

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
      // Legenda Plotly desabilitada — usamos legenda HTML customizada por
      // cima (ver <CatenaryLegend /> abaixo). Permite usar SVGs inline para
      // fairlead/âncora, o que não é possível na legenda nativa do Plotly.
      showlegend: false,
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

  // Hover do Plotly: pega o curveNumber do trace sob o mouse e mapeia
  // pelo ref pra encontrar o user-segment correspondente. Set apenas
  // se realmente é um trace de segmento (userIdx != null) — passar o
  // mouse pelo overlay grounded ou markers de attachment não dispara
  // highlight de segmento.
  const handlePlotHover = useCallback(
    (e: { points?: Array<{ curveNumber?: number }> }) => {
      const cn = e.points?.[0]?.curveNumber
      if (cn == null) return
      const idx = traceUserIdxRef.current[cn]
      if (idx != null) setHoveredUserIdx(idx)
    },
    [],
  )
  const handlePlotUnhover = useCallback(() => {
    setHoveredUserIdx(null)
  }, [])

  // Composição da legenda HTML: detecta quais traces da linha aparecem
  // no plot atual. SVGs de fairlead e âncora estão sempre presentes
  // (ícones via layout.images). Touchdown só quando td > 0.5.
  const legendItems = useMemo<LegendItem[]>(() => {
    const items: LegendItem[] = []
    const segBounds = result.segment_boundaries ?? []
    const isMulti = segBounds.length > 2
    const hasGrounded = (result.total_grounded_length ?? 0) > 0
    const hasSuspended = (result.total_suspended_length ?? 0) > 0
    const hasTouchdown = (result.dist_to_first_td ?? 0) > 0.5
    const hasBuoy = attachments.some((a) => a.kind === 'buoy')
    const hasClump = attachments.some((a) => a.kind === 'clump_weight')

    if (isMulti) {
      const segPaletteLight = ['#1E3A5F', '#D97706', '#047857', '#7C3AED', '#BE185D']
      const segPaletteDark = ['#60A5FA', '#FBBF24', '#34D399', '#A78BFA', '#F472B6']
      const segPalette = theme === 'dark' ? segPaletteDark : segPaletteLight
      // Legenda mostra UM chip por segmento criado pelo usuário (não
      // por sub-segmento gerado pelo resolver de attachments). Itera
      // sobre `segments` (input do form), não sobre `segBounds`.
      const userSegCount = (segments ?? []).length || 1
      for (let k = 0; k < userSegCount; k += 1) {
        const meta = segments[k]
        const catStyle =
          (meta?.category && CATEGORY_STYLE[meta.category]) ||
          { dash: 'solid', width: 3.5, label: 'Cabo' }
        const labelParts = [`Seg ${k + 1}`]
        if (meta?.line_type) labelParts.push(meta.line_type)
        else if (meta?.category && CATEGORY_STYLE[meta.category]) {
          labelParts.push(CATEGORY_STYLE[meta.category]!.label)
        }
        items.push({
          kind: 'line',
          color: segPalette[k % segPalette.length]!,
          label: labelParts.join(' · '),
          dash: catStyle.dash,
          width: catStyle.width,
          userIdx: k,
        })
      }
      // Mesmo em multi-segmento, mostra o chip "Trecho apoiado" quando
      // há touchdown — explica o overlay vermelho que aparece sobre as
      // cores dos segmentos no trecho que está em contato com o seabed.
      if (hasGrounded) {
        items.push({
          kind: 'line',
          color: palette.grounded,
          label: 'Trecho apoiado',
          width: 4,
        })
      }
    } else {
      if (hasSuspended) {
        items.push({ kind: 'line', color: palette.suspended, label: 'Trecho suspenso' })
      }
      if (hasGrounded) {
        items.push({ kind: 'line', color: palette.grounded, label: 'Trecho apoiado' })
      }
    }
    items.push({
      kind: 'svg',
      svg: fairleadSvg(palette.iconColor),
      label: 'Fairlead',
    })
    items.push({
      kind: 'svg',
      svg: anchorSvg(palette.anchorIconColor),
      label: 'Âncora',
    })
    if (hasBuoy) {
      items.push({
        kind: 'svg',
        svg: buoySvg(palette.buoyIconColor),
        label: 'Boia',
      })
    }
    if (hasClump) {
      items.push({
        kind: 'svg',
        svg: clumpSvg(palette.clumpIconColor),
        label: 'Clump weight',
      })
    }
    if (hasTouchdown) {
      items.push({
        kind: 'diamond',
        color: palette.touchdown,
        label: 'Touchdown',
      })
    }
    return items
  }, [result, palette, theme, attachments, segments])

  // F5.7.3 — banner de aviso quando há boias acima da superfície.
  // Solver detecta no post-process e expõe em result.surface_violations.
  const surfaceViolations =
    (result as unknown as {
      surface_violations?: Array<{
        index: number
        name: string
        height_above_surface_m: number
      }>
    }).surface_violations ?? []

  return (
    <div ref={plotContainerRef} className="relative h-full w-full">
      {/* Legenda HTML flutuante no topo do plot, com SVGs inline para
          fairlead e âncora — algo que a legenda nativa do Plotly não suporta. */}
      <div className="pointer-events-none absolute inset-x-0 top-1 z-10 flex justify-center px-2">
        <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3 rounded-md border border-border/40 bg-background/70 px-3 py-1 text-[11px] backdrop-blur-sm">
          {legendItems.map((item, i) => (
            <LegendChip
              key={i}
              item={item}
              hoveredUserIdx={hoveredUserIdx}
              onHoverChange={setHoveredUserIdx}
            />
          ))}
        </div>
      </div>
      {/* Banner de aviso de boia voadora — sobreposto ao topo do plot,
          abaixo da legenda. Cor amarelo/âmbar (warning, não error). */}
      {surfaceViolations.length > 0 && (
        <div className="pointer-events-none absolute inset-x-0 top-9 z-10 flex justify-center px-2">
          <div className="pointer-events-auto max-w-[90%] rounded-md border border-amber-500/50 bg-amber-500/15 px-3 py-1.5 text-[11px] text-amber-200 backdrop-blur-sm shadow-lg">
            <span className="font-semibold">
              ⚠ {surfaceViolations.length === 1 ? 'Boia' : 'Boias'} acima da
              superfície:
            </span>{' '}
            {surfaceViolations
              .map(
                (v) =>
                  `${v.name} (+${v.height_above_surface_m.toFixed(1)} m)`,
              )
              .join(', ')}
            . Boias reais não flutuam acima da água — reduza o empuxo,
            aumente T_fl ou compense com clump.
          </div>
        </div>
      )}
      <Suspense fallback={<Skeleton style={plotStyle} />}>
        <Plot
          data={data}
          layout={layout}
          config={config}
          style={plotStyle}
          useResizeHandler
          onHover={handlePlotHover}
          onUnhover={handlePlotUnhover}
        />
      </Suspense>
    </div>
  )
}

interface LegendItem {
  kind: 'line' | 'svg' | 'diamond'
  label: string
  color?: string
  svg?: string
  dash?: string
  width?: number
  /**
   * Para chips de segmento da linha (multi-seg): permite hover highlight
   * bidirecional com o trace correspondente. `null` para chips estáticos
   * (fairlead, âncora, touchdown, etc).
   */
  userIdx?: number
}

function LegendChip({
  item,
  hoveredUserIdx,
  onHoverChange,
}: {
  item: LegendItem
  hoveredUserIdx: number | null
  onHoverChange: (idx: number | null) => void
}) {
  const isInteractive = item.userIdx != null
  const isActive = isInteractive && hoveredUserIdx === item.userIdx
  const isDimmed =
    isInteractive && hoveredUserIdx != null && hoveredUserIdx !== item.userIdx
  return (
    <span
      onMouseEnter={isInteractive ? () => onHoverChange(item.userIdx!) : undefined}
      onMouseLeave={isInteractive ? () => onHoverChange(null) : undefined}
      className={`flex items-center gap-1.5 transition-opacity ${
        isInteractive ? 'cursor-pointer' : ''
      } ${isDimmed ? 'opacity-40' : ''} ${isActive ? 'font-semibold' : ''}`}
    >
      {item.kind === 'line' && (
        <LegendLineSwatch
          color={item.color ?? 'currentColor'}
          dash={item.dash ?? 'solid'}
          width={isActive ? (item.width ?? 3) * 1.4 : item.width ?? 3}
        />
      )}
      {item.kind === 'diamond' && (
        <span
          className="inline-block h-2.5 w-2.5 rotate-45 rounded-[1px] border border-white"
          style={{ backgroundColor: item.color }}
        />
      )}
      {item.kind === 'svg' && item.svg && (
        <span
          className="inline-block h-4 w-4"
          dangerouslySetInnerHTML={{ __html: item.svg }}
        />
      )}
      <span className="text-foreground">{item.label}</span>
    </span>
  )
}

/**
 * Mostra um traço com dash/largura sincronizados ao trace Plotly. Usa
 * SVG inline (em vez de border-style) porque CSS não tem dotted/dashed
 * que case com os nomes do Plotly ('dash', 'dot') de forma idêntica.
 */
function LegendLineSwatch({
  color,
  dash,
  width,
}: {
  color: string
  dash: string
  width: number
}) {
  // Mapeia dash strings do Plotly (solid|dash|dot|dashdot) para
  // stroke-dasharray do SVG. Ajustado para um swatch de 22px de largura.
  const dasharray =
    dash === 'dash' ? '5 3' : dash === 'dot' ? '1.5 2.5' : dash === 'dashdot' ? '5 2 1 2' : undefined
  // Largura visual reduzida (Plotly width 5 → ~3px no swatch).
  const strokeW = Math.max(1.5, Math.min(width * 0.65, 4))
  return (
    <svg
      width={22}
      height={6}
      viewBox="0 0 22 6"
      className="inline-block shrink-0"
      aria-hidden
    >
      <line
        x1={1}
        y1={3}
        x2={21}
        y2={3}
        stroke={color}
        strokeWidth={strokeW}
        strokeDasharray={dasharray}
        strokeLinecap="round"
      />
    </svg>
  )
}
