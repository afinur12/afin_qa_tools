import copy
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models import StepSection
from app.templating import tracker_url

TEMPLATE_PATH = Path(__file__).parent / "Template_Artifact_V1.docx"

HEADER_FIELD_ORDER = [
    "project", "scenario", "tester", "test_date", "environment",
    "test_priority", "test_type", "channel", "iteration",
    "balance_before", "balance_after", "usage", "final_status",
    "remark", "data_test",
]

SECTION_ORDER = ["PRECONDITION", "MAIN", "POSTCONDITION"]

# Heading text the template carries for each section kind. Used both to find
# the stencil headings and to label the clones.
SECTION_HEADINGS = {
    StepSection.PRECONDITION: "PRE CONDITION",
    StepSection.MAIN: "MAIN TEST",
    StepSection.POSTCONDITION: "POST CONDITION",
}

# Same headings, hyphenated for use inside filenames.
SECTION_FILE_LABELS = {kind: heading.replace(" ", "-") for kind, heading in SECTION_HEADINGS.items()}

# Fields rendered as a bulleted list rather than a single run of text.
BULLET_FIELDS = {"data_test"}

# Fields written as "<code> - <title>" where the code links to the tracker.
LINKED_FIELDS = {"project", "scenario"}

# Screenshots are sized to the template's usable content width (A4 minus the
# 1.27cm margins is 18.46cm, and the step tables are 18.44cm wide), so 18cm
# fills the block without overflowing the page or the cell.
SCREENSHOT_WIDTH = Cm(18)

# numId 1 in the template's numbering.xml is a real Word bullet list
# (abstractNumId 0, numFmt "bullet"). Reusing it gives native bullets that
# behave correctly in Word rather than a literal "-" typed into the text.
BULLET_NUM_ID = 1


def _unwrap_content_controls(doc: Document) -> None:
    """Replace every ``<w:sdt>`` with the contents it wraps.

    The source template ships with Word content controls: a date picker on
    the Test Date row and dropdowns on Environment / Priority / Type /
    Channel / Final Status. Two problems follow from leaving them in place:

    1. The Test Date control wraps the table CELL itself (``sdt`` -> ``tc``),
       so python-docx's ``row.cells`` only sees the three plain ``<w:tc>``
       siblings and never the real value cell hidden inside the control.
       Writing the date into the last visible cell then left the control's
       own stale placeholder ("Tuesday, 11 August 2026") sitting in the row
       as well, so the exported document showed the date twice.
    2. They render in Word as interactive form controls, which is not what an
       exported artifact should contain.

    Unwrapping first makes every header row a uniform four-cell row and
    leaves plain text behind, which fixes both.
    """
    body = doc.element.body
    # Controls can nest, so keep unwrapping until none are left.
    while True:
        sdts = body.findall(".//" + qn("w:sdt"))
        if not sdts:
            return
        for sdt in sdts:
            parent = sdt.getparent()
            if parent is None:
                continue
            content = sdt.find(qn("w:sdtContent"))
            index = list(parent).index(sdt)
            if content is not None:
                for child in reversed(list(content)):
                    parent.insert(index, child)
            parent.remove(sdt)


def _clone_table(pristine_tbl_xml, after_element, parent):
    """Clone a pristine (never filled/inserted-into) table XML snapshot and
    insert it immediately after ``after_element``.

    Callers must always pass a deepcopy of an UNTOUCHED template table as
    `pristine_tbl_xml` — never the XML of a table that has already gone
    through `_fill_step_block`/`_insert_screenshots` — otherwise content
    (in particular, appended screenshot image runs) accumulates across
    clones instead of each clone starting empty.

    ``after_element`` is the element the clone follows, which is the spacer
    paragraph trailing the previous step rather than that step's table, so
    the blocks stay separated in document order.
    """
    new_tbl = copy.deepcopy(pristine_tbl_xml)
    after_element.addnext(new_tbl)
    return Table(new_tbl, parent), new_tbl


def _append_spacer(after_element):
    """Put an empty paragraph after ``after_element`` and return it.

    Word merges tables that sit directly against each other into a single
    table, which ran consecutive step blocks together. A paragraph between
    them keeps each step its own table.
    """
    spacer = OxmlElement("w:p")
    after_element.addnext(spacer)
    return spacer


def _prevent_row_splits(table: Table) -> None:
    """Mark every row as non-splitting.

    A row that no longer fits on the current page then moves to the next page
    whole instead of being sliced across the break — which is what keeps an
    18cm screenshot and its labels together.
    """
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))


def _paragraph_text(element) -> str:
    return "".join(node.text or "" for node in element.iter(qn("w:t"))).strip()


def _set_paragraph_text(element, text: str) -> None:
    """Overwrite a paragraph's text, keeping its first run's formatting."""
    runs = element.findall(qn("w:r"))
    for run in runs[1:]:
        element.remove(run)
    if not runs:
        return
    first = runs[0]
    for node in first.findall(qn("w:t")):
        first.remove(node)
    text_node = OxmlElement("w:t")
    text_node.text = text
    text_node.set(qn("xml:space"), "preserve")
    first.append(text_node)


def _rebuild_sections(doc: Document, sections) -> None:
    """Lay out the document's section blocks from the test case's own list.

    The template ships one heading + step table per kind, in a fixed
    PRE/MAIN/POST order. A test case now carries an ordered list of sections
    where a kind may repeat, so the template's blocks are used as stencils:
    everything from the first heading through the last step table is removed
    and rebuilt, cloning a heading and a step table per section.

    Word numbers the Heading1 style automatically, so cloned headings letter
    themselves (A, B, C, D...) however many there are.
    """
    body = doc.element.body
    children = list(body)

    heading_stencils = {}
    first_index = None
    last_index = None
    step_table_stencil = None

    for index, element in enumerate(children):
        if element.tag == qn("w:p"):
            text = _paragraph_text(element)
            for kind, heading_text in SECTION_HEADINGS.items():
                if text == heading_text:
                    heading_stencils[kind] = copy.deepcopy(element)
                    first_index = index if first_index is None else first_index
        elif element.tag == qn("w:tbl") and first_index is not None:
            # Tables after the first heading are the step-block stencils; the
            # header table sits above it and must not be touched.
            if step_table_stencil is None:
                step_table_stencil = copy.deepcopy(element)
            last_index = index

    if first_index is None or last_index is None or step_table_stencil is None:
        raise RuntimeError("template is missing its section headings or step tables")

    parent = doc.tables[-1]._parent
    for element in children[first_index : last_index + 1]:
        body.remove(element)

    position = first_index

    def insert(element):
        nonlocal position
        body.insert(position, element)
        position += 1
        return element

    for section_index, section in enumerate(sections):
        heading = copy.deepcopy(heading_stencils[section.kind])
        _set_paragraph_text(heading, SECTION_HEADINGS[section.kind])
        insert(heading)
        if section_index > 0:
            # Each Heading 1 after the first starts on its own page — the
            # first section already starts fresh right below the header
            # table, so it gets no break of its own.
            Paragraph(heading, parent).paragraph_format.page_break_before = True
        insert(OxmlElement("w:p"))

        steps = list(section.steps)
        if not steps:
            table_element = insert(copy.deepcopy(step_table_stencil))
            _fill_step_block(Table(table_element, parent), "", "", "", "")
            insert(OxmlElement("w:p"))
            continue

        for step in steps:
            table_element = insert(copy.deepcopy(step_table_stencil))
            table = Table(table_element, parent)
            _fill_step_block(table, step.step_no, step.step_text, step.expected_result, step.actual_result)

            from app.routers.screenshots import UPLOADS_DIR

            _insert_screenshots(table, [str(UPLOADS_DIR / shot.file_path) for shot in step.screenshots])
            _prevent_row_splits(table)
            insert(OxmlElement("w:p"))


def _format_test_date(value: str) -> str:
    """Render the stored ISO date as "Wednesday, 26 August 2026".

    The web form submits YYYY-MM-DD from a native date picker. Anything that
    doesn't parse (legacy free-text entries) is passed through untouched
    rather than dropped.
    """
    text = (value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return text
    # %-d / %#d are platform-specific, so strip the leading zero by hand.
    return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"


def _apply_bullet(paragraph) -> None:
    """Attach the template's native bullet numbering to a paragraph."""
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id = OxmlElement("w:numId")
    num_id.set(qn("w:val"), str(BULLET_NUM_ID))
    num_pr.append(ilvl)
    num_pr.append(num_id)
    p_pr.append(num_pr)


def _add_hyperlink(paragraph, text: str, url: str) -> None:
    """Append a real Word hyperlink run to a paragraph.

    python-docx has no API for this, so the relationship and the
    ``<w:hyperlink>`` wrapper are built by hand.
    """
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    run_pr = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_pr.append(colour)
    run_pr.append(underline)
    run.append(run_pr)

    text_node = OxmlElement("w:t")
    text_node.text = text
    text_node.set(qn("xml:space"), "preserve")
    run.append(text_node)

    link.append(run)
    paragraph._p.append(link)


def _write_linked_cell(cell, code: str, title: str, url: str) -> None:
    """Write "<code> - <title>" with the code as a clickable link."""
    cell.text = ""
    paragraph = cell.paragraphs[0]
    if not code:
        paragraph.add_run(title or "")
        return
    _add_hyperlink(paragraph, code, url)
    if title:
        paragraph.add_run(f" - {title}")


def _write_cell(cell, text: str, bullet: bool = False) -> None:
    """Replace a cell's contents with ``text``.

    With ``bullet`` set, each non-empty line becomes its own bulleted
    paragraph; otherwise the text is written as-is (newlines preserved as
    line breaks within one paragraph).
    """
    if not bullet:
        cell.text = text
        return

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cell.text = ""
    if not lines:
        return
    for i, line in enumerate(lines):
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.text = line
        try:
            paragraph.style = "List Paragraph"
        except KeyError:
            pass
        _apply_bullet(paragraph)


# Depends on `table.rows[row_index].cells` being ROW-SCOPED (each row's own
# cell list), not the flat/deprecated `Table.cell()`/`Table.row_cells`
# accessor which indexes across merged-cell spans and can silently return a
# cell from the wrong row. This is documented behavior in python-docx 1.1.x
# (see requirements.txt pin) but was NOT reliably true in older releases,
# where using it here would reintroduce cross-row header data corruption.
def _fill_header(doc: Document, fields: dict) -> None:
    table = doc.tables[0]
    for row_index, field_name in enumerate(HEADER_FIELD_ORDER):
        row_cells = table.rows[row_index].cells
        # Every header row has its own value cell at index 3 once the
        # template's content controls have been unwrapped.
        target = row_cells[3] if len(row_cells) > 3 else row_cells[-1]

        value = fields.get(field_name, "")
        if field_name in LINKED_FIELDS and isinstance(value, dict):
            _write_linked_cell(target, value.get("code", ""), value.get("title", ""), value.get("url", ""))
            continue
        _write_cell(target, str(value or ""), bullet=field_name in BULLET_FIELDS)


def _fill_step_block(table: Table, step_no, step_text: str, expected: str, actual: str) -> None:
    table.cell(0, 2).text = str(step_no)
    table.cell(0, 5).text = step_text or ""
    table.cell(1, 2).text = actual or ""
    table.cell(1, 5).text = expected or ""


def _insert_screenshots(table: Table, screenshot_paths: list[str]) -> None:
    cell = table.cell(3, 0)
    for i, path in enumerate(screenshot_paths):
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            paragraph.add_run().add_picture(path, width=SCREENSHOT_WIDTH)
        except Exception:
            # Screenshot format/content is deliberately never validated at
            # upload time, so add_picture can fail here (e.g. WebP, a
            # missing file, or a corrupted image). Don't let one bad
            # screenshot abort the whole export — fall back to a text
            # placeholder naming the file so it's traceable, and keep going.
            paragraph.add_run(f"[screenshot could not be embedded: {Path(path).name}]")


def build_docx(testcase, output_path: str) -> str:
    doc = Document(str(TEMPLATE_PATH))
    _unwrap_content_controls(doc)

    story = testcase.subtask.phase.story
    fields = {
        # Project identifies the task (story); Scenario identifies the test
        # case itself. Each renders as "<code> - <title>" with the code
        # linking back to the ticket in the tracker.
        "project": {
            "code": story.display_code, "title": story.title,
            "url": tracker_url(story.display_code),
        },
        "scenario": {
            "code": testcase.display_code, "title": testcase.title,
            "url": tracker_url(testcase.display_code),
        },
        "tester": testcase.tester,
        "test_date": _format_test_date(testcase.test_date),
        "environment": testcase.subtask.phase.type.value,
        "test_priority": testcase.test_priority,
        "test_type": testcase.test_type_ref.name if testcase.test_type_ref else testcase.test_type,
        "channel": testcase.channel,
        "iteration": testcase.iteration,
        "balance_before": testcase.balance_before,
        "balance_after": testcase.balance_after,
        "usage": testcase.usage,
        "final_status": testcase.status.label,
        "remark": testcase.remark,
        "data_test": testcase.data_test,
    }
    _fill_header(doc, fields)

    _rebuild_sections(doc, testcase.sections)

    doc.save(output_path)
    return output_path
