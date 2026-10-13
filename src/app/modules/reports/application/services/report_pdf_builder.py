"""Build a printable PDF from one immutable migration-report snapshot."""

from collections import Counter
from datetime import UTC
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import ReportRuleMigrationResult
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


class ReportPdfBuilder:
    """Render the complete saved report snapshot as an English PDF document."""

    def build(self, *, report: Report, csp_profile: CSPProfileHeaderDTO) -> bytes:
        """Return a landscape A4 PDF for one report and all of its saved rules."""
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            title=report.title,
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )
        rules = report.rules or ()
        story = [
            Paragraph(escape(report.title), _title_style()),
            Spacer(1, 4 * mm),
            _metadata_table(report=report, csp_profile=csp_profile),
            Spacer(1, 4 * mm),
            Paragraph(_summary_text(rules), _summary_style()),
            Spacer(1, 3 * mm),
            _rules_table(rules),
        ]
        document.build(story)
        return output.getvalue()


def _title_style() -> ParagraphStyle:
    return ParagraphStyle(
        "ReportTitle",
        parent=getSampleStyleSheet()["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
    )


def _body_style() -> ParagraphStyle:
    return ParagraphStyle(
        "ReportBody",
        parent=getSampleStyleSheet()["BodyText"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
    )


def _summary_style() -> ParagraphStyle:
    return ParagraphStyle(
        "ReportSummary",
        parent=_body_style(),
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        leftIndent=10 * mm,
        rightIndent=10 * mm,
    )


def _metadata_table(
    *,
    report: Report,
    csp_profile: CSPProfileHeaderDTO,
) -> Table:
    rows = (
        (
            "Created at (UTC)",
            report.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "CSP profile",
            f"{csp_profile.name} ({csp_profile.base_url})",
        ),
        (
            "Project / VPC",
            f"{report.environment.project_name} / {report.environment.vpc_id}",
            "Install-On / Target ID",
            f"{report.environment.target_name} / {report.environment.target_id}",
        ),
    )
    table = Table(
        [[_paragraph(value, _body_style()) for value in row] for row in rows],
        colWidths=(28 * mm, 103 * mm, 28 * mm, 98 * mm),
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B0B0")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F2F2F2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _summary_text(rules: tuple[ReportRule, ...]) -> str:
    counts = Counter(rule.migration_result for rule in rules)
    result_counts = ", ".join(
        f"{result.value}: {counts[result]}" for result in ReportRuleMigrationResult
    )
    return f"Policies: {len(rules)} | {result_counts}"


def _rules_table(rules: tuple[ReportRule, ...]) -> LongTable:
    rows = [
        (
            "Priority",
            "Policy / action",
            "Source",
            "Destination",
            "Services",
            "Result",
            "Reason",
        ),
        *(_rule_row(rule) for rule in rules),
    ]
    table = LongTable(
        [
            [
                _paragraph(value, _body_style()) if isinstance(value, str) else value
                for value in row
            ]
            for row in rows
        ],
        colWidths=(16 * mm, 34 * mm, 47 * mm, 47 * mm, 32 * mm, 24 * mm, 57 * mm),
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B0B0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (5, 0), (5, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _rule_row(rule: ReportRule) -> tuple[str | Paragraph, ...]:
    return (
        str(rule.priority),
        Paragraph(f"{rule.policy_name}<br/><b>{rule.action.value}</b>", _body_style()),
        _endpoint_paragraph(rule.src_zone_names, rule.src_addr_values),
        _endpoint_paragraph(rule.dst_zone_names, rule.dst_addr_values),
        _values(rule.service_values),
        rule.migration_result.value,
        rule.reason,
    )


def _endpoint_paragraph(
    zones: tuple[str, ...],
    addresses: tuple[str, ...],
) -> Paragraph:
    return Paragraph(
        f"<b>Zones:</b> {escape(_values(zones))}<br/>"
        f"<b>Addresses:</b> {escape(_values(addresses))}",
        _body_style(),
    )


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "-"


def _paragraph(value: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(value).replace("\n", "<br/>"), style)
