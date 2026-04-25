"""Solver de catenária elástica para linhas de ancoragem offshore (QMoor)."""

# Versão do solver — incrementada quando há mudança de comportamento
# numérico ou estrutural que muda os resultados. Persistida em
# SolverResult.solver_version para auditoria de execuções antigas.
#
# Histórico:
#   1.0.0 — F1b/F2 inicial: catenária elástica, seabed, fully suspended e
#           touchdown. Validado contra MoorPy nos 9 BCs.
#   1.1.0 — F3+F4: aceita startpoint_depth > 0 (fairlead afundado) com
#           drop efetivo h − startpoint_depth. Novo módulo laid_line para
#           drop = 0. Trava de strain > 5% como INVALID_CASE. Adiciona
#           water_depth e startpoint_depth em SolverResult.
SOLVER_VERSION = "1.1.0"

__all__ = ["SOLVER_VERSION"]
