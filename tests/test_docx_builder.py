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
    assert doc.tables[0].cell(0, 3).text == "Payments"
    assert doc.tables[0].cell(1, 3).text == "SIT Login Flow"
    assert doc.tables[0].cell(4, 3).text == "SIT"
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
