/**
 * Tipos da API derivados do schema OpenAPI (gerados por openapi-typescript).
 * Aliases convenientes para uso no app.
 */
import type { components } from '@/types/openapi'

type S = components['schemas']

export type CaseInput = S['CaseInput']
export type CaseOutput = S['CaseOutput']
export type CaseSummary = S['CaseSummary']
export type ExecutionOutput = S['ExecutionOutput']
export type PaginatedResponse_CaseSummary_ = S['PaginatedResponse_CaseSummary_']
export type PaginatedResponse_LineTypeOutput_ = S['PaginatedResponse_LineTypeOutput_']
export type LineTypeOutput = S['LineTypeOutput']
export type LineTypeCreate = S['LineTypeCreate']
export type LineTypeUpdate = S['LineTypeUpdate']
export type SolverResult = S['SolverResult']
export type LineSegment = S['LineSegment']
export type BoundaryConditions = S['BoundaryConditions']
export type SeabedConfig = S['SeabedConfig']
export type UtilizationLimits = S['UtilizationLimits']
export type LineAttachment = S['LineAttachment']
export type AttachmentKind = LineAttachment['kind']

export type SolutionMode = S['SolutionMode']
export type ConvergenceStatus = S['ConvergenceStatus']
export type AlertLevel = S['AlertLevel']
export type CriteriaProfile = S['CriteriaProfile']
export type LineCategory =
  | 'Wire'
  | 'StuddedChain'
  | 'StudlessChain'
  | 'Polyester'

export interface CriteriaProfileInfo {
  name: string
  yellow_ratio: number
  red_ratio: number
  broken_ratio: number
  description: string
}

export interface HealthResponse {
  status: string
  db: string
}

export interface VersionResponse {
  api: string
  schema_version: string
  solver: string
}
