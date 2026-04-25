import { useQuery } from '@tanstack/react-query'
import { Command } from 'cmdk'
import {
  ArrowRight,
  Box,
  Cog,
  FilePlus,
  Files,
  ImportIcon,
  Moon,
  PaintBucket,
  Ruler,
  Sun,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listCases, listLineTypes } from '@/api/endpoints'
import { useDebounce } from '@/hooks/useDebounce'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/store/theme'
import { useUnitsStore } from '@/store/units'

export interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Command palette global (Cmd+K / Ctrl+K). Busca incremental em:
 *   - ações rápidas (estáticas, navegação + toggles)
 *   - casos (POST /cases?search=...)
 *   - tipos de linha do catálogo (POST /line-types?search=...)
 *
 * Convenções:
 *   - cmdk roda o filtro/ranking client-side em cima de string `value` de
 *     cada CommandItem. Para resultados dinâmicos do servidor, embutimos
 *     o nome no `value` para que o cmdk continue rankeando corretamente
 *     mesmo quando o servidor já filtrou.
 *   - debounce de 200 ms para queries de servidor; abaixo disso a busca
 *     fica instantânea para os itens estáticos.
 */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const toggleTheme = useThemeStore((s) => s.toggle)
  const themeNow = useThemeStore((s) => s.theme)
  const toggleUnits = useUnitsStore((s) => s.toggle)
  const unitSystem = useUnitsStore((s) => s.system)

  const [query, setQuery] = useState('')
  const debounced = useDebounce(query, 200)

  // Reset query ao fechar para não persistir entre aberturas.
  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  // Queries paralelas de casos + line types — só quando há texto.
  const casesQuery = useQuery({
    queryKey: ['palette-cases', debounced],
    queryFn: () =>
      listCases({ page: 1, page_size: 8, search: debounced || undefined }),
    enabled: open,
    staleTime: 30_000,
  })
  const lineTypesQuery = useQuery({
    queryKey: ['palette-line-types', debounced],
    queryFn: () =>
      listLineTypes({
        page: 1,
        page_size: 8,
        search: debounced || undefined,
      }),
    enabled: open && debounced.length > 0,
    staleTime: 30_000,
  })

  function go(path: string) {
    onOpenChange(false)
    navigate(path)
  }

  // Wrapper handles dialog overlay + scroll lock manualmente; o cmdk
  // não traz isso por default. Usamos um div fullscreen com backdrop.
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-background/60 backdrop-blur-sm pt-[18vh]"
      onClick={() => onOpenChange(false)}
    >
      <Command
        label="Command palette"
        className={cn(
          'w-full max-w-xl rounded-xl border border-border bg-card shadow-2xl',
          'animate-in fade-in-0 zoom-in-95',
        )}
        onClick={(e) => e.stopPropagation()}
        loop
      >
        <div className="flex items-center border-b border-border px-3">
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="Buscar casos, tipos de linha ou ações…"
            className={cn(
              'flex h-11 w-full bg-transparent py-3 text-sm outline-none',
              'placeholder:text-muted-foreground',
            )}
            autoFocus
          />
          <kbd className="ml-2 hidden rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline-block">
            esc
          </kbd>
        </div>

        <Command.List className="max-h-[60vh] overflow-y-auto custom-scroll p-1">
          <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
            Nenhum resultado para “{query}”.
          </Command.Empty>

          {/* ─────────── Ações rápidas ─────────── */}
          <Command.Group
            heading="Ações rápidas"
            className="px-2 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground [&_[cmdk-group-heading]]:px-1.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-items]]:space-y-0.5"
          >
            <PaletteItem
              icon={<FilePlus className="h-4 w-4" />}
              label="Novo caso"
              shortcut="N"
              onSelect={() => go('/cases/new')}
            />
            <PaletteItem
              icon={<Files className="h-4 w-4" />}
              label="Ver todos os casos"
              shortcut="g c"
              onSelect={() => go('/cases')}
            />
            <PaletteItem
              icon={<Box className="h-4 w-4" />}
              label="Catálogo de linhas"
              shortcut="g a"
              onSelect={() => go('/catalog')}
            />
            <PaletteItem
              icon={<ImportIcon className="h-4 w-4" />}
              label="Importar / exportar"
              shortcut="g i"
              onSelect={() => go('/import-export')}
            />
            <PaletteItem
              icon={<Cog className="h-4 w-4" />}
              label="Configurações"
              shortcut="g s"
              onSelect={() => go('/settings')}
            />
            <PaletteItem
              icon={
                themeNow === 'dark' ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )
              }
              label={
                themeNow === 'dark'
                  ? 'Alternar tema (claro)'
                  : 'Alternar tema (escuro)'
              }
              onSelect={() => {
                toggleTheme()
                onOpenChange(false)
              }}
            />
            <PaletteItem
              icon={<Ruler className="h-4 w-4" />}
              label={`Unidades: ${unitSystem === 'metric' ? 'Metric → SI' : 'SI → Metric'}`}
              onSelect={() => {
                toggleUnits()
                onOpenChange(false)
              }}
            />
            <PaletteItem
              icon={<PaintBucket className="h-4 w-4" />}
              label="Ajuda e atalhos (?)"
              shortcut="?"
              onSelect={() => {
                onOpenChange(false)
                // Dispara o atalho ? para abrir HelpDialog (registrado em AppLayout).
                window.dispatchEvent(
                  new KeyboardEvent('keydown', { key: '?', shiftKey: true }),
                )
              }}
            />
          </Command.Group>

          {/* ─────────── Casos ─────────── */}
          {casesQuery.data && casesQuery.data.items.length > 0 && (
            <Command.Group
              heading="Casos"
              className="px-2 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground [&_[cmdk-group-heading]]:px-1.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-items]]:space-y-0.5"
            >
              {casesQuery.data.items.map((c) => (
                <PaletteItem
                  key={`case-${c.id}`}
                  value={`caso ${c.name} ${c.id}`}
                  icon={<Files className="h-4 w-4" />}
                  label={c.name}
                  hint={`#${c.id}`}
                  onSelect={() => go(`/cases/${c.id}`)}
                />
              ))}
            </Command.Group>
          )}

          {/* ─────────── Tipos de linha ─────────── */}
          {lineTypesQuery.data && lineTypesQuery.data.items.length > 0 && (
            <Command.Group
              heading="Catálogo de linhas"
              className="px-2 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground [&_[cmdk-group-heading]]:px-1.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-items]]:space-y-0.5"
            >
              {lineTypesQuery.data.items.map((lt) => (
                <PaletteItem
                  key={`lt-${lt.id}`}
                  value={`linha ${lt.line_type} ${lt.category}`}
                  icon={<Box className="h-4 w-4" />}
                  label={lt.line_type}
                  hint={`${lt.category} · Ø ${(lt.diameter * 1000).toFixed(0)} mm`}
                  onSelect={() => go(`/catalog?search=${encodeURIComponent(lt.line_type)}`)}
                />
              ))}
            </Command.Group>
          )}
        </Command.List>

        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
          <span>
            <kbd className="mr-1 rounded border border-border px-1 py-0.5 font-mono">
              ↑↓
            </kbd>
            navegar
            <kbd className="mx-1 ml-3 rounded border border-border px-1 py-0.5 font-mono">
              ↵
            </kbd>
            selecionar
            <kbd className="mx-1 ml-3 rounded border border-border px-1 py-0.5 font-mono">
              esc
            </kbd>
            fechar
          </span>
          <span>QMoor Web</span>
        </div>
      </Command>
    </div>
  )
}

/**
 * Item da palette com layout uniforme. `value` é a string usada pelo cmdk
 * para filtrar/rankear; quando ausente, ele cai pra cópia visível.
 */
function PaletteItem({
  icon,
  label,
  hint,
  shortcut,
  value,
  onSelect,
}: {
  icon: React.ReactNode
  label: string
  hint?: string
  shortcut?: string
  value?: string
  onSelect: () => void
}) {
  return (
    <Command.Item
      value={value ?? label}
      onSelect={onSelect}
      className={cn(
        'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors',
        'data-[selected=true]:bg-muted data-[selected=true]:text-foreground',
        'cursor-pointer text-muted-foreground',
      )}
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted/40 text-muted-foreground">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate text-foreground">{label}</span>
      {hint && (
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
          {hint}
        </span>
      )}
      {shortcut && (
        <kbd className="ml-1 shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {shortcut}
        </kbd>
      )}
      <ArrowRight className="h-3 w-3 shrink-0 opacity-0 transition-opacity data-[selected=true]:opacity-100" />
    </Command.Item>
  )
}
