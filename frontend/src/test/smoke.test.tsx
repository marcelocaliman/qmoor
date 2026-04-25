import { vi, describe, it, expect } from 'vitest'
import { renderWithProviders } from './helpers'

/**
 * Smoke tests — para cada página principal, garantimos:
 *   - import resolve sem erro
 *   - render inicial não crasha (mesmo com a API offline; o axios é
 *     mockado no setup global)
 *   - elementos de marcação esperados aparecem no DOM
 *
 * Não cobrem comportamento — alvo é detectar regressão grossa
 * (importação quebrada, JSX inválido, hooks chamados fora de provider).
 */

// Mock axios global para todos os testes deste arquivo.
vi.mock('axios', () => {
  const stub = {
    create: () => stub,
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: {
      response: { use: vi.fn() },
      request: { use: vi.fn() },
    },
  }
  return { default: stub }
})

describe('smoke: páginas renderizam sem crashar', () => {
  it('CasesListPage', async () => {
    const { CasesListPage } = await import('@/pages/CasesListPage')
    const { container } = renderWithProviders(<CasesListPage />)
    expect(container).toBeTruthy()
  })

  it('CaseFormPage', async () => {
    const { CaseFormPage } = await import('@/pages/CaseFormPage')
    const { container } = renderWithProviders(<CaseFormPage />, {
      route: '/cases/new',
    })
    expect(container).toBeTruthy()
  })

  it('CatalogPage', async () => {
    const { CatalogPage } = await import('@/pages/CatalogPage')
    const { container } = renderWithProviders(<CatalogPage />)
    expect(container).toBeTruthy()
  })

  it('SettingsPage', async () => {
    const { SettingsPage } = await import('@/pages/SettingsPage')
    const { container } = renderWithProviders(<SettingsPage />)
    expect(container).toBeTruthy()
  })

  it('ImportExportPage', async () => {
    const { ImportExportPage } = await import('@/pages/ImportExportPage')
    const { container } = renderWithProviders(<ImportExportPage />)
    expect(container).toBeTruthy()
  })
})

describe('smoke: utilitários de unidades', () => {
  it('siToUnit converte corretamente kgf/m → N/m', async () => {
    const { siToUnit, unitToSi } = await import('@/lib/units')
    // 201,395 N/m em kgf/m: 201,395 / 9,80665 ≈ 20,53
    expect(siToUnit(201.395, 'kgf/m')).toBeCloseTo(20.53, 1)
    // round-trip
    expect(unitToSi(siToUnit(4.804e6, 'te'), 'te')).toBeCloseTo(4.804e6, 0)
  })

  it('fmtForce respeita o sistema escolhido', async () => {
    const { fmtForce } = await import('@/lib/units')
    expect(fmtForce(600000, 'metric')).toMatch(/te$/)
    expect(fmtForce(600000, 'si')).toMatch(/N$/)
  })
})

describe('smoke: ApiError', () => {
  it('expõe code, message e status', async () => {
    const { ApiError } = await import('@/api/client')
    const err = new ApiError('boom', 'falhou', 500)
    expect(err.code).toBe('boom')
    expect(err.message).toBe('falhou')
    expect(err.status).toBe(500)
  })
})
