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
#   1.2.0 — F5.1: linha multi-segmento heterogênea (até 10 segmentos com
#           w/EA/MBL próprios). Novo módulo multi_segment despachado por
#           solve() quando len(segments) > 1. Caso primário fully suspended;
#           touchdown em multi fica para sub-fase futura.
SOLVER_VERSION = "1.2.0"

__all__ = ["SOLVER_VERSION"]
