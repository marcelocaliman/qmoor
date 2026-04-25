import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import { type ReactElement, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'

/**
 * Helper de render para testes de smoke. Envolve o componente com:
 *  - QueryClientProvider isolado por chamada (sem cache compartilhado)
 *  - TooltipProvider (Radix)
 *  - MemoryRouter (rotas em memória, configuráveis por `initialEntries`)
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    ...rtlOptions
  }: { route?: string } & Omit<RenderOptions, 'wrapper'> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    )
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...rtlOptions }) }
}
