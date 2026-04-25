/**
 * Conversão e formatação de unidades para a UI.
 *
 * O backend trabalha 100% em SI (N, N/m, m, Pa). A UI permite que o usuário
 * trabalhe em sistema "metric" (te, kgf/m, kN) — convenção offshore brasileira
 * que combina com QMoor 0.8.5 e memoriais técnicos típicos.
 *
 * Pipeline:
 *   value SI ──[siToDisplay]──► display(value, unit) ──[displayToSi]──► value SI
 *
 * Os formatadores devolvem `{ value, unit, formatted }` para que o componente
 * possa montar o input separando número (editável) e sufixo (chip estático).
 */
import { G, N_PER_KGF, N_PER_TONF } from './utils'
import type { UnitSystem } from '@/store/units'

// ─────────────────────────────────────────────────────────────────────
// Quantidades suportadas
// ─────────────────────────────────────────────────────────────────────

export type Quantity =
  | 'force'         // T_fl, T_anchor, MBL, EA — em N (SI) ou te (metric)
  | 'force_per_m'   // wet/dry weight — em N/m (SI) ou kgf/m (metric)

/** Unidades concretas que mostramos no input/display. */
export type Unit = 'N' | 'kN' | 'te' | 'N/m' | 'kgf/m'

// ─────────────────────────────────────────────────────────────────────
// Resolução de unidade conforme sistema escolhido
// ─────────────────────────────────────────────────────────────────────

/**
 * Decide a unidade canônica para um par (quantidade, sistema). No metric,
 * forças usam **te** sempre (convenção QMoor) e força por metro usa **kgf/m**.
 * No SI, ambos ficam em **N** ou **N/m**, sem otimização automática para kN
 * (mantém uma única unidade simples e previsível).
 */
export function unitFor(q: Quantity, system: UnitSystem): Unit {
  if (system === 'metric') {
    return q === 'force' ? 'te' : 'kgf/m'
  }
  return q === 'force' ? 'N' : 'N/m'
}

// ─────────────────────────────────────────────────────────────────────
// Conversões SI ↔ unidade
// ─────────────────────────────────────────────────────────────────────

/** Valor SI → valor numérico na unidade-alvo (sem formatação). */
export function siToUnit(siValue: number, unit: Unit): number {
  switch (unit) {
    case 'N':
    case 'N/m':
      return siValue
    case 'kN':
      return siValue / 1000
    case 'te':
      return siValue / N_PER_TONF
    case 'kgf/m':
      return siValue / N_PER_KGF
  }
}

/** Valor numérico em uma unidade → valor SI. */
export function unitToSi(value: number, unit: Unit): number {
  switch (unit) {
    case 'N':
    case 'N/m':
      return value
    case 'kN':
      return value * 1000
    case 'te':
      return value * N_PER_TONF
    case 'kgf/m':
      return value * N_PER_KGF
  }
}

// ─────────────────────────────────────────────────────────────────────
// Formatadores compactos para display de RESULTADOS (cards, hover, etc)
// ─────────────────────────────────────────────────────────────────────

/**
 * Formata força em pt-BR. Em metric, usa **te** com 2 casas; se < 0,1 te
 * (≈100 kgf), cai para **kN** com 2 casas para evitar `0,00 te`. Em SI usa
 * sempre N.
 */
export function fmtForce(siValue: number, system: UnitSystem): string {
  if (system === 'metric') {
    const te = siValue / N_PER_TONF
    if (Math.abs(te) >= 0.1) {
      return `${te.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} te`
    }
    const kn = siValue / 1000
    return `${kn.toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} kN`
  }
  return `${siValue.toLocaleString('pt-BR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })} N`
}

/** Força por metro (peso submerso/seco). */
export function fmtForcePerM(siValue: number, system: UnitSystem): string {
  if (system === 'metric') {
    const kgfm = siValue / N_PER_KGF
    return `${kgfm.toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} kgf/m`
  }
  return `${siValue.toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} N/m`
}

/**
 * Devolve um par "primário + secundário" (ex.: `61,18 te ≈ 600,04 kN`).
 * Quando o sistema é metric, mostra te em primeiro plano e kN como secundário;
 * em SI, N principal e kN secundário.
 */
export function fmtForcePair(
  siValue: number,
  system: UnitSystem,
): { primary: string; secondary: string } {
  if (system === 'metric') {
    const te = siValue / N_PER_TONF
    const kn = siValue / 1000
    return {
      primary: `${te.toLocaleString('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })} te`,
      secondary: `${kn.toLocaleString('pt-BR', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })} kN`,
    }
  }
  const kn = siValue / 1000
  return {
    primary: `${siValue.toLocaleString('pt-BR', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })} N`,
    secondary: `${kn.toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} kN`,
  }
}

/**
 * Constante usada também no QMoor 0.8.5 ("Metric"): 1 te = 9,80665 kN.
 * Exportada para os componentes que precisam montar tooltips sobre
 * a convenção em uso.
 */
export const G_USED_FOR_CONVERSION = G
