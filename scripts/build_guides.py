"""Builds the Word (.docx) copies of the two guides in docs/guides/ from their Markdown, and draws the network diagram.

    python scripts/build_guides.py

Needs python-docx and Pillow (developer tools, not part of the shipped program). The Markdown files are the source; the pictures in
docs/guides/img/ come from `SCREENSHOTS=1 npx playwright test e2e/screenshots-guides.spec.ts` (run in desktop/).
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

GUIDES = Path(__file__).resolve().parents[1] / "docs" / "guides"
IMG = GUIDES / "img"
FILES = ["USER_GUIDE", "NETWORK_SETUP_GUIDE"]


# ---------------------------------------------------------------------------------------------------------------- the diagram
def font(size: int, bold: bool = False):
    for name in (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_network_diagram(path: Path) -> None:
    w, h = 1300, 640
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    ink, line, green, amber = (27, 36, 32), (138, 143, 135), (22, 101, 52), (146, 64, 14)

    def box(x, y, bw, bh, title, sub, fill, edge=ink):
        d.rounded_rectangle((x, y, x + bw, y + bh), radius=18, fill=fill, outline=edge, width=3)
        tw = d.textlength(title, font=font(26, True))
        d.text((x + (bw - tw) / 2, y + 18), title, fill=ink, font=font(26, True))
        for i, row in enumerate(sub):
            sw = d.textlength(row, font=font(20))
            d.text((x + (bw - sw) / 2, y + 62 + i * 28), row, fill=(70, 80, 75), font=font(20))

    def cable(a, b, wifi=False):
        if wifi:
            n = 24
            for i in range(0, n, 2):
                x1 = a[0] + (b[0] - a[0]) * i / n
                y1 = a[1] + (b[1] - a[1]) * i / n
                x2 = a[0] + (b[0] - a[0]) * (i + 1) / n
                y2 = a[1] + (b[1] - a[1]) * (i + 1) / n
                d.line((x1, y1, x2, y2), fill=amber, width=5)
        else:
            d.line((a, b), fill=green, width=7)

    box(450, 30, 400, 120, "MAIN PC", ["keeps ALL the data", "switched on all day"], (220, 243, 227), green)
    box(500, 250, 300, 100, "ROUTER / SWITCH", ["the pump's own network"], (240, 238, 230))
    cable((650, 150), (650, 250))
    xs = [60, 470, 880]
    names = [("COUNTER PC", ["Client PC", "keeps no data"], False), ("ACCOUNTANT'S PC", ["Client PC", "keeps no data"], False), ("OWNER'S LAPTOP", ["Client PC", "keeps no data"], True)]
    for x, (title, sub, wifi) in zip(xs, names):
        box(x, 470, 360, 120, title, sub, (255, 255, 255))
        cable((650, 350), (x + 180, 470), wifi)
    d.text((40, 190), "network cable", fill=green, font=font(22, True))
    d.line((40, 224, 200, 224), fill=green, width=7)
    d.text((1010, 190), "Wi-Fi", fill=amber, font=font(22, True))
    for i in range(0, 8, 2):
        d.line((1010 + i * 14, 224, 1010 + (i + 1) * 14, 224), fill=amber, width=5)
    d.text((900, 50), "No line leaves this picture:\nnothing connects to the internet.", fill=(70, 80, 75), font=font(22))
    IMG.mkdir(parents=True, exist_ok=True)
    img.save(path)


# ---------------------------------------------------------------------------------------------------------------- Markdown to Word
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)")


def add_runs(par, text: str) -> None:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = par.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            par.add_run(part[1:-1]).italic = True
        else:
            par.add_run(part)


def cells(row: str):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def convert(md_path: Path, out_path: Path) -> None:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    lines = md_path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or s == "---":
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i].strip())
                i += 1
            i += 1
            for row in block:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.4)
                r = p.add_run(row)
                r.font.name = "Consolas"
                r.font.size = Pt(9.5)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            doc.add_heading(m.group(2), level=len(m.group(1)) - 1 if len(m.group(1)) > 1 else 0)
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", s)
        if m:
            pic = GUIDES / m.group(2)
            if pic.exists():
                doc.add_picture(str(pic), width=Inches(6.2))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                if m.group(1):
                    cap = doc.add_paragraph()
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = cap.add_run(m.group(1))
                    run.italic = True
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0x55, 0x60, 0x5A)
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            body = [cells(r) for r in rows if not re.match(r"^\|\s*:?-{2,}", r.strip())]
            table = doc.add_table(rows=len(body), cols=len(body[0]))
            table.style = "Light Grid Accent 1"
            for ri, row in enumerate(body):
                for ci, text in enumerate(row[: len(body[0])]):
                    cell = table.cell(ri, ci)
                    cell.text = ""
                    add_runs(cell.paragraphs[0], text)
                    for run in cell.paragraphs[0].runs:
                        run.font.size = Pt(9.5)
                        if ri == 0:
                            run.bold = True
            doc.add_paragraph()
            continue
        m = re.match(r"^(\s*)([*-]|\d+\.)\s+(.*)", line)
        if m:
            indent = len(m.group(1))
            style = "List Number" if m.group(2)[0].isdigit() else "List Bullet"
            if indent >= 2:
                style += " 2"
            p = doc.add_paragraph(style=style)
            add_runs(p, m.group(3))
            i += 1
            continue
        if s.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            add_runs(p, s.lstrip("> "))
            i += 1
            continue
        # a paragraph: join the lines until a blank line
        text = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|```|\s*([*-]|\d+\.)\s)", lines[i].strip()) and lines[i].strip() != "---":
            text.append(lines[i].strip())
            i += 1
        add_runs(doc.add_paragraph(), " ".join(text))
    doc.save(out_path)


def main() -> None:
    draw_network_diagram(IMG / "network-diagram.png")
    for name in FILES:
        convert(GUIDES / f"{name}.md", GUIDES / f"{name}.docx")
        print("wrote", GUIDES / f"{name}.docx")


if __name__ == "__main__":
    sys.exit(main())
