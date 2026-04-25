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
#   1.3.0 — F5.2: attachments pontuais (boias e clump weights) nas junções
#           entre segmentos. V acumulado tem salto na junção; (x,y) contínuo;
#           ângulo da tangente faz quebra (kink). Validação por equilíbrio
#           vertical estendido V_fl − V_anchor = Σw·L_eff + Σ F_attachments.
#   1.4.0 — F5.3: seabed inclinado, entrega parcial (suspended-only).
#   1.4.1 — F5.3.x: pendências resolvidas — touchdown em rampa para modos
#           Tension e Range (single-segmento via fsolve 2D/3D), atrito
#           Coulomb modificado μ·w·cos(θ) ± w·sin(θ), multi-segmento +
#           slope com touchdown no segmento 0 (fsolve 2D em H, L_g_0).
#   1.4.2 — F5.3.y: últimas pendências — attachments + slope suportado
#           (saltos em V nas junções aplicados no integrador grounded);
#           touchdown em multi-segmento SEM slope agora cai no mesmo
#           motor (resolve pendência herdada da F5.1); elasticidade no
#           trecho grounded aplicada via T_mean ponderado entre grounded
#           e suspended dentro do segmento 0.
SOLVER_VERSION = "1.4.2"

__all__ = ["SOLVER_VERSION"]
