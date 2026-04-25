import { lazy, Suspense } from 'react'
import {
  Navigate,
  RouterProvider,
  createBrowserRouter,
} from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Code-splitting por rota: cada página é um chunk separado, carregado
 * sob demanda. Reduz drasticamente o JS executado no primeiro carregamento
 * da listagem de casos (rota inicial), que é a fatia visível ao usuário.
 *
 * Páginas que usam Plotly (CaseDetailPage, CaseFormPage, CompareCasesPage)
 * só puxam o chunk plotly-vendor quando a rota é visitada de fato.
 */
const CasesListPage = lazy(() =>
  import('@/pages/CasesListPage').then((m) => ({ default: m.CasesListPage })),
)
const CaseDetailPage = lazy(() =>
  import('@/pages/CaseDetailPage').then((m) => ({ default: m.CaseDetailPage })),
)
const CaseFormPage = lazy(() =>
  import('@/pages/CaseFormPage').then((m) => ({ default: m.CaseFormPage })),
)
const CompareCasesPage = lazy(() =>
  import('@/pages/CompareCasesPage').then((m) => ({
    default: m.CompareCasesPage,
  })),
)
const CatalogPage = lazy(() =>
  import('@/pages/CatalogPage').then((m) => ({ default: m.CatalogPage })),
)
const ImportExportPage = lazy(() =>
  import('@/pages/ImportExportPage').then((m) => ({
    default: m.ImportExportPage,
  })),
)
const SettingsPage = lazy(() =>
  import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const MooringSystemsListPage = lazy(() =>
  import('@/pages/MooringSystemsListPage').then((m) => ({
    default: m.MooringSystemsListPage,
  })),
)
const MooringSystemDetailPage = lazy(() =>
  import('@/pages/MooringSystemDetailPage').then((m) => ({
    default: m.MooringSystemDetailPage,
  })),
)
const MooringSystemFormPage = lazy(() =>
  import('@/pages/MooringSystemFormPage').then((m) => ({
    default: m.MooringSystemFormPage,
  })),
)
const NotFoundPage = lazy(() =>
  import('@/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

function PageFallback() {
  return (
    <div className="flex flex-1 flex-col gap-3 p-6">
      <Skeleton className="h-9 w-1/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

const wrap = (el: React.ReactNode) => (
  <Suspense fallback={<PageFallback />}>{el}</Suspense>
)

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/cases" replace /> },
      { path: 'cases', element: wrap(<CasesListPage />) },
      { path: 'cases/new', element: wrap(<CaseFormPage />) },
      { path: 'cases/compare', element: wrap(<CompareCasesPage />) },
      { path: 'cases/:id', element: wrap(<CaseDetailPage />) },
      { path: 'cases/:id/edit', element: wrap(<CaseFormPage />) },
      { path: 'mooring-systems', element: wrap(<MooringSystemsListPage />) },
      { path: 'mooring-systems/new', element: wrap(<MooringSystemFormPage />) },
      { path: 'mooring-systems/:id', element: wrap(<MooringSystemDetailPage />) },
      { path: 'mooring-systems/:id/edit', element: wrap(<MooringSystemFormPage />) },
      { path: 'catalog', element: wrap(<CatalogPage />) },
      { path: 'import-export', element: wrap(<ImportExportPage />) },
      { path: 'settings', element: wrap(<SettingsPage />) },
      { path: '*', element: wrap(<NotFoundPage />) },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
