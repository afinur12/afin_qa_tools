from docx import Document

from app.docx.builder import build_docx


class _Step:
    def __init__(self, step_no, section, text, expected, actual, screenshots=None):
        self.step_no = step_no
        self.section = section
        self.step_text = text
        self.expected_result = expected
        self.actual_result = actual
        self.screenshots = screenshots or []


class _Screenshot:
    def __init__(self, file_path):
        self.file_path = file_path


class _Enum:
    def __init__(self, value):
        self.value = value


class _Phase:
    def __init__(self, story, type_value):
        self.story = story
        self.type = _Enum(type_value)


class _Subtask:
    def __init__(self, story, title, phase_type):
        self.title = title
        self.phase = _Phase(story, phase_type)


class _Story:
    def __init__(self, title):
        self.title = title


class _TestCase:
    def __init__(self, subtask, steps):
        self.subtask = subtask
        self.steps = steps
        self.tester = "Andri Firman Nurvianto"
        self.test_date = "2026-08-26"
        self.test_priority = "High"
        self.test_type = "Functional"
        self.channel = "Mobile App"
        self.iteration = "1"
        self.balance_before = "Rp. -"
        self.balance_after = "Rp. -"
        self.usage = "Rp. -"
        self.remark = ""
        self.data_test = "msisdn: 62812"
        self.status = _Enum("PASS")


def _make_testcase(steps):
    from app.models import StepSection

    story = _Story("Payments")
    subtask = _Subtask(story, "SIT Login Flow", "SIT")
    return _TestCase(subtask, steps), StepSection


def test_build_docx_header_and_single_step(tmp_path):
    tc, StepSection = _make_testcase([])
    tc.steps = [
        _Step(1, StepSection.PRECONDITION, "pre text", "pre expected", "pre actual"),
        _Step(1, StepSection.MAIN, "main text", "main expected", "main actual"),
        _Step(1, StepSection.POSTCONDITION, "post text", "post expected", "post actual"),
    ]
    output_path = str(tmp_path / "out.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    # Use ground-truth row-scoped access (immune to flat-index bugs) for key header fields
    header_table = doc.tables[0]
    assert header_table.rows[0].cells[3].text == "Payments"  # project (row 0)
    assert header_table.rows[1].cells[3].text == "SIT Login Flow"  # scenario (row 1)
    assert header_table.rows[4].cells[3].text == "SIT"  # environment (row 4, affected by flat-index bug if using .cell())
    assert header_table.rows[8].cells[3].text == "1"  # iteration (row 8, affected by flat-index bug)
    assert header_table.rows[13].cells[3].text == ""  # remark (row 13, affected by flat-index bug)
    assert header_table.rows[14].cells[-1].text == "msisdn: 62812"  # data_test (row 14, uses fallback to last cell)

    # Step blocks
    assert doc.tables[1].cell(0, 5).text == "pre text"
    assert doc.tables[2].cell(1, 2).text == "main actual"
    assert doc.tables[3].cell(1, 5).text == "post expected"


def test_build_docx_clones_tables_for_multiple_steps(tmp_path):
    tc, StepSection = _make_testcase([])
    tc.steps = [
        _Step(1, StepSection.MAIN, "step one", "e1", "a1"),
        _Step(2, StepSection.MAIN, "step two", "e2", "a2"),
        _Step(3, StepSection.MAIN, "step three", "e3", "a3"),
    ]
    output_path = str(tmp_path / "out2.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    assert len(doc.tables) == 6  # header + 3 MAIN blocks + empty PRE + empty POST
    main_texts = [t.cell(0, 5).text for t in doc.tables if len(t.rows) == 4 and t.cell(0, 5).text.startswith("step")]
    assert main_texts == ["step one", "step two", "step three"]


def test_build_docx_inserts_screenshots(tmp_path):
    import base64

    png_path = tmp_path / "shot.png"
    png_path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    tc, StepSection = _make_testcase([])
    tc.steps = [_Step(1, StepSection.MAIN, "step", "e", "a", screenshots=[_Screenshot(str(png_path))])]
    output_path = str(tmp_path / "out3.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    assert len(doc.inline_shapes) == 1


def test_build_docx_screenshots_do_not_accumulate_across_cloned_step_tables(tmp_path):
    """Regression test for cloned step-block image accumulation.

    3 MAIN steps; screenshots on steps 1 and 2 only (step 3 has none). Each
    step's cloned table must contain exactly its own screenshots -- not the
    screenshots of steps that came before it. A bug where clones are made
    from an already-filled table (instead of a pristine snapshot) causes
    images to bleed forward into later steps' tables.
    """
    import base64

    png_path = tmp_path / "shot.png"
    png_path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    tc, StepSection = _make_testcase([])
    tc.steps = [
        _Step(1, StepSection.MAIN, "step one", "e1", "a1", screenshots=[_Screenshot(str(png_path))]),
        _Step(2, StepSection.MAIN, "step two", "e2", "a2", screenshots=[_Screenshot(str(png_path))]),
        _Step(3, StepSection.MAIN, "step three", "e3", "a3"),
    ]
    output_path = str(tmp_path / "out_accum.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    # Isolate the 3 MAIN step-block tables in document order (4-row step
    # blocks whose step-text cell starts with "step").
    step_tables = [
        t for t in doc.tables
        if len(t.rows) == 4 and t.cell(0, 5).text.startswith("step")
    ]
    assert [t.cell(0, 5).text for t in step_tables] == ["step one", "step two", "step three"]

    def _drawing_count(table):
        # Count w:drawing elements within just this table's own XML subtree,
        # so images are attributed to the correct table rather than counted
        # globally (a global doc.inline_shapes count would not distinguish
        # which step a bled-forward image landed in).
        return len(table._tbl.xpath(".//*[local-name()='drawing']"))

    counts = [_drawing_count(t) for t in step_tables]
    assert counts == [1, 1, 0]


def test_build_docx_preserves_data_test_field_despite_cell_index_anomaly(tmp_path):
    """Regression test: data_test field must be written even when row 14 col 3 is inaccessible.

    The template has a structural anomaly: row 14 column 3 raises IndexError when accessed via
    table.cell(), requiring a fallback to column 2. This test verifies the value is not silently
    dropped but actually written to the document.
    """
    tc, StepSection = _make_testcase([])
    tc.steps = [_Step(1, StepSection.MAIN, "step", "e", "a")]
    tc.data_test = "msisdn: 62812"
    output_path = str(tmp_path / "out_data_test.docx")
    build_docx(tc, output_path)

    doc = Document(output_path)
    # Verify the data_test value appears somewhere in the header table (exact column not guaranteed)
    header_table = doc.tables[0]
    header_text_found = False
    for row in header_table.rows:
        for cell in row.cells:
            if "msisdn: 62812" in cell.text.lower():
                header_text_found = True
                break
        if header_text_found:
            break
    assert header_text_found, "data_test field value 'msisdn: 62812' not found in header table"


def test_build_docx_handles_unembeddable_screenshot_without_crashing(tmp_path):
    """Regression test: a screenshot file add_picture can't embed must not abort the export.

    Screenshot format is deliberately never validated at upload time, so a referenced
    "screenshot" can be anything -- e.g. a non-image file, or an image format python-docx
    can't embed (such as WebP). build_docx must complete successfully and leave a
    traceable placeholder in that step's table instead of raising.
    """
    bad_path = tmp_path / "not_an_image.webp"
    bad_path.write_bytes(b"not actually an image")

    tc, StepSection = _make_testcase([])
    tc.steps = [_Step(1, StepSection.MAIN, "step", "e", "a", screenshots=[_Screenshot(str(bad_path))])]
    output_path = str(tmp_path / "out_bad_screenshot.docx")

    # Must not raise.
    build_docx(tc, output_path)

    doc = Document(output_path)
    step_table = next(t for t in doc.tables if len(t.rows) == 4 and t.cell(0, 5).text == "step")
    assert "not_an_image.webp" in step_table.cell(3, 0).text
    assert len(step_table._tbl.xpath(".//*[local-name()='drawing']")) == 0
