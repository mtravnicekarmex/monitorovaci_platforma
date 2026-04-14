"""
Export prehledu preppojovani podrouznych vodomeru do PDF.
Zobrazuje casove osy pro kazdou vetev potrubi.
"""
from datetime import timedelta
import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from moduly.mereni.vodomery.SCVK.historie_vetve import (
    INTERVALY_vetev_L,
    INTERVALY_vetev_dok_voda,
    INTERVALY_vetev_dok_poz_voda,
    INTERVALY_vetev_grobar,
)

# Registrace fontu s podporou češtiny - použijeme Arial Unicode
pdfmetrics.registerFont(TTFont('ArialUnicode', 'C:/Windows/Fonts/ARIALUNI.ttf'))
pdfmetrics.registerFont(TTFont('ArialUnicodeBold', 'C:/Windows/Fonts/ARIALUNI.ttf'))


def fmt_dt(dt):
    """Format datumu a casu pro PDF."""
    if dt.year == 2099:
        return "dnes"
    return dt.strftime("%d.%m.%Y %H:%M")


# Definice barev pro intervaly
BARVY = [
    colors.HexColor("#2E86AB"),
    colors.HexColor("#A23B72"),
    colors.HexColor("#F18F01"),
    colors.HexColor("#C73E1D"),
    colors.HexColor("#44AF69"),
    colors.HexColor("#6B2D5C"),
    colors.HexColor("#1B998B"),
    colors.HexColor("#4A1942"),
    colors.HexColor("#D4A017"),
    colors.HexColor("#556B2F"),
]

BARVY_Svetle = [
    colors.HexColor("#D4E8F0"),
    colors.HexColor("#EDD5E3"),
    colors.HexColor("#FDE8C8"),
    colors.HexColor("#F5D0C5"),
    colors.HexColor("#D4F0D8"),
    colors.HexColor("#E5D0E3"),
    colors.HexColor("#D0F0ED"),
    colors.HexColor("#E5D0E0"),
    colors.HexColor("#F5ECD0"),
    colors.HexColor("#E0E8D0"),
]


def generate_pdf(output_path):
    """Vygeneruje PDF s prehledem."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        fontName='ArialUnicodeBold',
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=15,
        spaceAfter=10,
        fontName='ArialUnicodeBold',
    )
    cell_style = ParagraphStyle(
        'cell',
        fontName='ArialUnicode',
        fontSize=7,
        leading=10,
    )

    elements = []

    # Pouze detailni prehled
    elements.append(Paragraph("Detailni prehled intervalu", title_style))
    elements.append(Spacer(1, 0.5*cm))

    větve = [
        ("HECHT (vetev L)", INTERVALY_vetev_L),
        ("DOKTOR VODA", INTERVALY_vetev_dok_voda),
        ("DOKTOR POŽÁRNÍ VODA", INTERVALY_vetev_dok_poz_voda),
        ("GROBÁŘ", INTERVALY_vetev_grobar),
    ]

    for vetev_nazev, intervaly in větve:
        # Cela tabulka je v KeepTogether aby nebyla rozdelena mezi strankami
        table_block = []

        table_block.append(Paragraph(vetev_nazev, heading_style))

        table_data = [["#", "Od", "Do", "Pocet", "Vodomery"]]
        for idx, (dt_from, dt_to, meters) in enumerate(intervaly):
            meters_str = ", ".join(meters)
            table_data.append([
                str(idx + 1),
                fmt_dt(dt_from),
                fmt_dt(dt_to),
                str(len(meters)),
                meters_str
            ])

        # Pouzijeme Paragraph pro text vodomeru aby se zalamoval
        formatted_data = [table_data[0]]
        for row in table_data[1:]:
            formatted_data.append([
                row[0],
                row[1],
                row[2],
                row[3],
                Paragraph(row[4], cell_style)
            ])

        # Sirsi sloupce pro landscape A4 (277mm dostupne po odecteni 2cm okraju)
        col_widths = [1*cm, 4*cm, 4*cm, 1.5*cm, 16.5*cm]
        t = Table(formatted_data, colWidths=col_widths)

        header_style = TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'ArialUnicodeBold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2E86AB")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (3, -1), 'CENTER'),
            ('LEFTPADDING', (4, 0), (4, -1), 5),
            ('RIGHTPADDING', (4, 0), (4, -1), 5),
        ])

        for row_idx in range(1, len(formatted_data)):
            barva = BARVY[(row_idx - 1) % len(BARVY)]
            svetla = BARVY_Svetle[(row_idx - 1) % len(BARVY_Svetle)]
            header_style.add('BACKGROUND', (0, row_idx), (0, row_idx), barva)
            header_style.add('TEXTCOLOR', (0, row_idx), (0, row_idx), colors.white)
            header_style.add('TEXTCOLOR', (1, row_idx), (-1, row_idx), colors.black)
            if row_idx % 2 == 0:
                header_style.add('BACKGROUND', (1, row_idx), (-1, row_idx), svetla)

        t.setStyle(header_style)
        table_block.append(t)
        table_block.append(Spacer(1, 0.5*cm))

        # Zabalime cely blok do KeepTogether
        elements.append(KeepTogether(table_block))

    doc.build(elements)
    print(f"PDF vytvoreno: {output_path}")


if __name__ == "__main__":
    output = "historie_vetvi.pdf"
    generate_pdf(output)