import '@testing-library/jest-dom/vitest'
import { afterEach, beforeAll, vi } from 'vitest'

/**
 * Setup global do Vitest. Executado antes de cada arquivo de teste.
 *
 * Garantias:
 *   1. Stubs de window APIs que o jsdom não fornece nativamente
 *      (matchMedia, ResizeObserver, scrollTo). Sem isso, componentes
 *      que tocam essas APIs (theme, charts, popovers) crasham antes
 *      do render terminar.
 *   2. localStorage limpo entre testes (zustand persist usa).
 *   3. Mock leve de axios — testes de smoke não devem fazer rede real.
 *      Cada teste pode sobrescrever via vi.spyOn.
 */

beforeAll(() => {
  // matchMedia: usado pelo store de theme para resolver `system`.
  if (typeof window !== 'undefined' && !window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  }

  // ResizeObserver: Plotly e Radix usam.
  class ResizeObserverStub {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
  }
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ResizeObserverStub

  // IntersectionObserver: alguns componentes do Radix usam.
  class IntersectionObserverStub {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
    takeRecords = vi.fn().mockReturnValue([])
    root = null
    rootMargin = ''
    thresholds = []
  }
  ;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
    IntersectionObserverStub

  // scrollTo: jsdom não implementa.
  if (typeof window !== 'undefined') {
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
  }
})

afterEach(() => {
  // Limpa state persistente do zustand entre testes (theme, units).
  if (typeof localStorage !== 'undefined') localStorage.clear()
  vi.restoreAllMocks()
})
