import copy
from pathlib import Path

from docx import Document
from docx.shared import Inches
from docx.table import Table

TEMPLATE_PATH = Path(__file__).parent / "Template_Artifact_V1.docx"

HEADER_FIELD_ORDER = [
    "project", "scenario", "tester", "test_date", "environment",
    "test_priority", "test_type", "channel", "iteration",
    "balance_before", "balance_after", "usage", "final_status",
    "remark", "data_test",
]

SECTION_ORDER = ["PRECONDITION", "MAIN", "POSTCONDITION"]


def _clone_table(table: Table) -> Table:
    new_tbl = copy.deepcopy(table._tbl)
    table._tbl.addnext(new_tbl)
    return Table(new_tbl, table._parent)


def _fill_header(doc: Document, fields: dict) -> None:
    table = doc.tables[0]
    for row_index, field_name in enumerate(HEADER_FIELD_ORDER):
        value_text = str(fields.get(field_name, "") or "")
        row_cells = table.rows[row_index].cells
        try:
            row_cells[3].text = value_text
        except IndexError:
            # This row's template row is genuinely missing its 4th (value) cell
            # in the source .docx (confirmed: row 3 "Test Date" has only 3 cells).
            # Write into the last existing cell in that row so the value is still
            # visible, rather than silently dropping it or corrupting another row.
            row_cells[-1].text = value_text


def _fill_step_block(table: Table, step_no, step_text: str, expected: str, actual: str) -> None:
    table.cell(0, 2).text = str(step_no)
    table.cell(0, 5).text = step_text or ""
    table.cell(1, 2).text = actual or ""
    table.cell(1, 5).text = expected or ""


def _insert_screenshots(table: Table, screenshot_paths: list[str]) -> None:
    cell = table.cell(3, 0)
    for i, path in enumerate(screenshot_paths):
        paragraph = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        paragraph.add_run().add_picture(path, width=Inches(2.5))


def build_docx(testcase, output_path: str) -> str:
    doc = Document(str(TEMPLATE_PATH))

    story = testcase.subtask.phase.story
    fields = {
        "project": story.title,
        "scenario": testcase.subtask.title,
        "tester": testcase.tester,
        "test_date": testcase.test_date,
        "environment": testcase.subtask.phase.type.value,
        "test_priority": testcase.test_priority,
        "test_type": testcase.test_type,
        "channel": testcase.channel,
        "iteration": testcase.iteration,
        "balance_before": testcase.balance_before,
        "balance_after": testcase.balance_after,
        "usage": testcase.usage,
        "final_status": testcase.status.value,
        "remark": testcase.remark,
        "data_test": testcase.data_test,
    }
    _fill_header(doc, fields)

    steps_by_section = {"PRECONDITION": [], "MAIN": [], "POSTCONDITION": []}
    for step in testcase.steps:
        steps_by_section[step.section.value].append(step)

    # Capture all base tables BEFORE any cloning — cloning shifts doc.tables indices.
    section_base_tables = {
        "PRECONDITION": doc.tables[1],
        "MAIN": doc.tables[2],
        "POSTCONDITION": doc.tables[3],
    }

    for section_name in SECTION_ORDER:
        steps = sorted(steps_by_section[section_name], key=lambda s: s.step_no)
        base_table = section_base_tables[section_name]
        if not steps:
            _fill_step_block(base_table, "", "", "", "")
            continue
        current_table = base_table
        for i, step in enumerate(steps):
            if i > 0:
                current_table = _clone_table(current_table)
            _fill_step_block(current_table, step.step_no, step.step_text, step.expected_result, step.actual_result)
            from app.routers.screenshots import UPLOADS_DIR

            _insert_screenshots(current_table, [str(UPLOADS_DIR / s.file_path) for s in step.screenshots])

    doc.save(output_path)
    return output_path
