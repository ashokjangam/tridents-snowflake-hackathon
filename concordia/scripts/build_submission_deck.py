"""Build the Concordia submission deck on the CoCo CLI template.

Slide 1 is kept from the existing deck. Slides 2-6 are rebuilt as native shapes on the template backgrounds.
Every figure on the slides is copied from data/generated/verification.json or the deployed account; nothing is calculated here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT.parent / "docs" / "submission" / "CONCORDIA-Prototype-Deck.pptx"
TEMPLATE = Path.home() / "Downloads" / "Prototype Submission Template _ CoCo CLI Hackathon GCC Edition (1).pptx"
SHOTS = ROOT / "data" / "generated" / "screens"
FACTS = json.loads((ROOT / "data" / "generated" / "deck_facts.json").read_text(encoding="utf-8"))

NAVY, BLUE, TEAL, SLATE = RGBColor(0x10, 0x2A, 0x43), RGBColor(0x17, 0x46, 0xA2), RGBColor(0x0E, 0x9F, 0x9A), RGBColor(0x51, 0x6D, 0x83)
LINE, MIST, WHITE, AMBER = RGBColor(0xD4, 0xDE, 0xE8), RGBColor(0xF3, 0xF6, 0xFA), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0xB7, 0x79, 0x1F)
TEAL_TINT, BLUE_TINT, AMBER_TINT = RGBColor(0xE6, 0xF6, 0xF4), RGBColor(0xEA, 0xF0, 0xFD), RGBColor(0xFD, 0xF3, 0xE1)
FONT = "Calibri"


# ---------------------------------------------------------------- primitives
def text(slide, x, y, w, h, runs, size=12, color=NAVY, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, name=None, spacing=0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = anchor
    paragraphs = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paragraphs):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        for part in para if isinstance(para, tuple) else (para,):
            if isinstance(part, str):
                part = {"t": part}
            r = p.add_run()
            r.text = part["t"]
            r.font.name = FONT
            r.font.size = Pt(part.get("size", size))
            r.font.bold = part.get("bold", bold)
            r.font.italic = part.get("italic", False)
            r.font.color.rgb = part.get("color", color)
    return box


def box(slide, x, y, w, h, fill=WHITE, line=LINE, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=False, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(0.75)
    if not shadow:
        sp_pr = s._element.spPr
        effect = sp_pr.find(qn("a:effectLst"))
        if effect is None:
            sp_pr.append(sp_pr.makeelement(qn("a:effectLst"), {}))
    s.text_frame.text = ""
    return s


def label(shape, runs, size=11, color=NAVY, bold=False, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.06):
    frame = shape.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = Inches(margin)
    frame.margin_top = frame.margin_bottom = Inches(0.03)
    paragraphs = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paragraphs):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.alignment = align
        for part in para if isinstance(para, tuple) else (para,):
            if isinstance(part, str):
                part = {"t": part}
            r = p.add_run()
            r.text = part["t"]
            r.font.name = FONT
            r.font.size = Pt(part.get("size", size))
            r.font.bold = part.get("bold", bold)
            r.font.color.rgb = part.get("color", color)
    return shape


def arrow(slide, x1, y1, x2, y2, color=SLATE, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def background(slide, image: Path):
    pic = slide.shapes.add_picture(str(image), 0, 0, Inches(10), Inches(5.625))
    pic.name = "Template background"
    tree = slide.shapes._spTree
    tree.remove(pic._element)
    tree.insert(2, pic._element)


def title(slide, heading: str, sub: str | None = None):
    text(slide, 0.45, 0.7, 9.1, 0.45, heading, size=22, bold=True, name="Title")
    if sub:
        text(slide, 0.45, 1.14, 9.1, 0.3, sub, size=11.5, color=SLATE, name="Subtitle")


def footnote(slide, note: str):
    text(slide, 0.45, 5.17, 9.1, 0.25, note, size=8.5, color=SLATE, name="Footnote")


# ---------------------------------------------------------------- slides
def slide_problem(slide):
    title(slide, "One question. Six source systems. Too many answers.",
          "Mid-size discrete manufacturer · supply chain leadership, procurement, logistics, planning and finance")
    q = box(slide, 0.45, 1.6, 5.35, 0.5, fill=NAVY, line=None, radius=0.25)
    label(q, [({"t": "“What was our on-time delivery in May?”", "bold": True, "size": 14, "color": WHITE},)])
    teams = [
        ("Procurement", "ERP", "on time = received by the PO need date"),
        ("Logistics", "TMS", "on time = left the dock by carrier pickup"),
        ("Customer service", "CRM", "measured against the latest revised promise"),
        ("Planning", "WMS · MES", "last night's snapshot, different part numbers"),
        ("Finance", "ERP", "missing freight booked as zero cost"),
    ]
    y = 2.25
    for team, system, rule in teams:
        chip = box(slide, 0.45, y, 1.55, 0.44, fill=BLUE_TINT, line=None, radius=0.2)
        label(chip, [({"t": team, "bold": True, "size": 10.5, "color": BLUE},)])
        text(slide, 2.12, y + 0.02, 0.95, 0.4, system, size=10, color=SLATE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 3.05, y + 0.02, 2.8, 0.4, rule, size=10.5, anchor=MSO_ANCHOR.MIDDLE)
        y += 0.55

    card = box(slide, 6.15, 1.6, 3.4, 3.45, fill=MIST, line=None, radius=0.05)
    card.name = "Pain card"
    text(slide, 6.4, 1.75, 2.95, 0.3, "What it costs today", size=13, bold=True)
    pains = [
        "Review meetings open by reconciling numbers, not deciding",
        "Month-end numbers move later with no record of why",
        "Chat over raw tables invents a sixth answer",
        "Cost and audit data leak to people who should not see them",
    ]
    text(slide, 6.4, 2.12, 2.95, 1.9, [({"t": "•  " + p},) for p in pains], size=10.5, spacing=5)
    promise = box(slide, 6.4, 4.05, 2.95, 0.85, fill=TEAL, line=None, radius=0.1)
    label(promise, [({"t": "Concordia: ", "bold": True, "color": WHITE, "size": 10.5},
                     {"t": "each metric defined once, computed once in Snowflake, the same for every team, with its evidence attached.",
                      "color": WHITE, "size": 10.5})], align=PP_ALIGN.LEFT, margin=0.12)
    footnote(slide, "Team definitions are illustrative of common practice, not measurements of a specific company.")


def slide_architecture(slide):
    title(slide, "Architecture: one governed path from source record to answer",
          "Snowflake-native end to end · the language model routes and narrates, SQL computes every number")
    cols = [
        (0.35, 1.45, "SOURCES", None),
        (2.05, 1.75, "LAND", ["RAW_RECORD", "append-only, hashed", "Stream + Task", f"Quarantine · {FACTS['quarantined']}"]),
        (4.1, 1.85, "CORE", ["Identity resolution", "Ontology: part · party ·", "facility · geography", "Ledger + knowledge graph", "Metric SQL  M1–M5"]),
        (6.25, 1.65, "APP", ["Published grid", f"{FACTS['as_of_points']} as-of points", "Persona-masked", "secure functions", "Semantic view"]),
        (8.2, 1.45, "EXPERIENCE", None),
    ]
    top, height = 1.62, 2.7
    header_fill = {"SOURCES": SLATE, "LAND": BLUE, "CORE": NAVY, "APP": TEAL, "EXPERIENCE": BLUE}
    for x, w, name, lines in cols:
        body = box(slide, x, top, w, height, fill=WHITE, line=LINE, radius=0.06)
        body.name = f"{name} column"
        head = box(slide, x, top, w, 0.38, fill=header_fill[name], line=None, radius=0.25)
        label(head, [({"t": name, "bold": True, "size": 11, "color": WHITE},)])
        if lines:
            text(slide, x + 0.12, top + 0.52, w - 0.24, height - 0.6, [({"t": line},) for line in lines], size=10, spacing=3,
                 align=PP_ALIGN.LEFT)
    y = top + 0.5
    for system, what in (("ERP", "orders · costs"), ("MES", "production"), ("WMS", "stock · holds"),
                         ("TMS", "shipments"), ("CRM", "promises"), ("IoT", "docks · lots")):
        chip = box(slide, 0.47, y, 1.21, 0.38, fill=MIST, line=None, radius=0.2)
        label(chip, [({"t": system + "  ", "bold": True, "size": 10}, {"t": what, "size": 8.5, "color": SLATE})])
        y += 0.355
    y = top + 0.52
    for head, sub in (("Streamlit in Snowflake", "7 pages, owner role"), ("Ask Concordia", "Analyst + SQL guard"),
                      ("Cortex Analyst", "ontology-first answers")):
        chip = box(slide, 8.3, y, 1.25, 0.6, fill=BLUE_TINT, line=None, radius=0.15)
        label(chip, [({"t": head, "bold": True, "size": 9.5, "color": BLUE},), ({"t": sub, "size": 8.5, "color": SLATE},)])
        y += 0.7
    mid = top + height / 2
    for x_from, x_to in ((1.8, 2.05), (3.8, 4.1), (5.95, 6.25), (7.9, 8.2)):
        arrow(slide, x_from + 0.02, mid, x_to - 0.02, mid, color=SLATE, width=2)
    gov = box(slide, 2.05, 4.45, 7.6, 0.58, fill=AMBER_TINT, line=None, radius=0.15)
    gov.name = "GOV band"
    label(gov, [({"t": "GOV   ", "bold": True, "size": 11, "color": AMBER},
                 {"t": "metric contracts (versioned, hashed) · entitlements · rejected aliases · evidence · query audit · pipeline runs",
                  "size": 10, "color": NAVY})], align=PP_ALIGN.LEFT, margin=0.15)
    text(slide, 0.35, 4.45, 1.55, 0.6, [({"t": "Synthetic world", "bold": True, "size": 9.5},),
                                         ({"t": "seeded simulator, 2 batches", "size": 8.5, "color": SLATE},)], anchor=MSO_ANCHOR.MIDDLE)
    footnote(slide, "Roles: ADMIN builds, TRANSFORM runs the task, APP_OWNER (never ACCOUNTADMIN) owns the app and uses governed interfaces.")


def slide_solution(slide):
    title(slide, "What every team gets: one number, its definition, its evidence",
          "Live Streamlit in Snowflake app over the governed APP layer")
    shot = SHOTS / "command-center.png"
    if shot.exists():
        frame = box(slide, 0.42, 1.55, 5.46, 3.5, fill=WHITE, line=LINE, radius=0.02)
        frame.name = "Screenshot frame"
        slide.shapes.add_picture(str(shot), Inches(0.47), Inches(1.6), Inches(5.36), Inches(3.4))
    features = [
        ("1", "Five governed metrics", "Supplier OTD, customer OTD, fill rate, days of inventory, landed cost. Versioned, hashed contracts."),
        ("2", "Ask over the ontology", "Cortex Analyst generates semantic SQL; a guard proves metric rows against the exact published scope."),
        ("3", "Ambiguity is refused", "Bare “OTD” asks inbound or outbound. “OTIF” is rejected. Missing cost stays incomplete."),
        ("4", "As-of replay", "What was known on the 5th versus final, and what each late load restated."),
        ("5", "Cross-domain evidence", "Supplier-to-customer paths, substitutions, lots, production consumption and synthetic IoT dock events."),
    ]
    y = 1.55
    for n, head, body in features:
        dot = box(slide, 6.15, y + 0.03, 0.36, 0.36, fill=TEAL, line=None, shape=MSO_SHAPE.OVAL)
        label(dot, [({"t": n, "bold": True, "size": 11, "color": WHITE},)], margin=0)
        text(slide, 6.62, y, 2.95, 0.25, head, size=11.5, bold=True)
        text(slide, 6.62, y + 0.25, 2.95, 0.45, body, size=9.5, color=SLATE)
        y += 0.71
    footnote(slide, "Screenshot: Command center as the VP Supply Chain persona, MM-440, May 2026, final as-of. Synthetic data.")


def slide_end_to_end(slide):
    title(slide, "End to end, verified on the deployed account",
          "Synthetic world CONCORDIA_SIM_V1 · two extract batches · every check re-run against live Snowflake")
    steps = [("Generate", f"{FACTS['raw_records']} records"), ("Land", "stream + quarantine"), ("Resolve", "one part, one party"),
             ("Compute", "SQL metric functions"), ("Publish", f"{FACTS['result_rows']} results"), ("Ask", "evidenced answer")]
    x, w = 0.45, 1.46
    for i, (head, sub) in enumerate(steps):
        cx = x + i * (w + 0.07)
        box(slide, cx, 1.55, w, 0.62, fill=NAVY if i % 2 == 0 else BLUE, line=None, shape=MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON)
        inset = 0.12 if i == 0 else 0.26
        text(slide, cx + inset, 1.58, w - inset - 0.2, 0.56, [({"t": head, "bold": True, "size": 11, "color": WHITE},),
                                                               ({"t": sub, "size": 8, "color": WHITE},)],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    stats = [(FACTS["golden"], "golden checks", "SQL equals the independent Python reference"),
             (FACTS["grid"], "grid samples", "published rows equal a live function call"),
             (FACTS["hero"], "hero checks", "including the restated landed cost"),
             (FACTS["security"], "security checks", "masking, alias refusal, role isolation")]
    for i, (big, head, sub) in enumerate(stats):
        cx = 0.45 + i * 2.3
        card = box(slide, cx, 2.4, 2.15, 1.25, fill=MIST, line=None, radius=0.08)
        card.name = f"Stat {head}"
        text(slide, cx + 0.15, 2.48, 1.9, 0.55, big, size=26, bold=True, color=TEAL)
        text(slide, cx + 0.15, 3.0, 1.9, 0.22, head, size=11, bold=True)
        text(slide, cx + 0.15, 3.22, 1.9, 0.4, sub, size=9, color=SLATE)
    story = box(slide, 0.45, 3.85, 9.1, 1.2, fill=WHITE, line=LINE, radius=0.05)
    story.name = "Hero story"
    text(slide, 0.65, 3.95, 8.7, 0.25, "Hero: MM-440 servo motor, May 2026, one answer for every team", size=11.5, bold=True)
    hero = [("Supplier OTD", FACTS["m1"]), ("Customer OTD", FACTS["m2"]), ("Fill rate", FACTS["m3"]),
            ("Landed cost, 5 Jun", FACTS["m5_early"]), ("Landed cost, 15 Jul", FACTS["m5_final"])]
    for i, (head, value) in enumerate(hero):
        hx = 0.65 + i * 1.75
        text(slide, hx, 4.25, 1.65, 0.22, head, size=9, color=SLATE, bold=True)
        text(slide, hx, 4.45, 1.65, 0.5, value, size=12.5 if len(value) < 16 else 10.5, bold=True,
             color=AMBER if "INCOMPLETE" in value else NAVY)
    footnote(slide, "All data is synthetic. Parity checks prove consistency, not business impact; time saved and accuracy on real ERP data are not measured.")


def slide_thanks(slide):
    text(slide, 0.5, 5.12, 9.0, 0.3, [({"t": "CONCORDIA  ", "bold": True, "color": WHITE, "size": 11},
                                        {"t": "Different teams. Same truth.   github.com/ashokjangam/snowcore-pdm", "color": WHITE, "size": 10})])


# ---------------------------------------------------------------- assembly
def drop_slides_after_first(deck):
    ids = deck.slides._sldIdLst
    for sld in list(ids)[1:]:
        deck.part.drop_rel(sld.get(qn("r:id")))
        ids.remove(sld)


def main(argv: list[str]) -> None:
    if len(argv) == 2 and argv[0] == "--shot":
        SHOTS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(argv[1], SHOTS / "command-center.png")
    output = Path(argv[1]) if len(argv) == 2 and argv[0] == "--output" else DECK
    template = Presentation(str(TEMPLATE))
    bg_dir = ROOT / "data" / "generated" / "template"
    bg_dir.mkdir(parents=True, exist_ok=True)
    content_bg, thanks_bg = bg_dir / "content.png", bg_dir / "thanks.png"
    content_bg.write_bytes(template.slides[2].shapes[0].image.blob)
    thanks_bg.write_bytes(template.slides[5].shapes[0].image.blob)

    backup = DECK.with_name(DECK.stem + ".before-rebuild.pptx")
    if not backup.exists():
        shutil.copyfile(DECK, backup)
    deck = Presentation(str(backup))
    drop_slides_after_first(deck)
    blank = next(layout for layout in deck.slide_layouts if layout.name.upper() == "BLANK")
    for builder, bg in ((slide_problem, content_bg), (slide_architecture, content_bg), (slide_solution, content_bg),
                        (slide_end_to_end, content_bg), (slide_thanks, thanks_bg)):
        slide = deck.slides.add_slide(blank)
        for ph in list(slide.placeholders):
            ph._element.getparent().remove(ph._element)
        background(slide, bg)
        builder(slide)
    deck.save(str(output))
    print(output)


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
