import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import {
  ChevronLeft,
  ChevronRight,
  Compass,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError } from '@/api/client'
import { deleteMooringSystem, listMooringSystems } from '@/api/endpoints'
import type { MooringSystemSummary } from '@/api/types'
import { EmptyState } from '@/components/common/EmptyState'
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

const PAGE_SIZE = 20

export function MooringSystemsListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const debounced = useDebounce(search, 300)
  const [page, setPage] = useState(1)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['mooring-systems', page, debounced],
    queryFn: () =>
      listMooringSystems({
        page,
        page_size: PAGE_SIZE,
        search: debounced || undefined,
      }),
  })

  const rows: MooringSystemSummary[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteMooringSystem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mooring-systems'] })
      toast.success('Sistema excluído com sucesso.')
      setDeleteId(null)
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : String(err)
      toast.error('Falha ao excluir sistema', { description: msg })
    },
  })

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
        <Link to="/mooring-systems/new">
          <Plus className="h-4 w-4" />
          Novo sistema
        </Link>
      </Button>
    </>
  )

  return (
    <>
      <Topbar actions={actions} />
      <div className="flex-1 overflow-auto custom-scroll p-6">
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <Label
              htmlFor="search"
              className="mb-1.5 block text-xs text-muted-foreground"
            >
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
                placeholder="Nome do sistema…"
                className="pl-8"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                  aria-label="Limpar busca"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
          <div className="ml-auto text-xs text-muted-foreground">
            {isLoading ? 'Carregando…' : `${rows.length} de ${total} sistemas`}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : isError ? (
            <EmptyState
              icon={Compass}
              title="Falha ao carregar sistemas"
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
              icon={Compass}
              title={search ? 'Nenhum sistema encontrado' : 'Nenhum sistema ainda'}
              description={
                search
                  ? `Nenhum resultado para "${search}".`
                  : 'Crie um sistema multi-linha para visualizar a planta de ancoragem e o resultante de forças.'
              }
              action={
                !search && (
                  <Button asChild size="sm">
                    <Link to="/mooring-systems/new">
                      <Plus className="h-4 w-4" />
                      Novo sistema
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
                  <TableHead className="w-[40%]">Nome</TableHead>
                  <TableHead className="text-right">Linhas</TableHead>
                  <TableHead className="text-right">Raio plataforma</TableHead>
                  <TableHead>Atualizado</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/mooring-systems/${row.id}`)}
                  >
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">
                          {row.name}
                        </span>
                        {row.description && (
                          <span className="line-clamp-1 text-xs text-muted-foreground">
                            {row.description}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-sm">
                      {row.line_count}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-sm">
                      {fmtMeters(row.platform_radius, 1)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {format(
                        new Date(row.updated_at),
                        "dd MMM yyyy 'às' HH:mm",
                        { locale: ptBR },
                      )}
                    </TableCell>
                    <TableCell
                      className="text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
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
                            <Link to={`/mooring-systems/${row.id}`}>Abrir</Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link to={`/mooring-systems/${row.id}/edit`}>
                              Editar
                            </Link>
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

      <Dialog open={deleteId !== null} onOpenChange={(o) => !o && setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir este sistema?</DialogTitle>
            <DialogDescription>
              Todas as execuções persistidas serão removidas junto. Esta ação
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
