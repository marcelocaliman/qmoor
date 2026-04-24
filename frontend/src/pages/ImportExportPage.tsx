import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileText,
  Upload,
  X,
} from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import {
  exportJsonUrl,
  exportMoorUrl,
  exportPdfUrl,
  importMoor,
  listCases,
} from '@/api/endpoints'
import { EmptyState } from '@/components/common/EmptyState'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

type ParseState =
  | { status: 'idle' }
  | { status: 'parsed'; payload: Record<string, unknown>; filename: string }
  | { status: 'error'; error: string; filename: string }

export function ImportExportPage() {
  return (
    <>
      <Topbar />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        <Tabs defaultValue="import">
          <TabsList>
            <TabsTrigger value="import" className="gap-1.5">
              <Upload className="h-3.5 w-3.5" />
              Importar
            </TabsTrigger>
            <TabsTrigger value="export" className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Exportar em lote
            </TabsTrigger>
          </TabsList>
          <TabsContent value="import" className="mt-5">
            <ImportPanel />
          </TabsContent>
          <TabsContent value="export" className="mt-5">
            <ExportPanel />
          </TabsContent>
        </Tabs>
      </div>
    </>
  )
}

// ──────────────────────────────── IMPORT ─────────────────────────────────────

function ImportPanel() {
  const [parse, setParse] = useState<ParseState>({ status: 'idle' })
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const handleFile = useCallback(async (file: File) => {
    const filename = file.name
    try {
      const text = await file.text()
      const payload = JSON.parse(text) as Record<string, unknown>
      if (typeof payload !== 'object' || payload === null) {
        throw new Error('JSON raiz precisa ser um objeto')
      }
      setParse({ status: 'parsed', payload, filename })
      toast.success(`${filename} carregado.`)
    } catch (err) {
      setParse({
        status: 'error',
        error: err instanceof Error ? err.message : 'Falha ao ler arquivo',
        filename,
      })
    }
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files?.[0]
      if (f) handleFile(f)
    },
    [handleFile],
  )

  const importMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => importMoor(payload),
    onSuccess: (out) => {
      toast.success('Caso criado.')
      navigate(`/cases/${out.id}`)
    },
    onError: (err) => {
      toast.error('Falha ao importar', {
        description: err instanceof ApiError ? err.message : String(err),
      })
    },
  })

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Importar arquivo .moor</CardTitle>
          <CardDescription>
            Arraste um arquivo JSON no formato QMoor Web (Seção 5.2 do MVP v2)
            ou clique para selecionar. Campos quantitativos podem vir como
            strings com unidade (ex: "450 ft") ou números no sistema indicado.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
            }}
            role="button"
            tabIndex={0}
            className={cn(
              'flex h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border bg-muted/30 text-center transition-colors',
              dragging && 'border-primary bg-primary/5',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            )}
          >
            <Upload className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm">
              <span className="font-medium text-foreground">Clique</span> ou
              arraste aqui um arquivo{' '}
              <code className="rounded-sm bg-muted px-1 py-0.5 font-mono text-xs">
                .moor
              </code>{' '}
              / JSON
            </p>
            <p className="text-[11px] text-muted-foreground">Máx 5 MB</p>
            <input
              type="file"
              accept=".json,.moor,application/json"
              ref={inputRef}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Preview */}
      {parse.status === 'parsed' && (
        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <CheckCircle2 className="h-4 w-4 text-success" />
                Pré-visualização · {parse.filename}
              </CardTitle>
              <CardDescription>
                Confira os campos antes de criar o caso.
              </CardDescription>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setParse({ status: 'idle' })}
              aria-label="Limpar preview"
            >
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto custom-scroll rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
              {JSON.stringify(parse.payload, null, 2)}
            </pre>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setParse({ status: 'idle' })}
              >
                Descartar
              </Button>
              <Button
                onClick={() => importMutation.mutate(parse.payload)}
                disabled={importMutation.isPending}
              >
                <Upload className="h-4 w-4" />
                Criar caso a partir deste arquivo
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {parse.status === 'error' && (
        <Card className="border-danger/40 bg-danger/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertCircle className="mt-0.5 h-4 w-4 text-danger" />
            <div className="flex-1">
              <p className="font-medium text-danger">
                Falha ao ler {parse.filename}
              </p>
              <p className="text-sm text-muted-foreground">{parse.error}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setParse({ status: 'idle' })}
            >
              <X className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ──────────────────────────────── EXPORT ─────────────────────────────────────

type ExportFmt = 'moor-metric' | 'moor-imperial' | 'json' | 'pdf'

function ExportPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['cases', 1, ''],
    queryFn: () => listCases({ page: 1, page_size: 100 }),
  })

  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [format, setFormat] = useState<ExportFmt>('json')

  const items = data?.items ?? []
  const allSelected = items.length > 0 && selected.size === items.length

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(items.map((c) => c.id)))
    }
  }

  function downloadEach() {
    if (selected.size === 0) {
      toast.warning('Selecione ao menos 1 caso.')
      return
    }
    Array.from(selected).forEach((id, i) => {
      const url =
        format === 'moor-metric'
          ? exportMoorUrl(id, 'metric')
          : format === 'moor-imperial'
            ? exportMoorUrl(id, 'imperial')
            : format === 'json'
              ? exportJsonUrl(id)
              : exportPdfUrl(id)
      // Dispara downloads com pequeno atraso para não ser bloqueado pelo browser
      setTimeout(() => {
        const a = document.createElement('a')
        a.href = url
        a.download = ''
        a.click()
      }, i * 120)
    })
    toast.success(`Disparando ${selected.size} downloads…`, {
      description:
        'Se o browser bloquear downloads múltiplos, permita pop-ups para este site.',
    })
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Exportação em lote</CardTitle>
          <CardDescription>
            Selecione os casos e o formato desejado. Cada caso gera um
            download separado — habilite pop-ups para mais de um arquivo.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Formato:</span>
            {(
              [
                ['json', 'JSON'],
                ['moor-metric', '.moor (métrico)'],
                ['moor-imperial', '.moor (imperial)'],
                ['pdf', 'PDF'],
              ] as Array<[ExportFmt, string]>
            ).map(([v, label]) => (
              <Button
                key={v}
                variant={format === v ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFormat(v)}
              >
                {label}
              </Button>
            ))}
            <Button
              onClick={downloadEach}
              size="sm"
              disabled={selected.size === 0}
              className="ml-auto"
            >
              <Download className="h-4 w-4" />
              Baixar {selected.size} {selected.size === 1 ? 'caso' : 'casos'}
            </Button>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="Nenhum caso para exportar"
              description="Crie um caso ou importe um .moor primeiro."
              action={
                <Button asChild>
                  <Link to="/cases/new">Novo caso</Link>
                </Button>
              }
              className="border-none"
            />
          ) : (
            <div className="rounded-lg border border-border">
              <div className="flex items-center gap-3 border-b border-border px-3 py-2">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={toggleAll}
                  aria-label="Selecionar todos"
                />
                <span className="text-xs text-muted-foreground">
                  {selected.size} selecionado(s) de {items.length}
                </span>
              </div>
              <ul className="divide-y divide-border">
                {items.map((c) => (
                  <li key={c.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-2 transition-colors hover:bg-muted/40">
                      <Checkbox
                        checked={selected.has(c.id)}
                        onCheckedChange={() => {
                          setSelected((prev) => {
                            const next = new Set(prev)
                            if (next.has(c.id)) next.delete(c.id)
                            else next.add(c.id)
                            return next
                          })
                        }}
                        aria-label={`Selecionar ${c.name}`}
                      />
                      <div className="flex flex-1 items-center justify-between gap-2 text-sm">
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {c.mode} · {c.water_depth.toFixed(0)} m
                        </span>
                      </div>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
