import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Helper padrão shadcn: combina clsx + tailwind-merge.
 * Permite `cn('p-2', isActive && 'bg-primary', className)` com override correto.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/**
 * 1 tonelada-força métrica = 9,80665 kN (convenção offshore).
 * Divide força em Newtons por essa constante para obter tf.
 */
export const KGF_PER_N = 1 / 9.80665
export const TONF_PER_N = KGF_PER_N / 1000

/** Formata número como tração em kN (valor em N). */
export function fmtForceKN(valueN: number, digits = 2): string {
  return `${(valueN / 1000).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} kN`
}

/** Apenas o número em toneladas-força, arredondado. Ex: 80.04 */
export function fmtTonfNumber(valueN: number, digits = 1): string {
  return (valueN * TONF_PER_N).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/**
 * Formata força como kN com conversão em toneladas-força discreta.
 * Ex: `{ primary: "785.00 kN", secondary: "≈ 80.0 tf" }`.
 */
export function fmtForcePair(valueN: number, digitsKN = 2, digitsTf = 1) {
  return {
    primary: fmtForceKN(valueN, digitsKN),
    secondary: `≈ ${fmtTonfNumber(valueN, digitsTf)} tf`,
  }
}

/** Formata distância em m (valor em m). */
export function fmtMeters(value: number, digits = 2): string {
  return `${value.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} m`
}

/** Formata número livre com separador pt-BR. */
export function fmtNumber(value: number, digits = 2): string {
  return value.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** Percentual: 0.397 → "39.7%" */
export function fmtPercent(value: number, digits = 1): string {
  return `${(value * 100).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`
}

/** Converte radianos para graus e formata com unidade. */
export function fmtAngleDeg(rad: number, digits = 1): string {
  const deg = (rad * 180) / Math.PI
  return `${deg.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}°`
}

/** Diâmetro formatado em mm (SI → mm comum em catálogo). */
export function fmtDiameterMM(valueM: number, digits = 1): string {
  return `${(valueM * 1000).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} mm`
}
