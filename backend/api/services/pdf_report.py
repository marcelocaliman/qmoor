"""
Geração de relatórios técnicos em PDF (F2.7 + redesign 2026).

Layout profissional de relatório de análise estática para revisão por
engenheiro chefe. Estrutura padrão:

  1. Header — nome, id, timestamp, versão do solver
  2. Disclaimer técnico (Seção 10 Documento A v2.2)
  3. Sumário executivo — caixa colorida com key findings
  4. Configuração / inputs detalhados
  5. Resultados (gráficos + tabelas)
  6. Diagnóstico do solver

Componentes compartilhados entre `build_pdf` (caso individual) e
`build_mooring_system_pdf` (sistema multi-linha) via helpers privados.

Usa reportlab (puro Python) para layout e matplotlib para gráficos.
Backend matplotlib é forçado para 'Agg' (não-interativo).
"""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Optional

# matplotlib precisa de backend não-interativo antes de importar pyplot
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.api.db.models import (
    CaseRecord,
    ExecutionRecord,
    MooringSystemExecutionRecord,
    MooringSystemRecord,
)
from backend.api.routers.health import SOLVER_VERSION
from backend.api.schemas.cases import CaseInput
from backend.api.schemas.mooring_systems import MooringSystemInput
from backend.solver.types import (
    ConvergenceStatus,
    MooringSystemResult,
    SolverResult,
)

# Disclaimer obrigatório — Seção 10 do Documento A v2.2
DISCLAIMER = (
    "Os resultados apresentados são estimativas de análise estática "
    "simplificada e não substituem análise de engenharia realizada com "
    "ferramenta validada, dados certificados, premissas aprovadas e revisão "
    "por responsável técnico habilitado."
)


# ──────────────────────────────────────────────────────────────────────
# Paleta e estilos compartilhados
# ──────────────────────────────────────────────────────────────────────

_BRAND_NAVY = colors.HexColor("#1f4e79")
_BRAND_GRAY = colors.HexColor("#555555")
_BRAND_LIGHT_GRAY = colors.HexColor("#f2f2f2")
_BRAND_BORDER = colors.HexColor("#888888")
_OK_GREEN = colors.HexColor("#2d7a2d")
_WARN_AMBER = colors.HexColor("#d1a200")
_DANGER_RED = colors.HexColor("#b33a3a")
_BROKEN_DARK_RED = colors.HexColor("#8b0000")

# Paleta para multi-segmento e multi-linha (mesma do frontend)
_SEG_PALETTE = [
    "#1E3A5F", "#D97706", "#047857", "#7C3AED", "#BE185D",
]


def _alert_color(alert_level: str) -> colors.Color:
    return {
        "ok": _OK_GREEN,
        "yellow": _WARN_AMBER,
        "red": _DANGER_RED,
        "broken": _BROKEN_DARK_RED,
    }.get(alert_level, colors.black)


def _alert_color_hex(alert_level: str) -> str:
    """Hex string `#rrggbb` para uso em matplotlib (que não aceita
    o formato `0xrrggbb` retornado por `colors.Color.hexval()`)."""
    return {
        "ok": "#2d7a2d",
        "yellow": "#d1a200",
        "red": "#b33a3a",
        "broken": "#8b0000",
    }.get(alert_level, "#000000")


def _alert_label(alert_level: str) -> str:
    return {
        "ok": "OK",
        "yellow": "ATENÇÃO",
        "red": "CRÍTICO",
        "broken": "ROMPIDA",
    }.get(alert_level, alert_level.upper())


def _uplift_color(severity: str) -> colors.Color:
    return {
        "ok": _OK_GREEN,
        "warning": _WARN_AMBER,
        "critical": _DANGER_RED,
    }.get(severity, colors.black)


def _uplift_label(severity: str) -> str:
    return {
        "ok": "OK",
        "warning": "MODERADO",
        "critical": "CRÍTICO",
    }.get(severity, severity.upper())


def _base_table_style() -> TableStyle:
    """Estilo padrão pra tabelas tipo 'inputs' e 'resultados'."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.3, _BRAND_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _BRAND_LIGHT_GRAY]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ])


def _data_table_style() -> TableStyle:
    """Tabelas com muitas linhas/colunas (multi-linha, multi-segmento)."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.25, _BRAND_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _BRAND_LIGHT_GRAY]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


def _build_styles():
    """Cria styles do reportlab uma vez por relatório (idempotente)."""
    styles = getSampleStyleSheet()
    if "HeaderSmall" not in styles.byName:
        styles.add(ParagraphStyle(
            name="HeaderSmall", parent=styles["Normal"],
            fontSize=9, textColor=_BRAND_GRAY,
        ))
    if "DisclaimerBox" not in styles.byName:
        styles.add(ParagraphStyle(
            name="DisclaimerBox", parent=styles["Normal"],
            fontSize=7.5, textColor=colors.HexColor("#606060"),
            borderPadding=6, borderColor=colors.HexColor("#cccccc"),
            borderWidth=0.5, leading=10,
        ))
    if "SectionTitle" not in styles.byName:
        styles.add(ParagraphStyle(
            name="SectionTitle", parent=styles["Heading3"],
            textColor=_BRAND_NAVY, fontSize=12, spaceBefore=8, spaceAfter=4,
        ))
    if "Caption" not in styles.byName:
        styles.add(ParagraphStyle(
            name="Caption", parent=styles["Normal"],
            fontSize=8, textColor=_BRAND_GRAY,
            alignment=1,  # centro
        ))
    return styles


# ──────────────────────────────────────────────────────────────────────
# Header / disclaimer / sumário executivo (compartilhado)
# ──────────────────────────────────────────────────────────────────────


def _header_block(
    title: str, subtitle: str, doc_id: str | int, styles
) -> list:
    now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S %Z")
    out = []
    out.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    out.append(Paragraph(
        f"{subtitle} <font color='#888'>(id {doc_id})</font>",
        styles["Heading3"],
    ))
    out.append(Paragraph(
        f"Gerado em {now} &middot; Solver versão {SOLVER_VERSION}",
        styles["HeaderSmall"],
    ))
    out.append(Spacer(1, 0.3 * cm))
    return out


def _disclaimer_block(styles) -> list:
    return [
        Paragraph("<b>Disclaimer técnico</b>", styles["Heading4"]),
        Paragraph(DISCLAIMER, styles["DisclaimerBox"]),
        Spacer(1, 0.4 * cm),
    ]


def _summary_box_case(result: SolverResult) -> Table:
    """
    Caixa colorida no topo do PDF com key findings do caso. Cor varia
    por alert_level. Pensada pra o engenheiro chefe ver o status do
    caso sem rolar.
    """
    color = _alert_color(result.alert_level.value)
    label = _alert_label(result.alert_level.value)

    # Linha 1 (cabeçalho colorido, branco em fundo color)
    # Linhas seguintes com métricas-chave
    rows = [
        [Paragraph(
            f"<font color='white'><b>STATUS DO CASO &middot; {label}</b></font>",
            ParagraphStyle("_sum_h", fontSize=11, alignment=1),
        )],
        [Paragraph(
            f"<b>Convergência:</b> {result.status.value} &nbsp;&nbsp; "
            f"<b>Alert level:</b> {label} &nbsp;&nbsp; "
            f"<b>Anchor uplift:</b> {_uplift_label(result.anchor_uplift_severity)}",
            ParagraphStyle("_sum_b", fontSize=9, alignment=0, leading=12),
        )],
        [Paragraph(
            f"<b>T_fl:</b> {result.fairlead_tension / 1000:.1f} kN &nbsp;&nbsp; "
            f"<b>Utilização:</b> {result.utilization * 100:.1f}% MBL &nbsp;&nbsp; "
            f"<b>Margem:</b> {(1 - result.utilization) * 100:.1f}%",
            ParagraphStyle("_sum_b2", fontSize=9, alignment=0, leading=12),
        )],
    ]
    t = Table(rows, colWidths=[16 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f8f8")),
        ("BOX", (0, 0), (-1, -1), 0.6, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.3, _BRAND_BORDER),
    ]))
    return t


def _summary_box_msys(result: MooringSystemResult) -> Table:
    """Sumário executivo do sistema multi-linha."""
    color = _alert_color(result.worst_alert_level.value)
    label = _alert_label(result.worst_alert_level.value)

    mag_kn = result.aggregate_force_magnitude / 1000
    n_total = len(result.lines)
    rows = [
        [Paragraph(
            f"<font color='white'><b>STATUS DO SISTEMA &middot; {label}</b></font>",
            ParagraphStyle("_sumh", fontSize=11, alignment=1),
        )],
        [Paragraph(
            f"<b>Linhas convergidas:</b> {result.n_converged} / {n_total} &nbsp;&nbsp; "
            f"<b>Pior alerta:</b> {label} &nbsp;&nbsp; "
            f"<b>Máx utilização:</b> {result.max_utilization * 100:.1f}% MBL",
            ParagraphStyle("_sumb", fontSize=9, alignment=0, leading=12),
        )],
        [Paragraph(
            f"<b>Resultante:</b> {mag_kn:.2f} kN &nbsp;&nbsp; "
            + (
                f"<b>Direção:</b> {result.aggregate_force_azimuth_deg:.1f}°"
                if result.aggregate_force_magnitude > 0
                else "<b>Direção:</b> — (≈ 0, sistema em equilíbrio)"
            ),
            ParagraphStyle("_sumb2", fontSize=9, alignment=0, leading=12),
        )],
    ]
    t = Table(rows, colWidths=[16 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f8f8")),
        ("BOX", (0, 0), (-1, -1), 0.6, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.3, _BRAND_BORDER),
    ]))
    return t


# ──────────────────────────────────────────────────────────────────────
# Tabelas de inputs (caso)
# ──────────────────────────────────────────────────────────────────────


def _case_metadata_table(case_rec: CaseRecord, case_input: CaseInput) -> Table:
    rows = [
        ["Campo", "Valor"],
        ["Nome", case_input.name],
        ["Descrição", case_input.description or "—"],
        ["ID interno", str(case_rec.id)],
        ["Criado em", case_rec.created_at.strftime("%d/%m/%Y %H:%M")],
        ["Atualizado em", case_rec.updated_at.strftime("%d/%m/%Y %H:%M")],
    ]
    t = Table(rows, colWidths=[5 * cm, 11 * cm])
    t.setStyle(_base_table_style())
    return t


def _case_boundary_table(case_input: CaseInput) -> Table:
    bc = case_input.boundary
    sb = case_input.seabed
    rows = [
        ["Parâmetro", "Valor"],
        ["Lâmina d'água (h)", f"{bc.h:.2f} m"],
        ["Profundidade do fairlead", f"{bc.startpoint_depth:.2f} m"],
        ["Modo de cálculo", bc.mode.value],
        [
            "Input value",
            f"{bc.input_value / 1000:.2f} kN" if bc.mode.value == "Tension"
            else f"{bc.input_value:.2f} m",
        ],
        ["Âncora apoiada", "Sim" if bc.endpoint_grounded else "Não"],
        ["μ atrito seabed", f"{sb.mu:.3f}"],
        [
            "Inclinação seabed",
            f"{math.degrees(sb.slope_rad):.2f}° "
            f"({sb.slope_rad:.4f} rad)",
        ],
        ["Perfil de critério", case_input.criteria_profile.value],
    ]
    t = Table(rows, colWidths=[6 * cm, 10 * cm])
    t.setStyle(_base_table_style())
    return t


def _case_segments_table(case_input: CaseInput) -> Table:
    """Tabela detalhada de segmentos (1 linha por segmento)."""
    header = [
        "#", "Categoria", "Tipo", "L (m)",
        "Diâm. (mm)", "w submerso (N/m)", "EA (kN)", "MBL (kN)",
    ]
    rows = [header]
    for i, seg in enumerate(case_input.segments):
        rows.append([
            f"{i + 1}",
            seg.category or "—",
            seg.line_type or "—",
            f"{seg.length:.1f}",
            f"{(seg.diameter or 0) * 1000:.1f}" if seg.diameter else "—",
            f"{seg.w:.1f}",
            f"{seg.EA / 1000:.0f}",
            f"{seg.MBL / 1000:.0f}",
        ])
    col_widths = [
        0.7 * cm, 2.0 * cm, 2.4 * cm, 1.6 * cm,
        2.0 * cm, 2.6 * cm, 2.0 * cm, 2.0 * cm,
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(_data_table_style())
    return t


def _case_attachments_table(case_input: CaseInput) -> Optional[Table]:
    """Tabela resumo de boias e clumps. Retorna None quando lista vazia.

    F5.7: posição mostrada como distância DO FAIRLEAD (consistente com
    a UI). Quando o attachment foi informado via position_index ou
    position_s_from_anchor, convertemos `s_fl = total − s_anc`.
    """
    if not case_input.attachments:
        return None
    total_len = sum(seg.length for seg in case_input.segments)
    header = [
        "#", "Tipo", "Nome", "Posição (m do fairlead)",
        "Força líquida (kN)", "Pendant (m)",
    ]
    rows = [header]
    for i, att in enumerate(case_input.attachments):
        kind_label = "Boia" if att.kind == "buoy" else "Clump weight"
        if att.position_s_from_anchor is not None:
            s_anc = att.position_s_from_anchor
            s_fl = max(0, total_len - s_anc)
            pos_label = f"s = {s_fl:.1f}"
        elif att.position_index is not None:
            cum = 0.0
            for j in range(att.position_index + 1):
                cum += case_input.segments[j].length
            s_fl = max(0, total_len - cum)
            pos_label = f"junção {att.position_index} (s = {s_fl:.1f})"
        else:
            pos_label = "—"
        rows.append([
            f"{i + 1}",
            kind_label,
            att.name or "—",
            pos_label,
            f"{att.submerged_force / 1000:.2f}",
            f"{att.tether_length:.1f}" if att.tether_length else "—",
        ])
    col_widths = [
        0.7 * cm, 1.8 * cm, 2.8 * cm, 4.0 * cm, 3.0 * cm, 2.0 * cm,
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(_data_table_style())
    return t


def _case_attachment_details_table(case_input: CaseInput) -> Optional[Table]:
    """
    Tabela detalhada de boias e pendants (F5.7). Apenas inclui linhas
    onde algum campo de detalhe foi preenchido. Retorna None quando
    nenhum attachment tem metadado adicional.
    """
    if not case_input.attachments:
        return None

    # Mapeia chave de end_type → label legível
    end_label = {
        "elliptical": "Elíptico",
        "flat": "Plano",
        "hemispherical": "Hemisférico",
        "semi_conical": "Semi-cônico",
    }
    type_label = {"surface": "Superfície", "submersible": "Submergível"}

    has_any_detail = False
    rows: list[list[str]] = [[
        "#", "Boia tipo", "Terminais", "Ø ext. (m)",
        "L (m)", "Peso ar (kN)", "Pendant cabo", "Pendant Ø (mm)",
    ]]
    for i, att in enumerate(case_input.attachments):
        details = (
            att.buoy_type, att.buoy_end_type, att.buoy_outer_diameter,
            att.buoy_length, att.buoy_weight_in_air,
            att.pendant_line_type, att.pendant_diameter,
        )
        if not any(d for d in details):
            # Sem detalhes pra esse attachment — pula.
            continue
        has_any_detail = True
        rows.append([
            f"{i + 1}",
            type_label.get(att.buoy_type or "", "—"),
            end_label.get(att.buoy_end_type or "", "—"),
            f"{att.buoy_outer_diameter:.2f}" if att.buoy_outer_diameter else "—",
            f"{att.buoy_length:.2f}" if att.buoy_length else "—",
            f"{att.buoy_weight_in_air / 1000:.2f}" if att.buoy_weight_in_air else "—",
            att.pendant_line_type or "—",
            f"{att.pendant_diameter * 1000:.1f}" if att.pendant_diameter else "—",
        ])
    if not has_any_detail:
        return None
    col_widths = [
        0.7 * cm, 2.0 * cm, 2.0 * cm, 1.8 * cm,
        1.5 * cm, 2.0 * cm, 2.5 * cm, 2.0 * cm,
    ]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(_data_table_style())
    return t


# ──────────────────────────────────────────────────────────────────────
# Tabelas de resultados (caso)
# ──────────────────────────────────────────────────────────────────────


def _case_geometry_table(result: SolverResult) -> Table:
    rows = [
        ["Métrica", "Valor"],
        ["Distância horizontal (X total)", f"{result.total_horz_distance:.2f} m"],
        ["Comprimento não-esticado", f"{result.unstretched_length:.3f} m"],
        ["Comprimento esticado", f"{result.stretched_length:.3f} m"],
        ["Alongamento (ΔL)", f"{result.elongation:.4f} m"],
        ["Comprimento suspenso", f"{result.total_suspended_length:.2f} m"],
        ["Comprimento apoiado", f"{result.total_grounded_length:.2f} m"],
        [
            "Distância até touchdown",
            (
                f"{result.dist_to_first_td:.2f} m"
                if result.dist_to_first_td and result.dist_to_first_td > 0
                else "— (sem touchdown)"
            ),
        ],
        ["Lâmina d'água (referência)", f"{result.water_depth:.2f} m"],
        ["Profundidade fairlead", f"{result.startpoint_depth:.2f} m"],
        ["Prof. seabed @ âncora", f"{result.depth_at_anchor:.2f} m"],
        ["Prof. seabed @ fairlead", f"{result.depth_at_fairlead:.2f} m"],
    ]
    t = Table(rows, colWidths=[7 * cm, 9 * cm])
    t.setStyle(_base_table_style())
    return t


def _case_forces_table(result: SolverResult) -> Table:
    v_fl = math.sqrt(max(result.fairlead_tension**2 - result.H**2, 0.0))
    v_anc = math.sqrt(max(result.anchor_tension**2 - result.H**2, 0.0))
    rows = [
        ["Grandeza", "Valor"],
        ["Tração no fairlead (T_fl)", f"{result.fairlead_tension / 1000:.2f} kN"],
        ["  → componente horizontal (H)", f"{result.H / 1000:.2f} kN"],
        ["  → componente vertical (V_fl)", f"{v_fl / 1000:.2f} kN"],
        ["  → ângulo c/ horizontal", f"{math.degrees(result.angle_wrt_horz_fairlead):.2f}°"],
        ["Tração na âncora (T_anc)", f"{result.anchor_tension / 1000:.2f} kN"],
        ["  → componente vertical (V_anc)", f"{v_anc / 1000:.2f} kN"],
        ["  → ângulo c/ horizontal", f"{math.degrees(result.angle_wrt_horz_anchor):.2f}°"],
        ["Utilização (T_fl / MBL)", f"{result.utilization * 100:.2f} %"],
        ["Margem para o limite", f"{(1 - result.utilization) * 100:.2f} %"],
    ]
    t = Table(rows, colWidths=[7 * cm, 9 * cm])
    t.setStyle(_base_table_style())
    return t


def _case_diagnostic_table(result: SolverResult) -> Table:
    rows = [
        ["Diagnóstico", "Valor"],
        ["Status de convergência", result.status.value],
        ["Iterações usadas", str(result.iterations_used)],
        ["Versão do solver", result.solver_version or "—"],
        ["Mensagem", result.message or "—"],
    ]
    t = Table(rows, colWidths=[5 * cm, 11 * cm])
    t.setStyle(_base_table_style())
    return t


# ──────────────────────────────────────────────────────────────────────
# Gráficos (matplotlib → PNG)
# ──────────────────────────────────────────────────────────────────────


def _profile_png(
    result: SolverResult, case_input: Optional[CaseInput] = None,
) -> bytes:
    """
    Perfil 2D da linha em PNG.

    Frame surface-relative (mesma do frontend):
      - X = 0 no fairlead, cresce em direção à âncora
      - Y = 0 na superfície da água, decresce para baixo
      - Fairlead em (0, -startpoint_depth)
      - Âncora em (X_total, -water_depth)

    Cores por segmento quando há multi-segmento; linhas verticais
    pontilhadas marcam fronteiras entre segmentos. Touchdown destacado
    em vermelho. Attachments (boias/clumps) plotados como marcadores.
    """
    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=130)

    xs = list(result.coords_x or [])
    ys = list(result.coords_y or [])
    Xtotal = result.total_horz_distance or 0.0
    water_depth = result.water_depth or 0.0
    startpoint_depth = result.startpoint_depth or 0.0
    fairlead_y = -startpoint_depth
    anchor_y = -water_depth
    td = result.dist_to_first_td or 0.0

    # Transforma para surface-relative
    plot_x = [Xtotal - x for x in xs]
    plot_y = [y - water_depth for y in ys]
    # Reverte para fairlead-first
    plot_x.reverse()
    plot_y.reverse()

    # Touchdown bookkeeping
    on_ground = []
    for i in range(len(xs)):
        sx = xs[i]
        on_ground.append(td > 0 and sx <= td + 1e-6)
    on_ground.reverse()

    # Seabed
    seabed_x_lo = -Xtotal * 0.05
    seabed_x_hi = Xtotal * 1.05
    ax.fill_between(
        [seabed_x_lo, seabed_x_hi],
        [anchor_y, anchor_y - 5],
        [anchor_y - 50, anchor_y - 50],
        color="#bcbcbc", alpha=0.3, zorder=0,
    )
    ax.plot(
        [seabed_x_lo, seabed_x_hi], [anchor_y, anchor_y],
        color="#666", linewidth=1.2, zorder=1,
    )
    # Superfície da água
    ax.axhline(0, color="#0EA5E9", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)

    # Curva: por segmento se houver multi-segmento
    seg_bounds = result.segment_boundaries or []
    is_multi = len(seg_bounds) > 2
    if is_multi:
        N = len(plot_x)
        for s in range(len(seg_bounds) - 1):
            startA = seg_bounds[s]
            endA = seg_bounds[s + 1]
            startF = N - 1 - endA
            endF = N - 1 - startA
            seg_color = _SEG_PALETTE[s % len(_SEG_PALETTE)]
            ax.plot(
                plot_x[startF:endF + 1], plot_y[startF:endF + 1],
                color=seg_color, linewidth=2.2, zorder=3,
                label=f"Seg {s + 1}" if case_input is None
                else (
                    f"Seg {s + 1} ({case_input.segments[s].line_type})"
                    if s < len(case_input.segments)
                    else f"Seg {s + 1}"
                ),
            )
        # Overlay vermelho na porção apoiada
        gx = [plot_x[i] for i in range(N) if on_ground[i]]
        gy = [plot_y[i] for i in range(N) if on_ground[i]]
        if gx:
            ax.plot(gx, gy, color="#DC2626", linewidth=2.8, zorder=4,
                    label="Trecho apoiado")
    else:
        # Single-segmento: split suspenso/apoiado
        suspended_x = [plot_x[i] for i in range(len(plot_x)) if not on_ground[i]]
        suspended_y = [plot_y[i] for i in range(len(plot_y)) if not on_ground[i]]
        grounded_x = [plot_x[i] for i in range(len(plot_x)) if on_ground[i]]
        grounded_y = [plot_y[i] for i in range(len(plot_y)) if on_ground[i]]
        if suspended_x and grounded_x:
            # Conecta visualmente
            suspended_x.append(grounded_x[0])
            suspended_y.append(grounded_y[0])
        if suspended_x:
            ax.plot(suspended_x, suspended_y, color="#1E3A5F",
                    linewidth=2.2, label="Suspenso", zorder=3)
        if grounded_x:
            ax.plot(grounded_x, grounded_y, color="#DC2626",
                    linewidth=2.8, label="Apoiado", zorder=4)

    # Fairlead e âncora marker
    ax.scatter([0], [fairlead_y], color="#1E3A5F", s=70, zorder=5,
               marker="s", label="Fairlead")
    ax.scatter([Xtotal], [anchor_y], color="#475569", s=80, zorder=5,
               marker="^", label="Âncora")

    # Touchdown
    if td > 0.5:
        td_x_plot = Xtotal - td
        ax.scatter([td_x_plot], [anchor_y], color="#DC2626",
                   s=80, zorder=6, marker="D", label="Touchdown")

    # Attachments
    if case_input and case_input.attachments and is_multi:
        N = len(plot_x)
        # Soma cumulativa de comprimentos pra mapear position_s
        cum = [0.0]
        for seg in case_input.segments:
            cum.append(cum[-1] + seg.length)
        total_unstr = cum[-1]
        for att in case_input.attachments:
            # Posição em arc length desde a âncora
            if att.position_s_from_anchor is not None:
                s_anc = att.position_s_from_anchor
            elif att.position_index is not None:
                s_anc = cum[att.position_index + 1] if att.position_index + 1 < len(cum) else 0
            else:
                continue
            # Mapeia para idx no plot via fração de arc length
            frac = (total_unstr - s_anc) / total_unstr if total_unstr > 0 else 0
            idx = max(0, min(N - 1, round(frac * (N - 1))))
            px = plot_x[idx]
            py = plot_y[idx]
            tether = att.tether_length or 0
            body_y = py + (tether if att.kind == "buoy" else -tether)
            color = "#0EA5E9" if att.kind == "buoy" else "#D97706"
            marker = "o" if att.kind == "buoy" else "s"
            label = f"{'Boia' if att.kind == 'buoy' else 'Clump'}"
            if att.name:
                label = f"{att.name} ({label})"
            ax.scatter([px], [body_y], color=color, s=60, marker=marker,
                       zorder=6, edgecolors="white", linewidths=1.5,
                       label=label)
            if tether > 0:
                ax.plot([px, px], [py, body_y], color=color,
                        linestyle=":", linewidth=1.2, alpha=0.6, zorder=5)

    ax.set_xlabel("Distância horizontal a partir do fairlead (m)", fontsize=9)
    ax.set_ylabel("Elevação (m) — superfície em y=0", fontsize=9)
    ax.set_title("Perfil 2D da linha (frame surface-relative)", fontsize=10)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.85)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def _tension_distribution_png(result: SolverResult) -> bytes:
    """
    Distribuição de tensão T(s) ao longo da linha em PNG. Eixo X = arc
    length da âncora ao fairlead, eixo Y = magnitude da tensão.
    """
    fig, ax = plt.subplots(figsize=(7.0, 3.0), dpi=130)
    xs = list(result.coords_x or [])
    ys = list(result.coords_y or [])
    ts = list(result.tension_magnitude or [])

    if not ts or not xs:
        ax.text(0.5, 0.5, "Sem dados de tensão disponíveis",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color="#888")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        # Arc length cumulativo a partir da âncora (frame solver)
        s_arc = [0.0]
        for i in range(1, len(xs)):
            s_arc.append(
                s_arc[-1] +
                math.hypot(xs[i] - xs[i-1], ys[i] - ys[i-1])
            )
        # Tensão em kN
        t_kn = [t / 1000 for t in ts]
        ax.plot(s_arc, t_kn, color="#1E3A5F", linewidth=1.8)
        ax.fill_between(s_arc, 0, t_kn, color="#1E3A5F", alpha=0.12)
        # MBL como linha de referência
        try:
            mbl_kn = result.fairlead_tension / max(result.utilization, 1e-9) / 1000
            if 0 < mbl_kn < 100 * max(t_kn):
                ax.axhline(mbl_kn, color="#DC2626", linestyle="--",
                           linewidth=1, alpha=0.7,
                           label=f"MBL = {mbl_kn:.0f} kN")
        except Exception:  # noqa: BLE001
            pass
        # Marcadores: âncora e fairlead
        ax.scatter([0], [t_kn[0]], color="#475569", s=60, marker="^",
                   zorder=4, label=f"Âncora (T = {t_kn[0]:.1f} kN)")
        ax.scatter([s_arc[-1]], [t_kn[-1]], color="#1E3A5F", s=60,
                   marker="s", zorder=4,
                   label=f"Fairlead (T = {t_kn[-1]:.1f} kN)")

        ax.set_xlabel("Arc length da âncora (m)", fontsize=9)
        ax.set_ylabel("Tensão |T| (kN)", fontsize=9)
        ax.legend(loc="best", fontsize=7, framealpha=0.85)

    ax.set_title("Distribuição de tensão ao longo da linha", fontsize=10)
    ax.grid(True, alpha=0.25)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────
# build_pdf — caso individual
# ──────────────────────────────────────────────────────────────────────


def build_pdf(
    case_rec: CaseRecord, execution: Optional[ExecutionRecord]
) -> bytes:
    """
    Gera PDF técnico do caso individual.

    Sem execução, gera relatório só com inputs + disclaimer.
    """
    case_input = CaseInput.model_validate_json(case_rec.input_json)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"QMoor — {case_input.name}",
    )
    styles = _build_styles()
    story: list = []

    # --- Header + Disclaimer ---
    story.extend(_header_block(
        "QMoor Web — Relatório de análise estática",
        f"Caso: <b>{case_input.name}</b>",
        case_rec.id, styles,
    ))
    story.extend(_disclaimer_block(styles))

    # --- Sumário executivo (apenas se há resultado) ---
    result: Optional[SolverResult] = None
    if execution is not None:
        result = SolverResult.model_validate_json(execution.result_json)
        story.append(_summary_box_case(result))
        story.append(Spacer(1, 0.5 * cm))

    # --- Configuração ---
    story.append(Paragraph("1. Identificação", styles["SectionTitle"]))
    story.append(_case_metadata_table(case_rec, case_input))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(
        "2. Condições de contorno e seabed", styles["SectionTitle"],
    ))
    story.append(_case_boundary_table(case_input))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(
        f"3. Segmentos da linha ({len(case_input.segments)})",
        styles["SectionTitle"],
    ))
    story.append(_case_segments_table(case_input))
    story.append(Spacer(1, 0.4 * cm))

    att_table = _case_attachments_table(case_input)
    if att_table is not None:
        story.append(Paragraph(
            f"4. Attachments — boias e clump weights "
            f"({len(case_input.attachments)})",
            styles["SectionTitle"],
        ))
        story.append(att_table)
        story.append(Spacer(1, 0.2 * cm))
        # Tabela de detalhes (geometria de boia + pendant material)
        # quando o usuário preencheu algum campo opcional.
        att_details = _case_attachment_details_table(case_input)
        if att_details is not None:
            story.append(Paragraph(
                "Detalhes adicionais (geometria + pendant):",
                styles["Caption"],
            ))
            story.append(att_details)
        story.append(Spacer(1, 0.4 * cm))

    if result is None:
        # Sem resultado: relatório parcial
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(
            "<b>Nenhuma execução do solver disponível.</b> Execute o "
            "caso (POST /cases/{id}/solve) e gere novamente o "
            "relatório para ver os resultados.",
            styles["Normal"],
        ))
        doc.build(story)
        return buf.getvalue()

    # --- Resultados ---
    story.append(PageBreak())
    story.append(Paragraph("5. Perfil da linha", styles["SectionTitle"]))
    profile_png = _profile_png(result, case_input)
    story.append(Image(io.BytesIO(profile_png), width=17 * cm, height=9.2 * cm))
    story.append(Paragraph(
        "Frame surface-relative: superfície em y=0; profundidades "
        "negativas. Cores por segmento quando multi-segmento; trecho "
        "apoiado no seabed em vermelho.",
        styles["Caption"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(
        "6. Distribuição de tensão", styles["SectionTitle"],
    ))
    tension_png = _tension_distribution_png(result)
    story.append(Image(io.BytesIO(tension_png), width=17 * cm, height=7.3 * cm))
    story.append(Paragraph(
        "Magnitude da tensão |T(s)| ao longo da linha. Tensão máxima "
        "no fairlead (extremo direito); diminui em direção à âncora "
        "devido ao peso suspenso e atrito do trecho apoiado.",
        styles["Caption"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    story.append(PageBreak())
    story.append(Paragraph("7. Geometria", styles["SectionTitle"]))
    story.append(_case_geometry_table(result))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("8. Forças e ângulos", styles["SectionTitle"]))
    story.append(_case_forces_table(result))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("9. Diagnóstico do solver", styles["SectionTitle"]))
    story.append(_case_diagnostic_table(result))

    doc.build(story)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────
# Mooring system (multi-linha)
# ──────────────────────────────────────────────────────────────────────


def _msys_metadata_table(
    msys_rec: MooringSystemRecord, msys_input: MooringSystemInput,
) -> Table:
    rows = [
        ["Campo", "Valor"],
        ["Nome", msys_input.name],
        ["Descrição", msys_input.description or "—"],
        ["ID interno", str(msys_rec.id)],
        ["Raio da plataforma", f"{msys_input.platform_radius:.2f} m"],
        ["Nº de linhas", str(len(msys_input.lines))],
        ["Criado em", msys_rec.created_at.strftime("%d/%m/%Y %H:%M")],
        ["Atualizado em", msys_rec.updated_at.strftime("%d/%m/%Y %H:%M")],
    ]
    t = Table(rows, colWidths=[5 * cm, 11 * cm])
    t.setStyle(_base_table_style())
    return t


def _msys_lines_summary_table(
    msys_input: MooringSystemInput,
    result: Optional[MooringSystemResult],
) -> Table:
    """Tabela larga: 1 linha por mooring line, com posição + parâmetros + resultado."""
    header = [
        "Linha", "Az (°)", "R fl (m)", "Modo", "Input",
        "T_fl (kN)", "H (kN)", "T_anc (kN)",
        "Util.", "Alerta", "Status",
    ]
    rows = [header]
    for idx, line in enumerate(msys_input.lines):
        bc = line.boundary
        input_label = (
            f"{bc.input_value / 1000:.1f} kN" if bc.mode.value == "Tension"
            else f"{bc.input_value:.1f} m"
        )
        lr = result.lines[idx] if result and idx < len(result.lines) else None
        sr = lr.solver_result if lr else None
        rows.append([
            line.name,
            f"{line.fairlead_azimuth_deg:.1f}",
            f"{line.fairlead_radius:.1f}",
            bc.mode.value,
            input_label,
            f"{sr.fairlead_tension / 1000:.1f}" if sr else "—",
            f"{sr.H / 1000:.1f}" if sr else "—",
            f"{sr.anchor_tension / 1000:.1f}" if sr else "—",
            f"{sr.utilization * 100:.1f}%" if sr else "—",
            _alert_label(sr.alert_level.value) if sr else "—",
            sr.status.value if sr else "—",
        ])
    col_widths = [
        1.5 * cm, 1.4 * cm, 1.5 * cm, 1.4 * cm, 1.6 * cm,
        1.7 * cm, 1.6 * cm, 1.7 * cm, 1.4 * cm, 1.7 * cm, 1.7 * cm,
    ]
    t = Table(rows, colWidths=col_widths)
    style = _data_table_style()
    # Pinta a célula do alerta com a cor correspondente em cada linha
    for row_idx, line in enumerate(msys_input.lines, start=1):
        lr = result.lines[row_idx - 1] if result and row_idx - 1 < len(result.lines) else None
        if lr and lr.solver_result.status == ConvergenceStatus.CONVERGED:
            color = _alert_color(lr.solver_result.alert_level.value)
            style.add(
                "TEXTCOLOR", (9, row_idx), (9, row_idx), color,
            )
            style.add(
                "FONTNAME", (9, row_idx), (9, row_idx), "Helvetica-Bold",
            )
    t.setStyle(style)
    return t


def _msys_anchors_table(result: MooringSystemResult) -> Table:
    """Posições absolutas das âncoras no plano da plataforma."""
    header = [
        "Linha", "Fairlead X (m)", "Fairlead Y (m)",
        "Âncora X (m)", "Âncora Y (m)", "F_x (kN)", "F_y (kN)",
    ]
    rows = [header]
    for lr in result.lines:
        rows.append([
            lr.line_name,
            f"{lr.fairlead_xy[0]:.2f}",
            f"{lr.fairlead_xy[1]:.2f}",
            f"{lr.anchor_xy[0]:.2f}",
            f"{lr.anchor_xy[1]:.2f}",
            f"{lr.horz_force_xy[0] / 1000:.2f}",
            f"{lr.horz_force_xy[1] / 1000:.2f}",
        ])
    col_widths = [1.6 * cm] + [2.2 * cm] * 6
    t = Table(rows, colWidths=col_widths)
    t.setStyle(_data_table_style())
    return t


def _msys_aggregate_table(result: MooringSystemResult) -> Table:
    rows = [
        ["Métrica agregada", "Valor"],
        ["Linhas convergidas", f"{result.n_converged} / {len(result.lines)}"],
        ["Linhas inválidas", str(result.n_invalid)],
        ["Resultante (módulo)", f"{result.aggregate_force_magnitude / 1000:.2f} kN"],
        [
            "Direção do resultante",
            (
                f"{result.aggregate_force_azimuth_deg:.1f}°"
                if result.aggregate_force_magnitude > 0
                else "— (sistema balanceado)"
            ),
        ],
        ["F_x agregado", f"{result.aggregate_force_xy[0] / 1000:.2f} kN"],
        ["F_y agregado", f"{result.aggregate_force_xy[1] / 1000:.2f} kN"],
        ["Máx. utilização", f"{result.max_utilization * 100:.2f}%"],
        ["Pior alerta", _alert_label(result.worst_alert_level.value)],
        ["Versão do solver", result.solver_version or "—"],
    ]
    t = Table(rows, colWidths=[7 * cm, 9 * cm])
    style = _base_table_style()
    # Pinta o pior alerta colorido
    for i, row in enumerate(rows):
        if row[0] == "Pior alerta":
            style.add(
                "TEXTCOLOR", (1, i), (1, i),
                _alert_color(result.worst_alert_level.value),
            )
            style.add("FONTNAME", (1, i), (1, i), "Helvetica-Bold")
    t.setStyle(style)
    return t


def _plan_view_png(
    msys_input: MooringSystemInput,
    result: Optional[MooringSystemResult],
) -> bytes:
    """Plan view (visão de topo) do sistema multi-linha."""
    fig, ax = plt.subplots(figsize=(6.5, 6.5), dpi=130)
    R = msys_input.platform_radius

    # Range
    max_radius = R
    if result:
        for lr in result.lines:
            r = max(
                math.hypot(*lr.anchor_xy),
                math.hypot(*lr.fairlead_xy),
            )
            if r > max_radius:
                max_radius = r
    else:
        max_radius = max(R, max(l.fairlead_radius for l in msys_input.lines) * 4)
    span = max_radius * 1.15

    # Anéis de referência
    for frac in (0.33, 0.66, 1.0):
        circle = plt.Circle(
            (0, 0), span * frac, fill=False,
            color="#888", linewidth=0.5, linestyle=":", alpha=0.4,
        )
        ax.add_patch(circle)

    # Plataforma
    plat = plt.Circle(
        (0, 0), R, fill=True, facecolor="#bcbcbc",
        edgecolor="#555", alpha=0.35, linewidth=1.3,
    )
    ax.add_patch(plat)
    ax.plot(R, 0, marker=">", markersize=15, color="#444", zorder=5)
    ax.text(0, 0, "Plataforma", fontsize=8, ha="center", va="center",
            color="#666", style="italic")

    # Linhas
    if result:
        for idx, lr in enumerate(result.lines):
            sr = lr.solver_result
            color = (
                "#9CA3AF" if sr.status != ConvergenceStatus.CONVERGED
                else _alert_color_hex(sr.alert_level.value)
            )
            ax.plot(
                [lr.fairlead_xy[0], lr.anchor_xy[0]],
                [lr.fairlead_xy[1], lr.anchor_xy[1]],
                color=color, linewidth=2.0,
                linestyle="--" if sr.status != ConvergenceStatus.CONVERGED else "-",
                alpha=0.85, zorder=3,
            )
            ax.plot(*lr.fairlead_xy, "o", markersize=6, color=color, zorder=4)
            ax.plot(*lr.anchor_xy, "^", markersize=10, color=color, zorder=4)
            # Label próximo da metade
            mx = lr.fairlead_xy[0] + 0.55 * (lr.anchor_xy[0] - lr.fairlead_xy[0])
            my = lr.fairlead_xy[1] + 0.55 * (lr.anchor_xy[1] - lr.fairlead_xy[1])
            ax.annotate(lr.line_name, (mx, my), fontsize=9, ha="center",
                        va="bottom", color="#222",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white",
                                  ec="none", alpha=0.7))

        # Resultante
        if result.aggregate_force_magnitude > 0:
            fx, fy = result.aggregate_force_xy
            mag = result.aggregate_force_magnitude
            tlen = max_radius * 0.4
            ax.annotate(
                "", xy=(fx / mag * tlen, fy / mag * tlen), xytext=(0, 0),
                arrowprops=dict(
                    arrowstyle="-|>", color="#EC4899",
                    lw=2, alpha=0.9,
                ),
            )
            ax.text(
                fx / mag * tlen * 1.1, fy / mag * tlen * 1.1,
                f"{mag / 1000:.1f} kN",
                fontsize=8, color="#EC4899", fontweight="bold",
            )
    else:
        # Modo sem resultado
        for line in msys_input.lines:
            theta = math.radians(line.fairlead_azimuth_deg)
            fx = line.fairlead_radius * math.cos(theta)
            fy = line.fairlead_radius * math.sin(theta)
            ar = line.fairlead_radius * 4
            ax_x = ar * math.cos(theta)
            ay = ar * math.sin(theta)
            ax.plot([fx, ax_x], [fy, ay],
                    color="#888", linestyle="--", linewidth=1.2, alpha=0.6)
            ax.plot(fx, fy, "o", markersize=5, color="#888")
            ax.annotate(line.name,
                        ((fx + ax_x) / 2, (fy + ay) / 2),
                        fontsize=9, ha="center", va="bottom", color="#444")

    # Eixos cardinais com labels
    ax.axhline(0, color="#bbb", linewidth=0.4, zorder=0)
    ax.axvline(0, color="#bbb", linewidth=0.4, zorder=0)
    ax.text(span * 1.02, 0, "+X (proa)", fontsize=8, color="#666", va="center")
    ax.text(0, span * 1.02, "+Y (BB)", fontsize=8, color="#666", ha="center")

    ax.set_xlim(-span, span)
    ax.set_ylim(-span, span)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("X (m)", fontsize=9)
    ax.set_ylabel("Y (m)", fontsize=9)
    ax.set_title("Plan view — disposição do mooring system", fontsize=10)
    ax.grid(True, alpha=0.18)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def _utilization_chart_png(result: MooringSystemResult) -> bytes:
    """Bar chart comparando utilização (T_fl/MBL) entre linhas."""
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=130)
    names = [lr.line_name for lr in result.lines]
    utils = [
        lr.solver_result.utilization * 100
        if lr.solver_result.status == ConvergenceStatus.CONVERGED else 0
        for lr in result.lines
    ]
    cores = [
        _alert_color_hex(lr.solver_result.alert_level.value)
        if lr.solver_result.status == ConvergenceStatus.CONVERGED
        else "#9CA3AF"
        for lr in result.lines
    ]
    bars = ax.bar(names, utils, color=cores, edgecolor="white", linewidth=0.5)
    # Linhas de referência: thresholds genéricos do MVP
    ax.axhline(60, color="#d1a200", linewidth=0.7, linestyle="--", alpha=0.6,
               label="Yellow (60%)")
    ax.axhline(80, color="#b33a3a", linewidth=0.7, linestyle="--", alpha=0.6,
               label="Red (80%)")
    ax.axhline(100, color="#8b0000", linewidth=0.8, linestyle="-", alpha=0.7,
               label="MBL (100%)")
    # Labels nas barras
    for bar, util in zip(bars, utils):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{util:.1f}%", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("Utilização (% MBL)", fontsize=9)
    ax.set_title("Comparação de utilização entre linhas", fontsize=10)
    ax.set_ylim(0, max(110, max(utils) * 1.15))
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.85)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def build_mooring_system_pdf(
    msys_rec: MooringSystemRecord,
    execution: Optional[MooringSystemExecutionRecord],
) -> bytes:
    """
    Gera PDF técnico de mooring system multi-linha.

    Estrutura mais elaborada (redesign 2026): sumário executivo
    colorido, plan view de qualidade, tabelas detalhadas por linha,
    bar chart comparativo de utilização, posições de âncoras, forças
    agregadas, diagnóstico.
    """
    msys_input = MooringSystemInput.model_validate_json(msys_rec.config_json)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"QMoor — {msys_input.name}",
    )
    styles = _build_styles()
    story: list = []

    # --- Header + Disclaimer ---
    story.extend(_header_block(
        "QMoor Web — Relatório de mooring system",
        f"Sistema: <b>{msys_input.name}</b>",
        msys_rec.id, styles,
    ))
    story.extend(_disclaimer_block(styles))

    result: Optional[MooringSystemResult] = None
    if execution is not None:
        result = MooringSystemResult.model_validate_json(execution.result_json)
        story.append(_summary_box_msys(result))
        story.append(Spacer(1, 0.5 * cm))

    # --- Configuração ---
    story.append(Paragraph("1. Identificação", styles["SectionTitle"]))
    story.append(_msys_metadata_table(msys_rec, msys_input))
    story.append(Spacer(1, 0.4 * cm))

    # --- Plan view ---
    story.append(Paragraph("2. Plan view", styles["SectionTitle"]))
    plan_png = _plan_view_png(msys_input, result)
    story.append(Image(io.BytesIO(plan_png), width=14 * cm, height=14 * cm))
    story.append(Paragraph(
        "Visão de topo: plataforma centrada na origem; cada linha "
        "saindo radialmente do fairlead até a âncora. Cor da linha "
        "indica nível de alerta (verde/amarelo/vermelho). Quando "
        "presente, seta rosa indica resultante das forças horizontais.",
        styles["Caption"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    if result is None:
        story.append(Paragraph(
            "<b>Nenhuma execução do solver disponível.</b> Resolva o "
            "sistema (POST /mooring-systems/{id}/solve) para ver "
            "tensões, ângulos e resultante agregado.",
            styles["Normal"],
        ))
        doc.build(story)
        return buf.getvalue()

    # --- Tabela detalhada por linha ---
    story.append(PageBreak())
    story.append(Paragraph(
        f"3. Tabela detalhada por linha ({len(msys_input.lines)})",
        styles["SectionTitle"],
    ))
    story.append(_msys_lines_summary_table(msys_input, result))
    story.append(Spacer(1, 0.4 * cm))

    # --- Utilização comparativa (bar chart) ---
    story.append(Paragraph(
        "4. Comparativo de utilização", styles["SectionTitle"],
    ))
    util_png = _utilization_chart_png(result)
    story.append(Image(io.BytesIO(util_png), width=17 * cm, height=7.8 * cm))
    story.append(Paragraph(
        "Fração da MBL utilizada por linha. Linhas tracejadas marcam "
        "thresholds típicos: 60% (atenção), 80% (crítico), 100% "
        "(rompimento). Cor da barra reflete o alert_level individual.",
        styles["Caption"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    # --- Posições absolutas ---
    story.append(PageBreak())
    story.append(Paragraph(
        "5. Posições no plano da plataforma", styles["SectionTitle"],
    ))
    story.append(_msys_anchors_table(result))
    story.append(Paragraph(
        "Coordenadas (x, y) em metros no frame do casco "
        "(origem no centro da plataforma; +X proa, +Y bombordo).",
        styles["Caption"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    # --- Forças agregadas ---
    story.append(Paragraph(
        "6. Forças agregadas e diagnóstico", styles["SectionTitle"],
    ))
    story.append(_msys_aggregate_table(result))

    doc.build(story)
    return buf.getvalue()


__all__ = ["build_pdf", "build_mooring_system_pdf", "DISCLAIMER"]
