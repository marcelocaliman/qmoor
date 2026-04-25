import { ChevronRight, Home } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useUnitsStore } from '@/store/units'

interface BreadcrumbItem {
  label: string
  to?: string
}

/**
 * Gera breadcrumbs a partir da rota atual. Customizável via prop
 * `items` (tem prioridade sobre o auto).
 */
function deriveBreadcrumbs(pathname: string): BreadcrumbItem[] {
  const segments = pathname.split('/').filter(Boolean)
  const items: BreadcrumbItem[] = []
  if (segments.length === 0) return [{ label: 'Início' }]

  const root = segments[0]
  const map: Record<string, string> = {
    cases: 'Casos',
    catalog: 'Catálogo',
    'import-export': 'Importar/Exportar',
    settings: 'Configurações',
  }
  items.push({ label: map[root] ?? root, to: `/${root}` })

  for (let i = 1; i < segments.length; i += 1) {
    const seg = segments[i]
    if (seg === 'new') items.push({ label: 'Novo' })
    else if (seg === 'edit') items.push({ label: 'Editar' })
    else if (seg === 'compare') items.push({ label: 'Comparar' })
    else if (/^\d+$/.test(seg)) items.push({ label: `#${seg}` })
    else items.push({ label: seg })
  }
  return items
}

export interface TopbarProps {
  /** Sobrescreve os breadcrumbs derivados da rota. */
  breadcrumbs?: BreadcrumbItem[]
  /** Ações contextuais à direita (botões). */
  actions?: ReactNode
}

export function Topbar({ breadcrumbs, actions }: TopbarProps) {
  const { pathname } = useLocation()
  const items = breadcrumbs ?? deriveBreadcrumbs(pathname)

  return (
    <header
      className={cn(
        'flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-background/80 px-6 backdrop-blur',
      )}
    >
      <nav aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <li>
            <Link
              to="/"
              className="flex items-center rounded-md p-1 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Início"
            >
              <Home className="h-3.5 w-3.5" />
            </Link>
          </li>
          {items.map((item, idx) => (
            <Fragment key={`${item.label}-${idx}`}>
              <li aria-hidden="true">
                <ChevronRight className="h-3.5 w-3.5" />
              </li>
              <li>
                {item.to && idx < items.length - 1 ? (
                  <Link
                    to={item.to}
                    className="rounded-sm px-1 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span
                    className={cn(
                      'px-1',
                      idx === items.length - 1 && 'font-medium text-foreground',
                    )}
                    aria-current={idx === items.length - 1 ? 'page' : undefined}
                  >
                    {item.label}
                  </span>
                )}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>

      <div className="flex items-center gap-2">
        <UnitSystemToggle />
        {actions}
      </div>
    </header>
  )
}

function UnitSystemToggle() {
  const system = useUnitsStore((s) => s.system)
  const setSystem = useUnitsStore((s) => s.setSystem)
  return (
    <div
      role="radiogroup"
      aria-label="Sistema de unidades"
      className="flex items-center rounded-md border border-border bg-muted/30 p-0.5 text-[11px] font-medium"
    >
      <button
        type="button"
        role="radio"
        aria-checked={system === 'metric'}
        onClick={() => setSystem('metric')}
        title="Metric: te, kgf/m, kN — convenção QMoor / offshore brasileira"
        className={cn(
          'rounded px-2 py-1 transition-colors',
          system === 'metric'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        Metric
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={system === 'si'}
        onClick={() => setSystem('si')}
        title="SI: N, N/m — sistema internacional puro"
        className={cn(
          'rounded px-2 py-1 transition-colors',
          system === 'si'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        SI
      </button>
    </div>
  )
}
