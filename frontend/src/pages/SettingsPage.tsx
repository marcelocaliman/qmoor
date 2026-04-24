import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Info, Keyboard, Moon, Sun, SunMoon } from 'lucide-react'
import { fetchVersion } from '@/api/endpoints'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { resolveTheme, useThemeStore } from '@/store/theme'
import { useUIStore } from '@/store/ui'
import { cn } from '@/lib/utils'

export function SettingsPage() {
  const { theme, setTheme } = useThemeStore()
  const { unitSystem, setUnitSystem } = useUIStore()
  const { data: version } = useQuery({
    queryKey: ['version'],
    queryFn: fetchVersion,
    staleTime: 5 * 60_000,
  })

  const resolvedTheme = resolveTheme(theme)

  return (
    <>
      <Topbar />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        <div className="mx-auto max-w-2xl space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Aparência</CardTitle>
              <CardDescription>Tema e preferências de exibição.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <Label className="mb-2 block">Tema</Label>
                <div className="flex gap-2">
                  {(
                    [
                      { v: 'light', Icon: Sun, label: 'Claro' },
                      { v: 'dark', Icon: Moon, label: 'Escuro' },
                      { v: 'system', Icon: SunMoon, label: 'Sistema' },
                    ] as const
                  ).map(({ v, Icon, label }) => (
                    <Button
                      key={v}
                      type="button"
                      variant={theme === v ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setTheme(v)}
                      className={cn('flex-1 justify-start')}
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </Button>
                  ))}
                </div>
                {theme === 'system' && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Usando {resolvedTheme === 'dark' ? 'escuro' : 'claro'}{' '}
                    (preferência do sistema).
                  </p>
                )}
              </div>

              <div>
                <Label>Sistema de unidades padrão</Label>
                <p className="mb-1.5 text-xs text-muted-foreground">
                  Preferido em displays e exportação. Backend armazena sempre em SI.
                </p>
                <Select
                  value={unitSystem}
                  onValueChange={(v) =>
                    setUnitSystem(v as 'metric' | 'imperial')
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="metric">Métrico (m, N, Pa)</SelectItem>
                    <SelectItem value="imperial">Imperial (ft, lbf, kip/in²)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 p-3">
                <div>
                  <p className="text-sm font-medium">Idioma</p>
                  <p className="text-xs text-muted-foreground">
                    Português (Brasil). Outros idiomas fora do MVP.
                  </p>
                </div>
                <Switch checked disabled aria-label="Idioma fixo" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Keyboard className="h-4 w-4" />
                Atalhos de teclado
              </CardTitle>
              <CardDescription>
                Pressione <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">?</kbd>{' '}
                em qualquer tela para ver todos.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-sm">
                <ShortcutRow keys={['?']} label="Abrir ajuda" />
                <ShortcutRow keys={['Cmd', 'B']} label="Alternar sidebar" />
                <ShortcutRow keys={['Esc']} label="Fechar diálogos" />
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="h-4 w-4" />
                Sobre
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">API</dt>
                  <dd className="font-mono">{version?.api ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Schema DB</dt>
                  <dd className="font-mono">{version?.schema_version ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Solver</dt>
                  <dd className="font-mono">{version?.solver ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Frontend</dt>
                  <dd className="font-mono">0.1.0</dd>
                </div>
              </dl>
              <p className="border-t border-border pt-3 text-xs text-muted-foreground">
                QMoor Web — análise estática de linhas de ancoragem offshore.
                Solver de catenária elástica validado contra MoorPy
                (&lt;1% em força, &lt;0,5% em geometria) em 9 casos de benchmark.
              </p>
              <div className="flex flex-wrap gap-3 text-xs">
                <a
                  href="/api/v1/docs"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  API Docs (Swagger) <ExternalLink className="h-3 w-3" />
                </a>
                <a
                  href="https://github.com/marcelocaliman/qmoor"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  Repositório <ExternalLink className="h-3 w-3" />
                </a>
                <a
                  href="https://github.com/NREL/MoorPy"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  MoorPy (referência) <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  )
}

function ShortcutRow({ keys, label }: { keys: string[]; label: string }) {
  return (
    <div className="flex items-center justify-between">
      <dd className="text-muted-foreground">{label}</dd>
      <dt className="flex items-center gap-1">
        {keys.map((k, i) => (
          <kbd
            key={i}
            className="inline-flex h-6 min-w-6 items-center justify-center rounded border border-border bg-muted px-1.5 font-mono text-[11px]"
          >
            {k}
          </kbd>
        ))}
      </dt>
    </div>
  )
}
