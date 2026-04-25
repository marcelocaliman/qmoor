import type { MooringLineResult, MooringSystemResult } from '@/api/types'

export interface MooringSystemPlanViewProps {
  /**
   * Resultado do solver multi-linha. Quando ausente, o componente
   * desenha só a plataforma e os fairleads, usando os parâmetros
   * informados em `previewLines` (modo edição).
   */
  result?: MooringSystemResult
  platformRadius: number
  /**
   * Quando `result` está ausente (ex.: linha em edição que ainda não
   * foi resolvida), permite renderizar a plataforma + fairleads a
   * partir dos azimuths/raios sem dados de solver.
   */
  previewLines?: Array<{
    name: string
    fairlead_azimuth_deg: number
    fairlead_radius: number
  }>
  className?: string
}

/**
 * Plan view (visão de topo) de um mooring system. Renderiza:
 *   - Plataforma como círculo no centro (raio = platform_radius).
 *   - Cada linha como segmento radial do fairlead até a âncora,
 *     colorido pelo `alert_level` da linha.
 *   - Vetor da força resultante agregada (quando há resultado).
 *   - Rosa-dos-ventos cardinal: N (proa, +X), L, S, O.
 *
 * Coordenadas mostradas no frame do casco (origem no centro). Eixo X+
 * para proa (N na rosa-dos-ventos). SVG tem Y invertido em CSS, então
 * mapeamos plot_y → -svg_y para que +Y aponte para cima.
 */
export function MooringSystemPlanView({
  result,
  platformRadius,
  previewLines,
  className,
}: MooringSystemPlanViewProps) {
  const lines = result?.lines ?? []

  // Calcula o raio máximo: maior distância de qualquer ponto desenhado
  // até a origem. Se não há linhas no resultado, usa o radius dos
  // previewLines + 200 m de fallback (linha sai mas não temos X ainda).
  let maxRadius = platformRadius
  for (const lr of lines) {
    const r = Math.max(
      Math.hypot(...lr.anchor_xy),
      Math.hypot(...lr.fairlead_xy),
    )
    if (r > maxRadius) maxRadius = r
  }
  if (lines.length === 0 && previewLines && previewLines.length > 0) {
    const maxFR = Math.max(...previewLines.map((p) => p.fairlead_radius))
    // Fallback: 4× raio do fairlead aproxima X ~ 3-5 vezes o raio numa
    // catenária típica em águas médias-rasas. Só pra preview.
    maxRadius = Math.max(maxRadius, maxFR * 4)
  }
  // padding visual: 10% de folga
  const span = maxRadius * 1.15

  // Viewbox quadrada centrada na origem
  const VB = 1000
  const cx = VB / 2
  const cy = VB / 2
  const scale = (VB / 2) / span // unidades dado → SVG units

  function toSvg(x: number, y: number): [number, number] {
    return [cx + x * scale, cy - y * scale]
  }

  return (
    <svg
      viewBox={`0 0 ${VB} ${VB}`}
      preserveAspectRatio="xMidYMid meet"
      className={className}
      style={{ width: '100%', height: '100%' }}
      aria-label="Plan view do mooring system"
    >
      {/* ── Anéis de referência ── */}
      <defs>
        <pattern
          id="msys-grid"
          width={VB / 10}
          height={VB / 10}
          patternUnits="userSpaceOnUse"
        >
          <path
            d={`M ${VB / 10} 0 L 0 0 0 ${VB / 10}`}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.06}
            strokeWidth={1}
          />
        </pattern>
      </defs>
      <rect width={VB} height={VB} fill="url(#msys-grid)" />

      {/* Anéis radiais (3, 6, 9 décimos do span) */}
      {[0.33, 0.66, 1.0].map((frac) => (
        <circle
          key={frac}
          cx={cx}
          cy={cy}
          r={(VB / 2) * frac * 0.95}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.12}
          strokeWidth={1}
          strokeDasharray="4 4"
        />
      ))}

      {/* Eixos cardinais (N=+X, L=+Y, S=-X, O=-Y; convenção do casco) */}
      <line
        x1={cx - VB / 2 + 8}
        y1={cy}
        x2={cx + VB / 2 - 8}
        y2={cy}
        stroke="currentColor"
        strokeOpacity={0.18}
        strokeWidth={1}
      />
      <line
        x1={cx}
        y1={cy - VB / 2 + 8}
        x2={cx}
        y2={cy + VB / 2 - 8}
        stroke="currentColor"
        strokeOpacity={0.18}
        strokeWidth={1}
      />
      <text x={cx + VB / 2 - 12} y={cy - 6} textAnchor="end" className="msys-axis">
        +X (proa)
      </text>
      <text x={cx + 6} y={cy - VB / 2 + 16} className="msys-axis">
        +Y (BB)
      </text>

      {/* ── Plataforma ── */}
      <circle
        cx={cx}
        cy={cy}
        r={platformRadius * scale}
        fill="currentColor"
        fillOpacity={0.08}
        stroke="currentColor"
        strokeOpacity={0.5}
        strokeWidth={1.5}
      />
      {/* Marca da proa */}
      <polygon
        points={`${cx + platformRadius * scale},${cy} ${cx + platformRadius * scale - 12},${cy - 6} ${cx + platformRadius * scale - 12},${cy + 6}`}
        fill="currentColor"
        fillOpacity={0.6}
      />

      {/* ── Linhas (se houver resultado) ── */}
      {lines.map((lr, i) => (
        <LineSegment key={i} lineResult={lr} toSvg={toSvg} />
      ))}

      {/* ── Linhas em modo preview (sem resultado) ── */}
      {lines.length === 0 &&
        previewLines &&
        previewLines.map((p, i) => {
          const theta = (p.fairlead_azimuth_deg * Math.PI) / 180
          const fx = p.fairlead_radius * Math.cos(theta)
          const fy = p.fairlead_radius * Math.sin(theta)
          // Anchor estimado: 4× raio (placeholder até resolver)
          const ar = p.fairlead_radius * 4
          const ax = ar * Math.cos(theta)
          const ay = ar * Math.sin(theta)
          const [fSvgX, fSvgY] = toSvg(fx, fy)
          const [aSvgX, aSvgY] = toSvg(ax, ay)
          return (
            <g key={i}>
              <line
                x1={fSvgX}
                y1={fSvgY}
                x2={aSvgX}
                y2={aSvgY}
                stroke="currentColor"
                strokeOpacity={0.4}
                strokeWidth={2}
                strokeDasharray="6 4"
              />
              <circle
                cx={fSvgX}
                cy={fSvgY}
                r={4}
                fill="currentColor"
                fillOpacity={0.6}
              />
              <text
                x={(fSvgX + aSvgX) / 2}
                y={(fSvgY + aSvgY) / 2 - 6}
                textAnchor="middle"
                className="msys-line-label"
              >
                {p.name}
              </text>
            </g>
          )
        })}

      {/* ── Vetor da força resultante (quando agregado é não-trivial) ── */}
      {result && result.aggregate_force_magnitude > 0 && (
        <ResultantArrow
          force_xy={result.aggregate_force_xy}
          maxRadius={maxRadius}
          toSvg={toSvg}
        />
      )}

      {/* Indicador "centro" */}
      <circle cx={cx} cy={cy} r={2.5} fill="currentColor" fillOpacity={0.9} />

      <style>{`
        .msys-axis {
          fill: currentColor;
          fill-opacity: 0.5;
          font-size: 11px;
          font-family: ui-sans-serif, system-ui, sans-serif;
        }
        .msys-line-label {
          fill: currentColor;
          fill-opacity: 0.85;
          font-size: 11px;
          font-family: ui-sans-serif, system-ui, sans-serif;
          font-weight: 500;
        }
      `}</style>
    </svg>
  )
}

// Cores por alert_level — alinhadas com StatusBadge.
const ALERT_COLOR: Record<string, string> = {
  ok: '#10B981',       // emerald
  yellow: '#F59E0B',   // amber
  red: '#EF4444',      // red
  broken: '#7F1D1D',   // dark red
}

function LineSegment({
  lineResult,
  toSvg,
}: {
  lineResult: MooringLineResult
  toSvg: (x: number, y: number) => [number, number]
}) {
  const sr = lineResult.solver_result
  const isInvalid = sr.status !== 'converged'
  const color = isInvalid
    ? '#9CA3AF' // cinza para linhas que não convergiram
    : ALERT_COLOR[sr.alert_level ?? 'ok']

  const [fSvgX, fSvgY] = toSvg(...lineResult.fairlead_xy)
  const [aSvgX, aSvgY] = toSvg(...lineResult.anchor_xy)
  // Posição do label: 60% do caminho do fairlead até o anchor (mais perto
  // do anchor onde costuma ter menos sobreposição).
  const lx = fSvgX + 0.6 * (aSvgX - fSvgX)
  const ly = fSvgY + 0.6 * (aSvgY - fSvgY)

  return (
    <g>
      <line
        x1={fSvgX}
        y1={fSvgY}
        x2={aSvgX}
        y2={aSvgY}
        stroke={color}
        strokeWidth={isInvalid ? 1.5 : 3}
        strokeOpacity={isInvalid ? 0.6 : 0.85}
        strokeDasharray={isInvalid ? '5 4' : undefined}
        strokeLinecap="round"
      />
      {/* Fairlead (no casco) */}
      <circle cx={fSvgX} cy={fSvgY} r={4} fill={color} />
      {/* Âncora */}
      <polygon
        points={`${aSvgX},${aSvgY - 6} ${aSvgX + 5},${aSvgY + 4} ${aSvgX - 5},${aSvgY + 4}`}
        fill={color}
        opacity={0.9}
      />
      <text x={lx} y={ly - 6} textAnchor="middle" className="msys-line-label">
        {lineResult.line_name}
      </text>
    </g>
  )
}

function ResultantArrow({
  force_xy,
  maxRadius,
  toSvg,
}: {
  force_xy: [number, number]
  maxRadius: number
  toSvg: (x: number, y: number) => [number, number]
}) {
  // O resultante físico está em N. Para visualização, normaliza a
  // magnitude para uma fração do raio máximo (40%) — assim a seta sempre
  // tem tamanho legível independente da escala da força.
  const fx = force_xy[0]
  const fy = force_xy[1]
  const mag = Math.hypot(fx, fy)
  if (mag <= 0) return null
  const targetLen = maxRadius * 0.4
  const ux = (fx / mag) * targetLen
  const uy = (fy / mag) * targetLen
  const [originX, originY] = toSvg(0, 0)
  const [tipX, tipY] = toSvg(ux, uy)

  // Cabeça da seta
  const angle = Math.atan2(tipY - originY, tipX - originX)
  const arrowSize = 10
  const ax1 = tipX - Math.cos(angle - Math.PI / 6) * arrowSize
  const ay1 = tipY - Math.sin(angle - Math.PI / 6) * arrowSize
  const ax2 = tipX - Math.cos(angle + Math.PI / 6) * arrowSize
  const ay2 = tipY - Math.sin(angle + Math.PI / 6) * arrowSize

  return (
    <g>
      <line
        x1={originX}
        y1={originY}
        x2={tipX}
        y2={tipY}
        stroke="#EC4899"
        strokeWidth={2.5}
        strokeOpacity={0.9}
      />
      <polygon
        points={`${tipX},${tipY} ${ax1},${ay1} ${ax2},${ay2}`}
        fill="#EC4899"
        opacity={0.9}
      />
    </g>
  )
}
