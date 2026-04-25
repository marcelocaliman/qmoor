/**
 * Funções de acesso à API organizadas por recurso. Todas retornam
 * Promises tipadas. Usadas pelos hooks do TanStack Query.
 */
import { apiClient } from './client'
import type {
  CaseInput,
  CaseOutput,
  CriteriaProfileInfo,
  HealthResponse,
  LineTypeCreate,
  LineTypeOutput,
  LineTypeUpdate,
  MooringSystemExecutionOutput,
  MooringSystemInput,
  MooringSystemOutput,
  MooringSystemResult,
  PaginatedResponse_CaseSummary_,
  PaginatedResponse_LineTypeOutput_,
  PaginatedResponse_MooringSystemSummary_,
  VersionResponse,
} from './types'

// ─────────────────────────────── metadata ──────────────────────────────────
export const fetchHealth = () =>
  apiClient.get<HealthResponse>('/health').then((r) => r.data)

export const fetchVersion = () =>
  apiClient.get<VersionResponse>('/version').then((r) => r.data)

export const fetchCriteriaProfiles = () =>
  apiClient.get<CriteriaProfileInfo[]>('/criteria-profiles').then((r) => r.data)

// ─────────────────────────────── cases ─────────────────────────────────────
export interface ListCasesParams {
  page?: number
  page_size?: number
  search?: string
}

export const listCases = (params?: ListCasesParams) =>
  apiClient
    .get<PaginatedResponse_CaseSummary_>('/cases', { params })
    .then((r) => r.data)

export const getCase = (id: number) =>
  apiClient.get<CaseOutput>(`/cases/${id}`).then((r) => r.data)

export const createCase = (input: CaseInput) =>
  apiClient.post<CaseOutput>('/cases', input).then((r) => r.data)

export const updateCase = (id: number, input: CaseInput) =>
  apiClient.put<CaseOutput>(`/cases/${id}`, input).then((r) => r.data)

export const deleteCase = (id: number) =>
  apiClient.delete(`/cases/${id}`).then((r) => r.data)

export const solveCase = (id: number) =>
  apiClient.post(`/cases/${id}/solve`).then((r) => r.data)

/**
 * Dry-run: não persiste. Usa para análise paramétrica ao vivo.
 *
 * Quando o solver retorna invalid_case/numerical_error (HTTP 422), a API
 * inclui o SolverResult completo em `error.detail.detail`. Para o preview
 * live queremos mostrar o gráfico mesmo nesses casos — a UI exibe o
 * alerta apropriado sem apagar a visualização.
 */
export const previewSolve = async (
  input: CaseInput,
): Promise<import('./types').SolverResult> => {
  try {
    const res = await apiClient.post<import('./types').SolverResult>(
      '/solve/preview',
      input,
    )
    return res.data
  } catch (err) {
    // ApiError com detail que é SolverResult: extrair
    if (
      err &&
      typeof err === 'object' &&
      'detail' in err &&
      err.detail &&
      typeof err.detail === 'object' &&
      'status' in err.detail &&
      'alert_level' in err.detail
    ) {
      return err.detail as unknown as import('./types').SolverResult
    }
    throw err
  }
}

// ─────────────────────────────── catalog ───────────────────────────────────
export interface ListLineTypesParams {
  page?: number
  page_size?: number
  category?: string
  search?: string
  diameter_min?: number
  diameter_max?: number
}

export const listLineTypes = (params?: ListLineTypesParams) =>
  apiClient
    .get<PaginatedResponse_LineTypeOutput_>('/line-types', { params })
    .then((r) => r.data)

export const getLineType = (id: number) =>
  apiClient.get<LineTypeOutput>(`/line-types/${id}`).then((r) => r.data)

export const lookupLineType = (line_type: string, diameter: number) =>
  apiClient
    .get<LineTypeOutput>('/line-types/lookup', { params: { line_type, diameter } })
    .then((r) => r.data)

export const createLineType = (input: LineTypeCreate) =>
  apiClient.post<LineTypeOutput>('/line-types', input).then((r) => r.data)

export const updateLineType = (id: number, input: LineTypeUpdate) =>
  apiClient.put<LineTypeOutput>(`/line-types/${id}`, input).then((r) => r.data)

export const deleteLineType = (id: number) =>
  apiClient.delete(`/line-types/${id}`).then((r) => r.data)

// ─────────────────────────────── mooring systems (F5.4) ───────────────────
export interface ListMooringSystemsParams {
  page?: number
  page_size?: number
  search?: string
}

export const listMooringSystems = (params?: ListMooringSystemsParams) =>
  apiClient
    .get<PaginatedResponse_MooringSystemSummary_>('/mooring-systems', { params })
    .then((r) => r.data)

export const getMooringSystem = (id: number) =>
  apiClient.get<MooringSystemOutput>(`/mooring-systems/${id}`).then((r) => r.data)

export const createMooringSystem = (input: MooringSystemInput) =>
  apiClient
    .post<MooringSystemOutput>('/mooring-systems', input)
    .then((r) => r.data)

export const updateMooringSystem = (id: number, input: MooringSystemInput) =>
  apiClient
    .put<MooringSystemOutput>(`/mooring-systems/${id}`, input)
    .then((r) => r.data)

export const deleteMooringSystem = (id: number) =>
  apiClient.delete(`/mooring-systems/${id}`).then((r) => r.data)

export const solveMooringSystem = (id: number) =>
  apiClient
    .post<MooringSystemExecutionOutput>(`/mooring-systems/${id}/solve`)
    .then((r) => r.data)

export const previewSolveMooringSystem = (input: MooringSystemInput) =>
  apiClient
    .post<MooringSystemResult>('/mooring-systems/preview-solve', input)
    .then((r) => r.data)

/** URL absoluta para download direto via window.open / <a href>. */
export const exportMooringSystemJsonUrl = (msysId: number) =>
  `/api/v1/mooring-systems/${msysId}/export/json`

export const exportMooringSystemPdfUrl = (msysId: number) =>
  `/api/v1/mooring-systems/${msysId}/export/pdf`

// ─────────────────────────────── import/export ─────────────────────────────
export const importMoor = (payload: Record<string, unknown>) =>
  apiClient.post<CaseOutput>('/import/moor', payload).then((r) => r.data)

export const exportMoorUrl = (caseId: number, unitSystem: 'imperial' | 'metric') =>
  `/api/v1/cases/${caseId}/export/moor?unit_system=${unitSystem}`

export const exportJsonUrl = (caseId: number) =>
  `/api/v1/cases/${caseId}/export/json`

export const exportPdfUrl = (caseId: number) =>
  `/api/v1/cases/${caseId}/export/pdf`
