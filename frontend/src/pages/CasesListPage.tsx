import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  FileBarChart2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { deleteCase, listCases } from '@/api/endpoints'
import type { CaseSummary } from '@/api/types'
import { ApiError } from '@/api/client'
import { EmptyState } from '@/components/common/EmptyState'
import {
  CategoryBadge,
  ModeBadge,
} from '@/components/common/StatusBadge'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDebounce } from '@/hooks/useDebounce'
import { fmtMeters } from '@/lib/utils'

type SortKey = 'name' | 'updated_at' | 'water_depth' | 'line_length' | 'mode'
type SortDir = 'asc' | 'desc'

const PAGE_SIZE = 20

export function CasesListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const debounced = useDebounce(search, 300)
  const [page, setPage] = useState(1)
  const [modeFilter, setModeFilter] = useState<string>('all')
  const [sortKey, setSortKey] = useState<SortKey>('updated_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['cases', page, debounced],
    queryFn: () =>
      listCases({
        page,
        page_size: PAGE_SIZE,
        search: debounced || undefined,
      }),
  })

  const rows = useMemo<CaseSummary[]>(() => {
    const base = data?.items ?? []
    const filtered =
      modeFilter === 'all' ? base : base.filter((r) => r.mode === modeFilter)
    // Ordenação client-side (backend já vem por updated_at desc)
    const sorted = [...filtered].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey]
      const bv = (b as unknown as Record<string, unknown>)[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return sortDir === 'asc' ? -1 : 1
      if (bv == null) return sortDir === 'asc' ? 1 : -1
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const as = String(av)
      const bs = String(bv)
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as)
    })
    return sorted
  }, [data, modeFilter, sortKey, sortDir])

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteCase(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      toast.success('Caso excluído com sucesso.')
      setDeleteId(null)
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao excluir caso', { description: msg })
    },
  })

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(k)
      setSortDir('asc')
    }
  }

  function sortIcon(k: SortKey) {
    if (sortKey !== k) {
      return <ArrowUpDown className="ml-1 inline h-3 w-3 opacity-50" aria-hidden />
    }
    return sortDir === 'asc' ? (
      <ArrowUp className="ml-1 inline h-3 w-3" aria-hidden />
    ) : (
      <ArrowDown className="ml-1 inline h-3 w-3" aria-hidden />
    )
  }

  const actions = (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => refetch()}
        disabled={isFetching}
        aria-label="Recarregar lista"
      >
        <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
      </Button>
      <Button asChild size="sm">
        <Link to="/cases/new">
          <Plus className="h-4 w-4" />
          Novo caso
        </Link>
      </Button>
    </>
  )

  return (
    <>
      <Topbar actions={actions} />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        {/* Filtros */}
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <Label htmlFor="search" className="mb-1.5 block text-xs text-muted-foreground">
              Buscar
            </Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                placeholder="Nome do caso…"
                className="pl-8"
                aria-label="Buscar casos"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Limpar busca"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
          <div className="w-40">
            <Label htmlFor="mode-filter" className="mb-1.5 block text-xs text-muted-foreground">
              Modo
            </Label>
            <Select value={modeFilter} onValueChange={setModeFilter}>
              <SelectTrigger id="mode-filter">
                <SelectValue placeholder="Modo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="Tension">Tension</SelectItem>
                <SelectItem value="Range">Range</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="ml-auto text-xs text-muted-foreground">
            {isLoading
              ? 'Carregando…'
              : `${rows.length} de ${total} casos`}
          </div>
        </div>

        {/* Table */}
        <div className="rounded-lg border border-border bg-card">
          {isLoading ? (
            <div className="p-4">
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            </div>
          ) : isError ? (
            <EmptyState
              icon={FileBarChart2}
              title="Falha ao carregar casos"
              description={
                error instanceof ApiError
                  ? error.message
                  : 'Verifique se o backend está no ar.'
              }
              action={
                <Button size="sm" onClick={() => refetch()}>
                  Tentar novamente
                </Button>
              }
              className="m-4 border-none"
            />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={FileBarChart2}
              title={search ? 'Nenhum caso encontrado' : 'Nenhum caso ainda'}
              description={
                search
                  ? `Nenhum resultado para "${search}". Tente outra busca ou limpe o filtro.`
                  : 'Crie o primeiro caso para começar a calcular catenárias.'
              }
              action={
                !search && (
                  <Button asChild size="sm">
                    <Link to="/cases/new">
                      <Plus className="h-4 w-4" />
                      Novo caso
                    </Link>
                  </Button>
                )
              }
              className="m-4 border-none"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[34%] cursor-pointer" onClick={() => toggleSort('name')}>
                    Nome
                    {sortIcon('name')}
                  </TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead
                    className="cursor-pointer text-right"
                    onClick={() => toggleSort('water_depth')}
                  >
                    Lâmina d'água
                    {sortIcon('water_depth')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer text-right"
                    onClick={() => toggleSort('line_length')}
                  >
                    Comprimento
                    {sortIcon('line_length')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => toggleSort('mode')}
                  >
                    Modo
                    {sortIcon('mode')}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => toggleSort('updated_at')}
                  >
                    Atualizado
                    {sortIcon('updated_at')}
                  </TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/cases/${row.id}`)}
                  >
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">{row.name}</span>
                        {row.description && (
                          <span className="line-clamp-1 text-xs text-muted-foreground">
                            {row.description}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <CategoryBadge category={row.line_type ?? null} />
                        {row.line_type && (
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {row.line_type}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-sm">
                      {fmtMeters(row.water_depth, 1)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-sm">
                      {fmtMeters(row.line_length, 1)}
                    </TableCell>
                    <TableCell>
                      <ModeBadge mode={row.mode} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {format(new Date(row.updated_at), "dd MMM yyyy 'às' HH:mm", { locale: ptBR })}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            aria-label="Ações"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link to={`/cases/${row.id}`}>Abrir</Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link to={`/cases/${row.id}/edit`}>Editar</Link>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-danger focus:text-danger"
                            onSelect={() => setDeleteId(row.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                            Excluir
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Paginação */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Página {page} de {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page <= 1}
              >
                <ChevronLeft className="h-4 w-4" />
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page >= totalPages}
              >
                Próxima
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmação de exclusão */}
      <Dialog open={deleteId !== null} onOpenChange={(o) => !o && setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir este caso?</DialogTitle>
            <DialogDescription>
              Todas as execuções associadas serão removidas junto. Esta ação
              não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteId(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
              Excluir permanentemente
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
