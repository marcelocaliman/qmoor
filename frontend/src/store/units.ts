import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Sistemas de unidades suportados na UI.
 *
 * - `metric`: convenção offshore brasileira (kgf/m, te, kN). Default — combina
 *   com o QMoor 0.8.5 e os memoriais que o usuário lê no dia a dia.
 * - `si`:     SI puro (N/m, N). Útil para depurar o solver, que opera em SI
 *   internamente, e para integrações com ferramentas que usam SI explícito.
 *
 * O estado do form sempre persiste em SI; este store só afeta DISPLAY e
 * INPUT do usuário, com conversão nas bordas.
 */
export type UnitSystem = 'metric' | 'si'

interface UnitsState {
  system: UnitSystem
  setSystem: (s: UnitSystem) => void
  toggle: () => void
}

export const useUnitsStore = create<UnitsState>()(
  persist(
    (set, get) => ({
      system: 'metric',
      setSystem: (s) => set({ system: s }),
      toggle: () => set({ system: get().system === 'metric' ? 'si' : 'metric' }),
    }),
    { name: 'qmoor-units' },
  ),
)
