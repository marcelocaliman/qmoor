"""
Geração do relatório técnico em PDF (F2.7).

Usa reportlab (puro Python, sem headless Chrome). Layout minimalista
conforme Seção 8 do plano F2:
  1. Header: nome do caso, timestamp, versão do solver
  2. Disclaimer obrigatório (Seção 10 do Documento A v2.2)
  3. Tabela de inputs
  4. Gráfico de perfil 2D (matplotlib → PNG → embed)
  5. Tabela de resultados
  6. Status de convergência + mensagem

Gera bytes em memória; router decide como devolver.
"""
from __future__ import annotations

import io
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


def _profile_png(result: SolverResult) -> bytes:
    """Gera o perfil 2D da linha em PNG (bytes)."""
    fig, ax = plt.subplots(figsize=(7.0, 3.5), dpi=120)
    ax.plot(result.coords_x, result.coords_y, color="#1f77b4", linewidth=1.6)
    ax.axhline(0.0, color="#8b6914", linewidth=0.7, linestyle="--", alpha=0.6)
    ax.scatter([0.0], [0.0], color="#d62728", zorder=5, label="Âncora")
    ax.scatter(
        [result.total_horz_distance], [result.endpoint_depth],
        color="#2ca02c", zorder=5, label="Fairlead",
    )
    if result.dist_to_first_td is not None and result.dist_to_first_td > 0:
        ax.scatter(
            [result.dist_to_first_td], [0.0],
            color="#9467bd", zorder=5, label="Touchdown",
        )
    ax.set_xlabel("Distância horizontal (m)")
    ax.set_ylabel("Elevação (m)")
    ax.set_title("Perfil 2D da linha")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _inputs_table_data(case_input: CaseInput) -> list[list[str]]:
    seg = case_input.segments[0]
    bc = case_input.boundary
    sb = case_input.seabed
    rows = [
        ["Grandeza", "Valor"],
        ["Nome do caso", case_input.name],
        ["Descrição", case_input.description or "—"],
        ["Modo", bc.mode.value],
        ["Input value", f"{bc.input_value:.3f}"],
        ["Lâmina d'água (m)", f"{bc.h:.2f}"],
        ["Comprimento (m)", f"{seg.length:.2f}"],
        ["Peso submerso (N/m)", f"{seg.w:.2f}"],
        ["EA (N)", f"{seg.EA:.3e}"],
        ["MBL (N)", f"{seg.MBL:.3e}"],
        ["Categoria", seg.category or "—"],
        ["Tipo de linha", seg.line_type or "—"],
        ["μ atrito seabed", f"{sb.mu:.2f}"],
        ["Perfil de critério", case_input.criteria_profile.value],
    ]
    return rows


def _results_table_data(result: SolverResult) -> list[list[str]]:
    rows = [
        ["Grandeza", "Valor"],
        ["Status", result.status.value],
        ["Alert level", result.alert_level.value],
        ["Tração no fairlead (kN)", f"{result.fairlead_tension / 1000:.2f}"],
        ["Tração na âncora (kN)", f"{result.anchor_tension / 1000:.2f}"],
        ["H (horizontal) (kN)", f"{result.H / 1000:.2f}"],
        ["Distância horizontal total (m)", f"{result.total_horz_distance:.2f}"],
        ["Profundidade endpoint (m)", f"{result.endpoint_depth:.2f}"],
        ["Comprimento não-esticado (m)", f"{result.unstretched_length:.3f}"],
        ["Comprimento esticado (m)", f"{result.stretched_length:.3f}"],
        ["Alongamento (m)", f"{result.elongation:.4f}"],
        ["Comprimento suspenso (m)", f"{result.total_suspended_length:.3f}"],
        ["Comprimento apoiado (m)", f"{result.total_grounded_length:.3f}"],
        [
            "Distância até touchdown (m)",
            (f"{result.dist_to_first_td:.3f}" if result.dist_to_first_td else "—"),
        ],
        ["Utilização (T_fl/MBL)", f"{result.utilization:.4f}"],
        ["Iterações do solver", str(result.iterations_used)],
    ]
    return rows


def _base_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#888888")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ])


def _alert_color(alert_level: str) -> colors.Color:
    return {
        "ok": colors.HexColor("#2d7a2d"),
        "yellow": colors.HexColor("#d1a200"),
        "red": colors.HexColor("#b33a3a"),
        "broken": colors.HexColor("#8b0000"),
    }.get(alert_level, colors.black)


def build_pdf(
    case_rec: CaseRecord, execution: Optional[ExecutionRecord]
) -> bytes:
    """
    Gera o PDF em memória e retorna os bytes.

    Se `execution` é None, produz um relatório só com os inputs e um
    aviso de que o caso ainda não foi resolvido.
    """
    case_input = CaseInput.model_validate_json(case_rec.input_json)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"QMoor — {case_input.name}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="HeaderSmall", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#555555"),
    ))
    styles.add(ParagraphStyle(
        name="DisclaimerBox", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#606060"),
        borderPadding=6, borderColor=colors.HexColor("#cccccc"),
        borderWidth=0.5, leading=10,
    ))

    story = []

    # --- Header ---
    story.append(Paragraph(f"<b>QMoor Web — Relatório de análise</b>", styles["Title"]))
    story.append(Paragraph(
        f"Caso: <b>{case_input.name}</b> (id {case_rec.id})",
        styles["Heading3"],
    ))
    now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S %Z")
    story.append(Paragraph(
        f"Gerado em {now} — Solver versão {SOLVER_VERSION}",
        styles["HeaderSmall"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    # --- Disclaimer ---
    story.append(Paragraph(f"<b>Disclaimer técnico</b>", styles["Heading4"]))
    story.append(Paragraph(DISCLAIMER, styles["DisclaimerBox"]))
    story.append(Spacer(1, 0.4 * cm))

    # --- Inputs ---
    story.append(Paragraph("<b>Entradas</b>", styles["Heading3"]))
    inputs_table = Table(_inputs_table_data(case_input), colWidths=[6 * cm, 8 * cm])
    inputs_table.setStyle(_base_table_style())
    story.append(inputs_table)
    story.append(Spacer(1, 0.5 * cm))

    if execution is None:
        # Sem resultado ainda
        story.append(Paragraph(
            "Nenhuma execução do solver disponível para este caso. "
            "Execute POST /cases/{id}/solve antes de gerar o relatório.",
            styles["Normal"],
        ))
        doc.build(story)
        return buf.getvalue()

    result = SolverResult.model_validate_json(execution.result_json)

    # --- Gráfico ---
    story.append(PageBreak())
    story.append(Paragraph("<b>Perfil da linha</b>", styles["Heading3"]))
    png_bytes = _profile_png(result)
    story.append(Image(io.BytesIO(png_bytes), width=17 * cm, height=8.5 * cm))
    story.append(Spacer(1, 0.4 * cm))

    # --- Resultados ---
    story.append(Paragraph("<b>Resultados</b>", styles["Heading3"]))
    results_table = Table(_results_table_data(result), colWidths=[7 * cm, 7 * cm])
    results_table.setStyle(_base_table_style())
    # Pinta linha do alert_level
    for i, row in enumerate(_results_table_data(result)):
        if row[0] == "Alert level":
            results_table.setStyle(TableStyle([
                ("TEXTCOLOR", (1, i), (1, i), _alert_color(result.alert_level.value)),
                ("FONTNAME", (1, i), (1, i), "Helvetica-Bold"),
            ]))
    story.append(results_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Convergência ---
    story.append(Paragraph(
        f"<b>Mensagem do solver:</b> {result.message or '—'}",
        styles["Normal"],
    ))

    doc.build(story)
    return buf.getvalue()


# ───────────────────────────────────────────────────────────────────────
# F5.4.5c — PDF report do mooring system multi-linha
# ───────────────────────────────────────────────────────────────────────


def _plan_view_png(
    msys_input: MooringSystemInput,
    result: Optional[MooringSystemResult],
) -> bytes:
    """
    Plan view (visão de topo) do sistema multi-linha em PNG.

    Plataforma como círculo, linhas como segmentos do fairlead até a
    âncora, coloridas por `alert_level`. Quando `result` está presente,
    o resultante agregado aparece como vetor rosa partindo do centro.
    Sem resultado, desenha-se a plataforma + fairleads + linhas
    radiais com âncoras estimadas em 4× raio (placeholder).
    """
    fig, ax = plt.subplots(figsize=(7.0, 7.0), dpi=120)
    R = msys_input.platform_radius
    lines = result.lines if result else []

    # Determina o range
    max_radius = R
    if lines:
        for lr in lines:
            r = max(
                (lr.anchor_xy[0] ** 2 + lr.anchor_xy[1] ** 2) ** 0.5,
                (lr.fairlead_xy[0] ** 2 + lr.fairlead_xy[1] ** 2) ** 0.5,
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
            color="#888888", linewidth=0.6, linestyle=":", alpha=0.4,
        )
        ax.add_patch(circle)

    # Plataforma
    plat = plt.Circle(
        (0, 0), R, fill=True, facecolor="#bcbcbc",
        edgecolor="#555555", alpha=0.35, linewidth=1.2,
    )
    ax.add_patch(plat)
    # Marca da proa (+X)
    ax.plot(R, 0, marker=">", markersize=14, color="#444444")

    alert_color = {
        "ok": "#10B981",
        "yellow": "#F59E0B",
        "red": "#EF4444",
        "broken": "#7F1D1D",
    }

    if lines:
        for lr in lines:
            sr = lr.solver_result
            invalid = sr.status != ConvergenceStatus.CONVERGED
            color = "#9CA3AF" if invalid else alert_color.get(
                sr.alert_level.value, "#10B981",
            )
            ax.plot(
                [lr.fairlead_xy[0], lr.anchor_xy[0]],
                [lr.fairlead_xy[1], lr.anchor_xy[1]],
                color=color, linewidth=2.0 if not invalid else 1.0,
                linestyle="--" if invalid else "-", alpha=0.85,
            )
            # Fairlead
            ax.plot(*lr.fairlead_xy, marker="o", markersize=6, color=color)
            # Anchor
            ax.plot(*lr.anchor_xy, marker="^", markersize=8, color=color)
            # Label
            mx = lr.fairlead_xy[0] + 0.6 * (lr.anchor_xy[0] - lr.fairlead_xy[0])
            my = lr.fairlead_xy[1] + 0.6 * (lr.anchor_xy[1] - lr.fairlead_xy[1])
            ax.annotate(lr.line_name, (mx, my), fontsize=9, ha="center",
                        va="bottom", color="#222222")
        # Resultante
        if result and result.aggregate_force_magnitude > 0:
            fx, fy = result.aggregate_force_xy
            mag = (fx**2 + fy**2) ** 0.5
            tlen = max_radius * 0.4
            ax.annotate(
                "", xy=(fx / mag * tlen, fy / mag * tlen), xytext=(0, 0),
                arrowprops=dict(
                    arrowstyle="-|>", color="#EC4899", lw=2.0, alpha=0.9,
                ),
            )
    else:
        # Modo sem resultado — só linhas radiais com âncoras estimadas
        import math as _math
        for line in msys_input.lines:
            theta = _math.radians(line.fairlead_azimuth_deg)
            fx = line.fairlead_radius * _math.cos(theta)
            fy = line.fairlead_radius * _math.sin(theta)
            ar = line.fairlead_radius * 4
            ax_x = ar * _math.cos(theta)
            ay = ar * _math.sin(theta)
            ax.plot([fx, ax_x], [fy, ay],
                    color="#888888", linestyle="--", linewidth=1.2, alpha=0.6)
            ax.plot(fx, fy, marker="o", markersize=5, color="#888888")
            ax.annotate(line.name,
                        ((fx + ax_x) / 2, (fy + ay) / 2),
                        fontsize=9, ha="center", va="bottom",
                        color="#444444")

    ax.set_xlim(-span, span)
    ax.set_ylim(-span, span)
    ax.set_aspect("equal", adjustable="box")
    ax.axhline(0, color="#bbbbbb", linewidth=0.5)
    ax.axvline(0, color="#bbbbbb", linewidth=0.5)
    ax.set_xlabel("X (m) — proa →")
    ax.set_ylabel("Y (m) — bombordo ↑")
    ax.set_title("Plan view do mooring system")
    ax.grid(True, alpha=0.18)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _msys_meta_table(
    msys_rec: MooringSystemRecord, msys_input: MooringSystemInput,
) -> list[list[str]]:
    return [
        ["Grandeza", "Valor"],
        ["Nome do sistema", msys_input.name],
        ["Descrição", msys_input.description or "—"],
        ["Raio plataforma (m)", f"{msys_input.platform_radius:.2f}"],
        ["Nº de linhas", str(len(msys_input.lines))],
        ["ID", str(msys_rec.id)],
    ]


def _msys_aggregate_table(result: MooringSystemResult) -> list[list[str]]:
    mag_kn = result.aggregate_force_magnitude / 1000
    return [
        ["Métrica", "Valor"],
        ["Resultante (kN)", f"{mag_kn:.2f}"],
        [
            "Direção (°)",
            (
                f"{result.aggregate_force_azimuth_deg:.1f}"
                if result.aggregate_force_magnitude > 0
                else "— (≈ 0)"
            ),
        ],
        [
            "Linhas convergidas",
            f"{result.n_converged} / {len(result.lines)}",
        ],
        ["Linhas inválidas", str(result.n_invalid)],
        ["Máx. utilização", f"{result.max_utilization * 100:.2f}%"],
        ["Pior alerta", result.worst_alert_level.value],
        ["Solver", result.solver_version or "—"],
    ]


def _msys_lines_table(
    msys_input: MooringSystemInput,
    result: Optional[MooringSystemResult],
) -> list[list[str]]:
    rows: list[list[str]] = [
        ["Linha", "Az (°)", "R (m)", "T_fl/X input", "H (kN)",
         "Util.", "Alerta", "Status"],
    ]
    for idx, line in enumerate(msys_input.lines):
        bc = line.boundary
        input_label = (
            f"{bc.input_value / 1000:.1f} kN" if bc.mode.value == "Tension"
            else f"{bc.input_value:.1f} m"
        )
        lr = result.lines[idx] if result else None
        sr = lr.solver_result if lr else None
        h_kn = f"{sr.H / 1000:.1f}" if sr else "—"
        util = f"{sr.utilization * 100:.1f}%" if sr else "—"
        alert = sr.alert_level.value if sr else "—"
        status = sr.status.value if sr else "—"
        rows.append([
            line.name,
            f"{line.fairlead_azimuth_deg:.1f}",
            f"{line.fairlead_radius:.1f}",
            input_label,
            h_kn,
            util,
            alert,
            status,
        ])
    return rows


def build_mooring_system_pdf(
    msys_rec: MooringSystemRecord,
    execution: Optional[MooringSystemExecutionRecord],
) -> bytes:
    """
    Relatório PDF do mooring system multi-linha (F5.4.5c).

    Layout:
      1. Header (sistema, timestamp, solver version)
      2. Disclaimer técnico (mesmo da Seção 10 do Documento A)
      3. Tabela de metadados
      4. Plan view 2D (matplotlib → PNG → embed)
      5. Tabela de agregados (resultante, direção, etc.)
      6. Tabela por linha (Az, R, H, util, alerta, status)

    Sem execução, gera relatório só com inputs + plan view sem
    posições resolvidas.
    """
    msys_input = MooringSystemInput.model_validate_json(msys_rec.config_json)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"QMoor — {msys_input.name}",
    )
    styles = getSampleStyleSheet()
    if "HeaderSmall" not in styles.byName:
        styles.add(ParagraphStyle(
            name="HeaderSmall", parent=styles["Normal"],
            fontSize=9, textColor=colors.HexColor("#555555"),
        ))
    if "DisclaimerBox" not in styles.byName:
        styles.add(ParagraphStyle(
            name="DisclaimerBox", parent=styles["Normal"],
            fontSize=8, textColor=colors.HexColor("#606060"),
            borderPadding=6, borderColor=colors.HexColor("#cccccc"),
            borderWidth=0.5, leading=10,
        ))

    story: list = []

    # Header
    story.append(Paragraph(
        "<b>QMoor Web — Relatório de mooring system</b>", styles["Title"],
    ))
    story.append(Paragraph(
        f"Sistema: <b>{msys_input.name}</b> (id {msys_rec.id})",
        styles["Heading3"],
    ))
    now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S %Z")
    story.append(Paragraph(
        f"Gerado em {now} — Solver versão {SOLVER_VERSION}",
        styles["HeaderSmall"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    # Disclaimer
    story.append(Paragraph("<b>Disclaimer técnico</b>", styles["Heading4"]))
    story.append(Paragraph(DISCLAIMER, styles["DisclaimerBox"]))
    story.append(Spacer(1, 0.4 * cm))

    # Metadados
    story.append(Paragraph("<b>Configuração</b>", styles["Heading3"]))
    meta = Table(_msys_meta_table(msys_rec, msys_input), colWidths=[6 * cm, 8 * cm])
    meta.setStyle(_base_table_style())
    story.append(meta)
    story.append(Spacer(1, 0.4 * cm))

    result = (
        MooringSystemResult.model_validate_json(execution.result_json)
        if execution is not None
        else None
    )

    # Plan view
    story.append(Paragraph("<b>Plan view</b>", styles["Heading3"]))
    png = _plan_view_png(msys_input, result)
    story.append(Image(io.BytesIO(png), width=14 * cm, height=14 * cm))
    story.append(Spacer(1, 0.4 * cm))

    if result is None:
        story.append(Paragraph(
            "Nenhuma execução do solver disponível para este sistema. "
            "Execute POST /mooring-systems/{id}/solve antes de gerar "
            "o relatório completo.",
            styles["Normal"],
        ))
        doc.build(story)
        return buf.getvalue()

    # Agregados
    story.append(PageBreak())
    story.append(Paragraph("<b>Resultante agregado</b>", styles["Heading3"]))
    agg = Table(_msys_aggregate_table(result), colWidths=[6 * cm, 8 * cm])
    agg.setStyle(_base_table_style())
    # Pinta a célula do "Pior alerta" com a cor correspondente.
    for i, row in enumerate(_msys_aggregate_table(result)):
        if row[0] == "Pior alerta":
            agg.setStyle(TableStyle([
                ("TEXTCOLOR", (1, i), (1, i),
                 _alert_color(result.worst_alert_level.value)),
                ("FONTNAME", (1, i), (1, i), "Helvetica-Bold"),
            ]))
    story.append(agg)
    story.append(Spacer(1, 0.4 * cm))

    # Tabela por linha
    story.append(Paragraph("<b>Detalhe por linha</b>", styles["Heading3"]))
    lines_table = Table(
        _msys_lines_table(msys_input, result),
        colWidths=[
            2.4 * cm, 1.5 * cm, 1.5 * cm, 2.6 * cm,
            1.8 * cm, 1.7 * cm, 1.8 * cm, 2.4 * cm,
        ],
    )
    lines_table.setStyle(_base_table_style())
    story.append(lines_table)
    story.append(Spacer(1, 0.4 * cm))

    doc.build(story)
    return buf.getvalue()


__all__ = ["build_pdf", "build_mooring_system_pdf", "DISCLAIMER"]
