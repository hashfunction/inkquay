"""Original editable sample content for actual Scriblark product captures.
Copyright 2026 Trieflow LLC. MIT. No screenshot generation or image manipulation.
"""
import gzip
import math
import xml.etree.ElementTree as ET

WIDTH, HEIGHT = 841.89, 595.28
INK = "#263e39ff"
GREEN = "#388872ff"
MINT = "#bee8d9ff"
GRAY = "#62736fff"


def make_note():
    doc = ET.Element("xournal", creator="Scriblark original marketing sample", fileversion="4")
    ET.SubElement(doc, "title").text = "A pocket of green — fictional design workshop"
    page = ET.SubElement(doc, "page", width=str(WIDTH), height=str(HEIGHT))
    ET.SubElement(page, "background", type="solid", color="#ffffffff", style="plain")
    layer = ET.SubElement(page, "layer")

    def text(value, x, y, size=13, color=INK, font="Arial"):
        ET.SubElement(layer, "text", font=font, size=str(size), x=str(x), y=str(y), color=color).text = value

    def stroke(points, color=GREEN, width=1.5, tool="pen"):
        ET.SubElement(layer, "stroke", tool=tool, color=color, width=str(width)).text = " ".join(
            f"{v:.2f}" for point in points for v in point)

    def line(x1, y1, x2, y2, color=MINT, width=1):
        stroke([(x1, y1), (x2, y2)], color, width)

    def box(x, y, w, h):
        stroke([(x,y),(x+w,y+1),(x+w-1,y+h),(x+1,y+h-1),(x,y)])

    text("STUDIO NOTES  /  04", 43, 31, 11, GREEN, "Arial Bold")
    text("A pocket of green", 41, 54, 37, INK, "Arial Bold")
    text("Small places. Better pauses. A garden workshop in one page.", 43, 103, 14, GRAY)
    line(43, 134, 800, 134, MINT, 2)
    line(213, 157, 213, 457, MINT, 1)

    text("THE QUESTION", 43, 161, 10, GREEN, "Arial Bold")
    text("How could a quiet\ncorner invite people\nto stop for a moment?", 43, 182, 12.5)
    text("WHAT WE NOTICED", 43, 269, 10, GREEN, "Arial Bold")
    text("A sunny wall.\nA narrow walkway.\nRoom for one bench.", 43, 290, 12.5)
    text("TRY THIS NEXT", 43, 376, 10, GREEN, "Arial Bold")
    text("Sketch small.\nMove things around.\nKeep the path clear.", 43, 397, 12.5)

    text("01  Make room for a pause", 238, 158, 17, INK, "Arial Bold")
    text("A seat in the shade, a few hardy plants, and a clear way through.", 238, 187, 12.5)
    text("02  Sketch the possibilities", 238, 228, 17, INK, "Arial Bold")
    # Original pen strokes, stored as editable vectors in the sample notebook.
    box(280, 315, 166, 25)
    line(296, 341, 294, 386, GREEN, 2)
    line(429, 341, 431, 386, GREEN, 2)
    line(300, 325, 425, 325, GREEN, 1)
    for x, y, scale in [(517, 363, 1), (655, 364, 1.28)]:
        stroke([(x-18*scale,y),(x-13*scale,y+34*scale),(x+13*scale,y+34*scale),(x+18*scale,y),(x-18*scale,y)], GREEN, 1.7)
        stroke([(x,y),(x-2*scale,y-25*scale),(x+1*scale,y-64*scale)], GREEN, 1.6)
        for side, dy in [(-1,-20),(1,-35),(-1,-48)]:
            stroke([(x,y+dy*scale),(x+side*22*scale,y+(dy-14)*scale),(x+side*26*scale,y+(dy-27)*scale),(x+side*8*scale,y+(dy-23)*scale),(x,y+dy*scale)], GREEN, 1.4)
    stroke([(257,408),(316,407),(405,409),(506,407),(588,409),(718,407)], GRAY, 1)
    text("one simple bench", 278, 419, 11, GRAY)
    text("plants at different heights", 516, 419, 11, GRAY)
    text("leave breathing room", 537, 272, 12, GREEN, "Arial Italic")
    stroke([(550,294),(572,305),(583,326),(584,347)], GREEN, 1.2)
    stroke([(578,339),(584,349),(590,341)], GREEN, 1.2)

    line(43, 482, 800, 482, MINT, 2)
    text("KEEP THE IDEA", 43, 502, 10, GREEN, "Arial Bold")
    stroke([(239,523),(767,523)], "#bcebd499", 20, "highlighter")
    text("Start with one welcoming corner. Let the garden grow from there.", 238, 513, 14, INK, "Arial Bold")
    text("Fictional workshop notes • Original editable sample", 43, 560, 9, GRAY)
    text("01 / 01", 760, 559, 10, GREEN)
    return gzip.compress(ET.tostring(doc, encoding="utf-8", xml_declaration=True), mtime=0)


def validate_note(data):
    xml = gzip.decompress(data)
    if len(xml) > 100000:
        raise ValueError("Sample exceeds document bound")
    doc = ET.fromstring(xml)
    pages = doc.findall("page")
    if len(pages) != 1 or (float(pages[0].get("width")),float(pages[0].get("height"))) != (WIDTH,HEIGHT):
        raise ValueError("Sample page geometry differs")
    texts = pages[0].findall("./layer/text")
    if len(texts) != 19 or "A pocket of green" not in [t.text for t in texts]:
        raise ValueError("Sample content missing")
    for item in pages[0].findall("./layer/*"):
        if item.tag == "text":
            points = [(float(item.get("x")),float(item.get("y")))]
        elif item.tag == "stroke":
            values = list(map(float,item.text.split()))
            if len(values) < 4 or len(values) % 2:
                raise ValueError("Invalid editable stroke")
            points = list(zip(values[::2],values[1::2]))
        else:
            raise ValueError("Unexpected sample element")
        if any(not math.isfinite(x) or not math.isfinite(y) or not (0 <= x <= WIDTH and 0 <= y <= HEIGHT) for x,y in points):
            raise ValueError("Sample element outside page")
    return {"pages":1,"text_elements":len(texts),"stroke_elements":len(pages[0].findall("./layer/stroke")),"width":WIDTH,"height":HEIGHT}
