import {
  ArrowLeftRight,
  Compass,
  LayoutList,
  Package,
  Settings,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { ApiStatusIndicator } from '@/components/common/ApiStatusIndicator'
import { Logo } from '@/components/common/Logo'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { Separator } from '@/components/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface NavItem {
  label: string
  to: string
  icon: React.ComponentType<{ className?: string }>
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Casos', to: '/cases', icon: LayoutList },
  { label: 'Mooring systems', to: '/mooring-systems', icon: Compass },
  { label: 'Catálogo', to: '/catalog', icon: Package },
  { label: 'Importar/Exportar', to: '/import-export', icon: ArrowLeftRight },
  { label: 'Configurações', to: '/settings', icon: Settings },
]

/**
 * Sidebar compacta (64px) — apenas ícones, nome em tooltip ao hover.
 * Sem toggle de colapsar; mantém o layout limpo e previsível.
 */
export function Sidebar() {
  return (
    <aside
      aria-label="Navegação principal"
      className="flex h-screen w-16 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground"
    >
      {/* Logo */}
      <div className="flex h-14 shrink-0 items-center justify-center border-b border-border">
        <Tooltip>
          <TooltipTrigger asChild>
            <NavLink to="/" aria-label="QMoor Web — Início">
              <Logo compact />
            </NavLink>
          </TooltipTrigger>
          <TooltipContent side="right">QMoor Web</TooltipContent>
        </Tooltip>
      </div>

      {/* Itens */}
      <nav className="flex-1 overflow-y-auto custom-scroll py-2">
        <ul className="flex flex-col items-center gap-1">
          {NAV_ITEMS.map(({ label, to, icon: Icon }) => (
            <li key={to}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <NavLink
                    to={to}
                    end={to === '/cases'}
                    aria-label={label}
                    className={({ isActive }) =>
                      cn(
                        'relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        isActive
                          ? 'bg-primary/12 text-primary'
                          : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span
                            aria-hidden
                            className="absolute -left-[6px] top-1.5 h-7 w-[3px] rounded-full bg-primary"
                          />
                        )}
                        <Icon className="h-[18px] w-[18px]" />
                      </>
                    )}
                  </NavLink>
                </TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            </li>
          ))}
        </ul>
      </nav>

      <Separator />

      {/* Rodapé: status API + tema */}
      <div className="flex shrink-0 flex-col items-center gap-1 py-2">
        <ApiStatusIndicator compact />
        <ThemeToggle compact />
      </div>
    </aside>
  )
}
