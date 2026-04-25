"""
Camada multi-segmento (F5.1) — linha composta heterogênea.

Suporta linhas formadas por uma sequência de N segmentos com propriedades
distintas (w_i, EA_i, MBL_i, L_i). Caso clássico em projetos reais:
chain pendant inferior + wire central + chain pendant superior.

Convenção de ordem
------------------
Segmentos são indexados de 0 (mais próximo da âncora) a N-1 (mais próximo
do fairlead). A ordem importa para o cálculo do touchdown e da
distribuição de tração.

Modelo físico
-------------
Para o trecho TOTALMENTE SUSPENSO (sem touchdown), a tração horizontal H
é constante em toda a linha (não há força externa horizontal nas junções).
A tração vertical V cresce monotonamente do anchor até o fairlead com a
soma das contribuições de peso w_i × L_i de cada segmento.

Em cada segmento i, a curva é localmente uma catenária com parâmetro
a_i = H / w_i. Como H é o mesmo, w_i diferentes produzem catenárias
diferentes — é exatamente isso que dá a "quebra" visual entre segmentos.

Discrete cálculo: usamos a variável V (componente vertical) como parâmetro
global e integramos cada segmento com sua catenária local:

  s_i = V_local_i / w_i  (arc length na catenária local do segmento i)
  Δx_i = a_i · [asinh(s_end_i / a_i) − asinh(s_start_i / a_i)]
  Δy_i = sqrt(a_i² + s_end_i²) − sqrt(a_i² + s_start_i²)

X_total = Σ Δx_i
h_total = Σ Δy_i

Modos
-----
- TENSION (T_fl dado): incógnita única H. V_fl é determinado por
  V_fl = sqrt(T_fl² − H²); V_anchor = V_fl − Σ w_i·L_i. Se V_anchor < 0,
  o caso requer touchdown — caímos no caminho com seabed.
  Equação: brentq sobre H para satisfazer h_total(H) = h.

- RANGE (X_total dado): 2 incógnitas (H, V_anchor). 2 equações
  (h_total = h, X_total = X). Resolvido via scipy.optimize.fsolve com
  chute inicial vindo do caso single-segmento equivalente.

Touchdown
---------
F5.1 suporta touchdown apenas no segmento 0 (mais próximo da âncora).
Convenção offshore (pendant inferior em chain): é o segmento que toca
o fundo. Para casos onde o touchdown caia em segmentos intermediários,
o resultado é INVALID_CASE com mensagem orientadora.

Atrito (μ) atua apenas sobre o segmento 0:
  T_anchor = T_touchdown − μ · w_0 · L_g

Elasticidade
------------
Iteração ponto-fixo multidimensional. Para cada segmento i:
  L_eff_i = L_i × (1 + T_mean_i / EA_i)
onde T_mean_i é a tensão média no segmento i (computada na geometria
rígida com os L_eff atuais). Itera até ||L_eff_new − L_eff_old||_∞ <
config.elastic_tolerance × max(L_i), ou esgota max_elastic_iter.

Validação
---------
Casos de benchmark BC-MS-01..BC-MS-05 em test_multi_segment.py — chain
pendant + wire + chain pendant, polyester + chain, etc. Tolerância
geometria 0,5 % e força 1 % vs. MoorPy quando suportado, senão validação
analítica (continuidade nas junções, conservação de H).
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.optimize import brentq, fsolve

from .types import (
    ConvergenceStatus,
    LineAttachment,
    LineSegment,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


def _signed_force(att: LineAttachment) -> float:
    """
    Converte LineAttachment em força líquida signada aplicada à V acumulada
    na junção: clump_weight tende a aumentar V (peso → puxa para baixo);
    buoy tende a diminuir V (empuxo → empurra para cima).
    """
    if att.kind == "buoy":
        return -att.submerged_force
    return att.submerged_force  # clump_weight ou default


# ==============================================================================
# Integração de geometria com H e V_anchor dados
# ==============================================================================


def _integrate_segments(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    H: float,
    V_anchor: float,
    attachments: Sequence[LineAttachment] = (),
    n_points_per_segment: int = 50,
) -> dict:
    """
    Integra a catenária ao longo de uma sequência de segmentos suspensos.

    Para cada segmento i, parametriza a catenária local pela arc length s_i
    medida no vértice virtual local (s_i = V_local / w_i). H define o
    parâmetro a_i = H/w_i.

    Attachments (boias/clumps, F5.2) aplicam saltos em V_local nas junções
    entre segmentos: V_local += signed_force(att) imediatamente antes de
    iniciar a integração do segmento seguinte. (x, y) ficam contínuos; a
    inclinação muda no kink.

    Retorna dict com:
      X_total, h_total, V_fairlead, T_fairlead, T_anchor,
      coords_x[n], coords_y[n], tension_magnitude[n], tension_x[n],
      tension_y[n], boundaries[N+1] (índices em coords[] onde cada segmento
      começa/termina), T_mean_per_segment[N].

    Os coords são em frame anchor-fixo (anchor em (0, 0)).
    """
    if H <= 0:
        raise ValueError(f"H={H} deve ser positivo")
    N = len(segments)
    if N == 0 or len(L_effs) != N:
        raise ValueError("segments e L_effs devem ter mesmo tamanho não-vazio")

    coords_x: list[float] = []
    coords_y: list[float] = []
    tension_mag: list[float] = []
    tension_x: list[float] = []
    tension_y: list[float] = []
    boundaries: list[int] = []
    t_mean_per_seg: list[float] = []

    # Pré-tabela: força signada por junção (índice da junção = posição
    # entre segmento i e i+1, que é também o número da junção). Junções
    # válidas: 0 .. N-2.
    junction_force: dict[int, float] = {}
    for att in attachments:
        if att.position_index < 0 or att.position_index >= len(segments) - 1:
            raise ValueError(
                f"Attachment '{att.name or att.kind}' tem position_index="
                f"{att.position_index} fora do range válido "
                f"[0, {len(segments) - 2}] para {len(segments)} segmentos."
            )
        junction_force[att.position_index] = (
            junction_force.get(att.position_index, 0.0) + _signed_force(att)
        )

    x_acc = 0.0
    y_acc = 0.0
    V_local = V_anchor  # vai acumulando peso suspenso a cada segmento

    boundaries.append(0)
    for i, (seg, L_i) in enumerate(zip(segments, L_effs)):
        # Aplica salto da junção anterior (i-1 → i): att com position_index
        # = i-1 atua AO ENTRAR no segmento i. Para i=0, sem efeito.
        if i > 0 and (i - 1) in junction_force:
            V_local = V_local + junction_force[i - 1]
            if V_local < 0:
                # V negativo significa vértice virtual ABAIXO da junção:
                # geometria fisicamente inviável (linha "voltaria para
                # baixo" depois de subir, sem mais peso suspenso).
                raise ValueError(
                    f"Attachment na junção {i - 1} produz V_local={V_local:.1f}"
                    " < 0 — empuxo excede peso suspenso acumulado. "
                    "Reduza o empuxo da boia ou troque a posição."
                )

        w_i = seg.w
        a_i = H / w_i
        s_start = V_local / w_i
        s_end = (V_local + w_i * L_i) / w_i

        # Discretiza a arc length física do segmento (s_phys ∈ [0, L_i])
        n = max(2, n_points_per_segment)
        s_phys = np.linspace(0.0, L_i, n)
        s_local = s_start + s_phys  # = s_start + s_phys (mesmo passo)

        # Posições locais (catenária com parâmetro a_i, vértice virtual local)
        x_local = a_i * (np.arcsinh(s_local / a_i) - math.asinh(s_start / a_i))
        y_local = (
            np.sqrt(a_i * a_i + s_local * s_local)
            - math.sqrt(a_i * a_i + s_start * s_start)
        )

        # Translada para o frame global (acumula offset do final do segmento anterior)
        seg_x = x_acc + x_local
        seg_y = y_acc + y_local

        # Tração: T(s) = w_i · sqrt(a_i² + s²); H constante; V = w_i · s
        T_seg = w_i * np.sqrt(a_i * a_i + s_local * s_local)
        Tx_seg = np.full_like(T_seg, H)
        Ty_seg = w_i * s_local

        # Concatena (evita duplicar a junção: pulo o primeiro ponto exceto no segmento 0)
        if i == 0:
            coords_x.extend(seg_x.tolist())
            coords_y.extend(seg_y.tolist())
            tension_mag.extend(T_seg.tolist())
            tension_x.extend(Tx_seg.tolist())
            tension_y.extend(Ty_seg.tolist())
        else:
            coords_x.extend(seg_x[1:].tolist())
            coords_y.extend(seg_y[1:].tolist())
            tension_mag.extend(T_seg[1:].tolist())
            tension_x.extend(Tx_seg[1:].tolist())
            tension_y.extend(Ty_seg[1:].tolist())

        boundaries.append(len(coords_x) - 1)

        # Tensão média no segmento (para correção elástica)
        T_start = w_i * math.sqrt(a_i * a_i + s_start * s_start)
        T_end = w_i * math.sqrt(a_i * a_i + s_end * s_end)
        t_mean_per_seg.append((T_start + T_end) / 2.0)

        x_acc = seg_x[-1].item()
        y_acc = seg_y[-1].item()
        V_local = V_local + w_i * L_i

    X_total = x_acc
    h_total = y_acc
    V_fairlead = V_local
    T_anchor = math.sqrt(H * H + V_anchor * V_anchor)
    T_fairlead = math.sqrt(H * H + V_fairlead * V_fairlead)

    return {
        "X_total": X_total,
        "h_total": h_total,
        "V_anchor": V_anchor,
        "V_fairlead": V_fairlead,
        "T_fairlead": T_fairlead,
        "T_anchor": T_anchor,
        "H": H,
        "coords_x": coords_x,
        "coords_y": coords_y,
        "tension_magnitude": tension_mag,
        "tension_x": tension_x,
        "tension_y": tension_y,
        "boundaries": boundaries,
        "T_mean_per_segment": t_mean_per_seg,
    }


# ==============================================================================
# Modo Tension — totalmente suspenso
# ==============================================================================


def _solve_suspended_tension(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    h: float,
    T_fl: float,
    config: SolverConfig,
    attachments: Sequence[LineAttachment] = (),
) -> dict:
    """
    Resolve modo Tension para multi-segmento totalmente suspenso.

    V_fl está determinado por T_fl: V_fl = sqrt(T_fl² − H²). Daí
    V_anchor = V_fl − Σ w_i L_i − Σ F_attachments. Brentq em H para
    h_total(H) = h.

    Levanta ValueError se a busca não consegue bracket — caso provável de
    touchdown (V_anchor negativo) ou geometria infactível.
    """
    sum_wL = sum(s.w * L for s, L in zip(segments, L_effs))
    sum_F = sum(_signed_force(att) for att in attachments)
    # Total de "peso suspenso" considerando attachments. Sum pode ser
    # negativa se há mais empuxo (boias) do que peso submerso (caso
    # patológico que vai cair em V_anchor inviável).
    sum_total = sum_wL + sum_F

    def residual(H: float) -> float:
        V_fl_sq = T_fl * T_fl - H * H
        if V_fl_sq < 0:
            return float("inf")
        V_fl = math.sqrt(V_fl_sq)
        V_anchor = V_fl - sum_total
        if V_anchor < 0:
            # Vértice virtual estaria além do anchor: requer touchdown
            return float("inf")
        try:
            res = _integrate_segments(
                segments, L_effs, H, V_anchor, attachments=attachments,
            )
        except ValueError:
            return float("inf")
        return res["h_total"] - h

    # Bracket: H ∈ (0, H_max] onde H_max = sqrt(T_fl² − sum_total²) é o
    # limite físico em que V_anchor → 0 (touchdown iminente). Acima disso,
    # V_anchor ficaria negativo → caso requer touchdown.
    if sum_total <= 0:
        raise ValueError(
            f"Somatório de peso suspenso (Σw·L + Σ F_attachments) = "
            f"{sum_total:.1f} N <= 0: empuxo das boias excede o peso da "
            "linha. Geometria invertida não suportada."
        )
    H_max_sq = T_fl * T_fl - sum_total * sum_total
    if H_max_sq <= 0:
        raise ValueError(
            f"T_fl={T_fl:.1f} N <= soma de pesos suspensos {sum_total:.1f} N "
            "(incluindo attachments): linha não consegue sustentar o peso "
            "pendurado. Reduza algum w·L, aumente T_fl, ou troque clump "
            "weights por boias."
        )
    H_max = math.sqrt(H_max_sq)

    # Em H pequeno: a_i = H/w_i pequeno, catenária muito acentuada, h_total
    # grande. Em H próximo de H_max: V_anchor → 0, h_total → h_critico
    # (valor para touchdown iminente). Se h_critico > h_target, todo o
    # caminho está OK; senão o caso exige touchdown.
    H_lo = max(1.0, H_max * 1e-4)
    H_hi = H_max * (1.0 - 1e-6)  # ε abaixo de H_max para evitar V_anchor=0 exato
    f_lo = residual(H_lo)
    f_hi = residual(H_hi)

    if f_lo == float("inf") or f_hi == float("inf") or f_lo * f_hi >= 0:
        raise ValueError(
            f"Bracket de H inválido para fully suspended (f_lo={f_lo}, "
            f"f_hi={f_hi}). Provável caso de touchdown — multi-segmento "
            "com touchdown ainda não suportado nesta sub-fase."
        )

    H_sol = brentq(
        residual, H_lo, H_hi,
        xtol=1e-3, rtol=1e-6, maxiter=config.max_brent_iter,
    )
    V_fl = math.sqrt(T_fl * T_fl - H_sol * H_sol)
    V_anchor = V_fl - sum_total
    return _integrate_segments(
        segments, L_effs, H_sol, V_anchor, attachments=attachments,
    )


# ==============================================================================
# Modo Range — totalmente suspenso (2 incógnitas)
# ==============================================================================


def _solve_suspended_range(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    h: float,
    X: float,
    config: SolverConfig,
    attachments: Sequence[LineAttachment] = (),
) -> dict:
    """
    Modo Range com multi-segmento: fsolve sobre (H, V_anchor).

    Chute inicial: trata o conjunto como um segmento equivalente com
    w_eq = w_médio ponderado por L. Isso converge bem para os casos
    típicos onde os pesos não diferem em mais de uma ordem de grandeza.
    """
    sum_L = sum(L_effs)
    w_eq = sum(s.w * L for s, L in zip(segments, L_effs)) / sum_L
    # Para single-segmento equivalente, já temos a solução analítica
    # (ver catenary._solve_suspended_range_mode). Para chute, usamos
    # estimativa simplificada: a_eq tal que sinh(X/a_eq) = L_eq/a_eq
    # e cosh(X/a_eq) - 1 = h/a_eq... aproximamos por (X²+h²)/(2h).
    a_eq_guess = max(1.0, (X * X - h * h) / (2.0 * h)) if X > h else max(1.0, h)
    H_guess = w_eq * a_eq_guess
    V_anchor_guess = max(0.0, w_eq * sum_L * 0.3)  # 30% da catenária no anchor

    def system(vars: np.ndarray) -> np.ndarray:
        H, V_anchor = vars
        if H <= 0 or V_anchor < 0:
            return np.array([1e9, 1e9])
        try:
            res = _integrate_segments(
                segments, L_effs, H, V_anchor, attachments=attachments,
            )
        except ValueError:
            return np.array([1e9, 1e9])
        return np.array(
            [res["h_total"] - h, res["X_total"] - X],
        )

    sol, info, ier, _ = fsolve(
        system, np.array([H_guess, V_anchor_guess]),
        full_output=True, xtol=1e-6, maxfev=config.max_brent_iter * 4,
    )
    if ier != 1:
        raise ValueError(
            "fsolve não convergiu para multi-segmento no modo Range. "
            "Verifique se a geometria é factível (X compatível com sum L)."
        )
    H_sol, V_anchor_sol = sol
    return _integrate_segments(
        segments, L_effs, H_sol, V_anchor_sol, attachments=attachments,
    )


# ==============================================================================
# Iteração elástica multi-dimensional
# ==============================================================================


def _solve_rigid_multi(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    h: float,
    mode: SolutionMode,
    input_value: float,
    config: SolverConfig,
    attachments: Sequence[LineAttachment] = (),
) -> dict:
    """Roteia para o modo apropriado e retorna o dicionário de resultados."""
    if mode == SolutionMode.TENSION:
        return _solve_suspended_tension(
            segments, L_effs, h, float(input_value), config, attachments,
        )
    elif mode == SolutionMode.RANGE:
        return _solve_suspended_range(
            segments, L_effs, h, float(input_value), config, attachments,
        )
    else:
        raise ValueError(f"modo inválido: {mode}")


def _integrate_segments_with_grounded(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    H: float,
    L_g_0: float,
    slope_rad: float,
    mu: float,
    attachments: Sequence[LineAttachment] = (),
    n_points_per_segment: int = 50,
) -> dict:
    """
    Multi-segmento com trecho grounded em rampa (F5.3 + F5.1 + F5.2).

    Trecho grounded: parte do segmento 0 (comprimento L_g_0) apoiada no
    seabed inclinado de inclinação `slope_rad`. Trecho suspenso: resto
    do segmento 0 (L_0 − L_g_0) + segmentos 1..N-1 inteiros, todos
    integrados como catenárias compostas (H constante).

    Tangência no touchdown: catenária do segmento 0 entra no touchdown
    com inclinação local = slope_rad (encaixe suave na rampa).

    Attachments (F5.3.y P1): se fornecidos, aplicam saltos em V_local
    nas junções entre segmentos suspensos (mesmas regras da F5.2).
    Attachment com `position_index = 0` (junção entre seg 0 e seg 1)
    é aplicado APÓS a integração do trecho suspenso do segmento 0,
    antes do segmento 1. Tangência no touchdown não é afetada por
    attachments (eles ficam acima do touchdown na linha).
    """
    if H <= 0:
        raise ValueError(f"H={H} deve ser > 0")
    if L_g_0 < 0 or L_g_0 > L_effs[0] + 1e-6:
        raise ValueError(
            f"L_g_0={L_g_0:.2f} fora do range [0, L_0={L_effs[0]:.2f}]"
        )

    m = math.tan(slope_rad)
    u = math.asinh(m)
    sqrt_1pm2 = math.sqrt(1.0 + m * m)
    L_g_0 = max(0.0, L_g_0)
    x_td = L_g_0 / sqrt_1pm2 if sqrt_1pm2 > 0 else 0.0
    y_td = m * x_td

    coords_x: list[float] = []
    coords_y: list[float] = []
    tension_mag: list[float] = []
    tension_x: list[float] = []
    tension_y: list[float] = []
    boundaries: list[int] = [0]
    t_mean_per_seg: list[float] = []

    # Trecho grounded (parte do segmento 0)
    if L_g_0 > 0:
        n_g = max(2, int(round(n_points_per_segment * L_g_0 / L_effs[0])))
        x_g = np.linspace(0.0, x_td, n_g)
        y_g = m * x_g
        # Tração: T_anchor → T_touchdown linear ao longo da rampa
        T_td = math.sqrt(H * H + (H * m) ** 2)  # = H·sqrt(1+m²)
        T_anc = max(
            0.0,
            T_td - mu * segments[0].w * math.cos(slope_rad) * L_g_0
            - segments[0].w * math.sin(slope_rad) * L_g_0,
        )
        T_g_arr = np.linspace(T_anc, T_td, n_g)
        Tx_g = T_g_arr * math.cos(slope_rad)
        Ty_g = T_g_arr * math.sin(slope_rad)
        coords_x.extend(x_g.tolist())
        coords_y.extend(y_g.tolist())
        tension_mag.extend(T_g_arr.tolist())
        tension_x.extend(Tx_g.tolist())
        tension_y.extend(Ty_g.tolist())
        # T_mean do trecho grounded (parte do segmento 0)
        t_mean_grounded = (T_anc + T_td) / 2.0

    # Trecho suspenso: começa no touchdown (ou no anchor se L_g_0=0).
    # Entrada do segmento 0 suspenso:
    x_acc = x_td
    y_acc = y_td
    # V_local no início do trecho suspenso do segmento 0
    if L_g_0 > 0:
        # Touchdown: V_local = H·m (tangente m, sinh(asinh(m))=m)
        V_local = H * m
    else:
        # Sem grounded: entrada do segmento 0 = anchor com algum V_anchor
        # No multi sem touchdown a função de fora calcula V_anchor; mas
        # aqui assumimos touchdown imminente: V_anchor = 0 (caso slope=0)
        # ou V_anchor = H·m (slope ≠ 0, vértice virtual no anchor).
        # Para o caller chamando com L_g_0 = 0 e slope ≠ 0, o vértice
        # está EXATAMENTE no anchor (touchdown coincide com anchor).
        V_local = H * m

    L_0_suspended = L_effs[0] - L_g_0

    # Pré-tabela de força signada por junção (mesma regra da F5.2).
    junction_force: dict[int, float] = {}
    for att in attachments:
        if att.position_index < 0 or att.position_index >= len(segments) - 1:
            raise ValueError(
                f"Attachment '{att.name or att.kind}' tem position_index="
                f"{att.position_index} fora do range válido "
                f"[0, {len(segments) - 2}] para {len(segments)} segmentos."
            )
        junction_force[att.position_index] = (
            junction_force.get(att.position_index, 0.0) + _signed_force(att)
        )

    for i, (seg, L_i_full) in enumerate(zip(segments, L_effs)):
        # Aplica salto da junção anterior (i-1 → i) — mesma lógica da
        # função sem grounded. position_index = i-1 atua AO ENTRAR no
        # segmento i. Salto é aplicado em V_local antes da integração.
        if i > 0 and (i - 1) in junction_force:
            V_local = V_local + junction_force[i - 1]
            if V_local < 0:
                raise ValueError(
                    f"Attachment na junção {i - 1} produz V_local="
                    f"{V_local:.1f} < 0 — empuxo excede peso suspenso "
                    "acumulado."
                )

        # Para o segmento 0, usamos apenas L_0_suspended (resto após grounded)
        L_eff_seg = L_0_suspended if i == 0 else L_i_full
        if L_eff_seg < 1e-9:
            # Segmento 0 inteiramente grounded — pula
            boundaries.append(len(coords_x) - 1)
            t_mean_per_seg.append(
                t_mean_grounded if i == 0 and L_g_0 > 0 else 0.0
            )
            continue
        w_i = seg.w
        a_i = H / w_i
        s_start = V_local / w_i
        s_end = (V_local + w_i * L_eff_seg) / w_i

        n = max(2, n_points_per_segment)
        s_phys = np.linspace(0.0, L_eff_seg, n)
        s_local = s_start + s_phys
        # Coordenadas locais relativas ao vértice virtual do segmento i.
        # asinh(s/a) − asinh(s_start/a) gives x relativo; idem para y.
        x_local = a_i * (np.arcsinh(s_local / a_i) - math.asinh(s_start / a_i))
        y_local = (
            np.sqrt(a_i * a_i + s_local * s_local)
            - math.sqrt(a_i * a_i + s_start * s_start)
        )
        seg_x = x_acc + x_local
        seg_y = y_acc + y_local

        T_seg = w_i * np.sqrt(a_i * a_i + s_local * s_local)
        Tx_seg = np.full_like(T_seg, H)
        Ty_seg = w_i * s_local

        # Concatena: o primeiro ponto suspenso coincide com o fim do trecho
        # anterior (touchdown ou junção). Pulamos para evitar duplicação.
        if len(coords_x) > 0 and i == 0 and L_g_0 > 0:
            coords_x.extend(seg_x[1:].tolist())
            coords_y.extend(seg_y[1:].tolist())
            tension_mag.extend(T_seg[1:].tolist())
            tension_x.extend(Tx_seg[1:].tolist())
            tension_y.extend(Ty_seg[1:].tolist())
        elif i == 0 and L_g_0 == 0:
            coords_x.extend(seg_x.tolist())
            coords_y.extend(seg_y.tolist())
            tension_mag.extend(T_seg.tolist())
            tension_x.extend(Tx_seg.tolist())
            tension_y.extend(Ty_seg.tolist())
        else:
            # Junção entre segmentos i-1 e i
            coords_x.extend(seg_x[1:].tolist())
            coords_y.extend(seg_y[1:].tolist())
            tension_mag.extend(T_seg[1:].tolist())
            tension_x.extend(Tx_seg[1:].tolist())
            tension_y.extend(Ty_seg[1:].tolist())

        boundaries.append(len(coords_x) - 1)

        # Tração média no segmento i (na parte suspensa, para correção elástica)
        T_st = w_i * math.sqrt(a_i * a_i + s_start * s_start)
        T_en = w_i * math.sqrt(a_i * a_i + s_end * s_end)
        if i == 0 and L_g_0 > 0:
            # Média ponderada: grounded (linear) e suspended
            T_mean_susp = (T_st + T_en) / 2.0
            t_mean_per_seg.append(
                (t_mean_grounded * L_g_0 + T_mean_susp * L_eff_seg) / L_effs[0]
            )
        else:
            t_mean_per_seg.append((T_st + T_en) / 2.0)

        x_acc = float(seg_x[-1])
        y_acc = float(seg_y[-1])
        V_local = V_local + w_i * L_eff_seg

    X_total = x_acc
    h_total = y_acc
    V_fairlead = V_local
    T_fairlead = math.sqrt(H * H + V_fairlead * V_fairlead)
    if L_g_0 > 0:
        T_anchor = max(
            0.0,
            math.sqrt(H * H + (H * m) ** 2)
            - mu * segments[0].w * math.cos(slope_rad) * L_g_0
            - segments[0].w * math.sin(slope_rad) * L_g_0,
        )
        V_anchor = 0.0  # entra no grounded; tração total na rampa é T_anchor (vetorial)
    else:
        T_anchor = math.sqrt(H * H + (H * m) ** 2)
        V_anchor = H * m

    return {
        "X_total": X_total,
        "h_total": h_total,
        "V_anchor": V_anchor,
        "V_fairlead": V_fairlead,
        "T_fairlead": T_fairlead,
        "T_anchor": T_anchor,
        "H": H,
        "L_g_0": L_g_0,
        "x_td": x_td,
        "y_td": y_td,
        "coords_x": coords_x,
        "coords_y": coords_y,
        "tension_magnitude": tension_mag,
        "tension_x": tension_x,
        "tension_y": tension_y,
        "boundaries": boundaries,
        "T_mean_per_segment": t_mean_per_seg,
    }


def _solve_multi_sloped(
    segments: Sequence[LineSegment],
    L_effs: Sequence[float],
    h: float,
    mode: SolutionMode,
    input_value: float,
    mu: float,
    slope_rad: float,
    config: SolverConfig,
    attachments: Sequence[LineAttachment] = (),
) -> dict:
    """
    Multi-segmento com touchdown na rampa: fsolve 2D sobre (H, L_g_0).

    Modo Tension: 2 equações
      - T_fl_calc = T_fl_target
      - h_total = h
    Modo Range: 2 equações
      - X_total = X_target
      - h_total = h
    """
    L_0 = L_effs[0]
    sum_wL_higher = sum(s.w * L for s, L in zip(segments[1:], L_effs[1:]))
    m = math.tan(slope_rad)

    # Pre-check de viabilidade: peso submerso total (linha + attachments)
    # deve ser positivo, senão a geometria seria invertida (boias > peso).
    sum_wL = sum(s.w * L for s, L in zip(segments, L_effs))
    sum_F = sum(_signed_force(att) for att in attachments)
    sum_total = sum_wL + sum_F
    if sum_total <= 0:
        raise ValueError(
            f"Somatório de peso suspenso (Σw·L + Σ F_attachments) = "
            f"{sum_total:.1f} N <= 0: empuxo das boias excede o peso da "
            "linha. Geometria invertida não suportada."
        )

    def F(vars: np.ndarray) -> np.ndarray:
        H, L_g_0 = vars
        if H <= 0 or L_g_0 < 0 or L_g_0 > L_0 - 1e-6:
            return np.array([1e9, 1e9])
        try:
            res = _integrate_segments_with_grounded(
                segments, L_effs, H, L_g_0, slope_rad, mu,
                attachments=attachments,
            )
        except ValueError:
            return np.array([1e9, 1e9])
        if mode == SolutionMode.TENSION:
            return np.array([res["T_fairlead"] - float(input_value), res["h_total"] - h])
        else:
            return np.array([res["X_total"] - float(input_value), res["h_total"] - h])

    # Chute inicial: assume L_g_0 ≈ 30% do segmento 0; H estimado da
    # solução horizontal análoga.
    L_g_init = 0.3 * L_0
    if mode == SolutionMode.TENSION:
        H_init = max(1.0, float(input_value) - segments[0].w * h)
    else:
        # Para Range, estima H a partir de geometria simples
        H_init = max(1.0, segments[0].w * (float(input_value) ** 2 + h * h) / (2 * h) / 5)

    sol, _info, ier, _ = fsolve(
        F, np.array([H_init, L_g_init]),
        full_output=True, xtol=1e-9, maxfev=300,
    )
    if ier != 1:
        raise ValueError(
            "fsolve não convergiu para multi-segmento + slope com touchdown. "
            "Verifique se a configuração tem touchdown viável no segmento 0."
        )
    H_sol, L_g_sol = sol
    return _integrate_segments_with_grounded(
        segments, L_effs, H_sol, L_g_sol, slope_rad, mu,
        attachments=attachments,
    )


def solve_multi_segment(
    segments: Sequence[LineSegment],
    h: float,
    mode: SolutionMode,
    input_value: float,
    mu: float = 0.0,
    config: SolverConfig | None = None,
    attachments: Sequence[LineAttachment] = (),
    slope_rad: float = 0.0,
) -> SolverResult:
    """
    Solver multi-segmento (F5.1). Ver docstring do módulo.

    Pre-condições:
      - len(segments) >= 1 (mas se 1, o caller normalmente despacha para
        o solver single-segmento; aceitamos 1 aqui também por simetria)
      - h > 0 (drop vertical efetivo)
      - input_value > 0
      - todos os segmentos com w, L, EA, MBL > 0

    Retorna SolverResult com status CONVERGED ou levanta ValueError em
    casos infactíveis.
    """
    if config is None:
        config = SolverConfig()
    if h <= 0:
        raise ValueError(f"h={h} deve ser > 0 para o solver suspenso")
    if not segments:
        raise ValueError("segments vazio")

    # Iteração elástica ponto-fixo: começa com L_eff = L_unstretched.
    L_unstretched = [s.length for s in segments]
    L_effs = list(L_unstretched)

    last_rigid: dict | None = None
    iters_used = 0
    tol = max(s.length for s in segments) * config.elastic_tolerance

    # F5.3.y: detecta dinamicamente se há touchdown no segmento 0.
    # O motor _solve_multi_sloped funciona tanto com slope ≠ 0 quanto
    # com slope = 0 (caso plano). Quando o solver fully-suspended falha
    # ou retorna V_anchor < 0, fazemos fallback para o motor com grounded.
    has_grounded = False

    for it in range(config.max_elastic_iter):
        iters_used = it + 1
        if not has_grounded:
            try:
                rigid_susp = _solve_rigid_multi(
                    segments, L_effs, h, mode, input_value, config, attachments,
                )
                if rigid_susp.get("V_anchor", 0.0) >= 0:
                    rigid = rigid_susp
                else:
                    # V_anchor < 0 → exige touchdown. Despacha para grounded.
                    has_grounded = True
                    rigid = _solve_multi_sloped(
                        segments, L_effs, h, mode, input_value,
                        mu, slope_rad, config, attachments,
                    )
            except ValueError:
                # Solver fully-suspended falhou (não conseguiu bracketar):
                # provavelmente caso de touchdown.
                has_grounded = True
                rigid = _solve_multi_sloped(
                    segments, L_effs, h, mode, input_value,
                    mu, slope_rad, config, attachments,
                )
        else:
            # Já sabemos que há grounded — vai direto.
            rigid = _solve_multi_sloped(
                segments, L_effs, h, mode, input_value,
                mu, slope_rad, config, attachments,
            )
        last_rigid = rigid
        new_L_effs = [
            L_unstretched[i] * (1.0 + rigid["T_mean_per_segment"][i] / segments[i].EA)
            for i in range(len(segments))
        ]
        max_delta = max(abs(new - old) for new, old in zip(new_L_effs, L_effs))
        L_effs = new_L_effs
        if max_delta < tol:
            break

    assert last_rigid is not None
    rigid = last_rigid

    # Sanidade física: strain por segmento — qualquer um > 5 % é implausível.
    for i, (s, Le) in enumerate(zip(segments, L_effs)):
        strain = (Le - s.length) / s.length
        if strain > 0.05:
            raise ValueError(
                f"Segmento {i}: strain {strain * 100:.1f} % > 5 % é "
                "fisicamente implausível. Verifique unidades (EA em N, "
                "w em N/m) e a viabilidade do T_fl pedido."
            )

    # Constrói SolverResult
    sum_L = sum(s.length for s in segments)
    sum_L_eff = sum(L_effs)
    elongation = sum_L_eff - sum_L

    # Utilização: T_fl / MBL_min — o segmento mais fraco governa
    MBL_min = min(s.MBL for s in segments)
    utilization = (
        rigid["T_fairlead"] / MBL_min if MBL_min > 0 else 0.0
    )

    # Ângulos no fairlead e na âncora — atan2(V, H)
    angle_h_fl = math.atan2(rigid["V_fairlead"], rigid["H"])
    if has_grounded:
        # Com touchdown na rampa, o ângulo no anchor segue o slope
        angle_h_an = slope_rad
    else:
        angle_h_an = math.atan2(rigid["V_anchor"], rigid["H"])

    # F5.3.x: separa grounded (no segmento 0) do suspended para o resultado
    L_g_total = rigid.get("L_g_0", 0.0)
    L_susp_total = sum_L_eff - L_g_total

    # Mensagem inclui per-segment strain para auditoria
    strains = [(L_effs[i] - segments[i].length) / segments[i].length for i in range(len(segments))]
    strain_str = ", ".join(f"{s * 100:.3f}%" for s in strains)

    msg_parts = [
        f"Multi-segmento ({len(segments)} segs) convergido em {iters_used} "
        f"iterações elásticas. Strains por segmento: [{strain_str}]."
    ]
    if has_grounded and L_g_total > 0:
        msg_parts.append(
            f"Touchdown na rampa de {math.degrees(slope_rad):.2f}°: "
            f"L_g={L_g_total:.2f} m apoiado no segmento 0."
        )

    return SolverResult(
        status=ConvergenceStatus.CONVERGED,
        message=" ".join(msg_parts),
        coords_x=rigid["coords_x"],
        coords_y=rigid["coords_y"],
        tension_x=rigid["tension_x"],
        tension_y=rigid["tension_y"],
        tension_magnitude=rigid["tension_magnitude"],
        fairlead_tension=rigid["T_fairlead"],
        anchor_tension=rigid["T_anchor"],
        total_horz_distance=rigid["X_total"],
        endpoint_depth=h,
        unstretched_length=sum_L,
        stretched_length=sum_L_eff,
        elongation=elongation,
        total_suspended_length=L_susp_total,
        total_grounded_length=L_g_total,
        dist_to_first_td=rigid.get("x_td") if has_grounded else None,
        angle_wrt_horz_fairlead=angle_h_fl,
        angle_wrt_vert_fairlead=math.pi / 2.0 - angle_h_fl,
        angle_wrt_horz_anchor=angle_h_an,
        angle_wrt_vert_anchor=math.pi / 2.0 - angle_h_an,
        H=rigid["H"],
        iterations_used=iters_used,
        utilization=utilization,
        segment_boundaries=rigid["boundaries"],
    )


__all__ = ["solve_multi_segment"]
