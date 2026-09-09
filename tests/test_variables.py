"""app/variables.py: sandboxed Python execution for {{variable}} Script
fields (run_script) and the Python Runner utility tool (run_snippet)."""
import sys

from app.variables import ScriptError, run_script, run_snippet


def test_run_script_returns_the_return_value_as_a_string():
    assert run_script("return 1 + 2") == "3"


def test_run_script_supports_multiple_statements_before_the_return():
    assert run_script("x = 2\ny = 3\nreturn x * y") == "6"


def test_run_script_can_use_the_whitelisted_modules():
    result = run_script("return str(uuid.uuid4())")
    assert len(result) == 36  # a UUID4's string form


def test_run_script_raises_scripterror_on_exception():
    try:
        run_script("raise ValueError('boom')")
        assert False, "expected ScriptError"
    except ScriptError as exc:
        assert "boom" in str(exc)


def test_run_script_blocks_import():
    try:
        run_script("import os\nreturn os.getcwd()")
        assert False, "expected ScriptError"
    except ScriptError as exc:
        assert "__import__" in str(exc)


def test_run_snippet_captures_printed_output():
    result = run_snippet('print("hello")\nprint(1 + 2)')
    assert result == {"stdout": "hello\n3\n", "error": None}


def test_run_snippet_keeps_output_printed_before_a_later_crash():
    result = run_snippet('print("before")\nraise ValueError("boom")')
    assert result["stdout"] == "before\n"
    assert result["error"] == "ValueError: boom"


def test_run_snippet_blocks_import_same_as_run_script():
    result = run_snippet('import os\nprint(os.getcwd())')
    assert result["stdout"] == ""
    assert "__import__" in result["error"]


def test_run_snippet_empty_script_is_a_no_op():
    assert run_snippet("") == {"stdout": "", "error": None}


def test_run_snippet_restores_sys_stdout_even_when_the_script_times_out():
    # Regression test for a real bug: redirect_stdout swaps the process-wide
    # sys.stdout, not something thread-local. A script whose background
    # thread never finishes (never reaches redirect_stdout's own __exit__)
    # would leave sys.stdout permanently hijacked into an orphaned buffer —
    # breaking print() (and this test's own assertions) for the rest of the
    # process, not just this one call, unless the swap is undone explicitly
    # regardless of whether the thread actually finished.
    original_stdout = sys.stdout
    result = run_snippet("while True:\n    pass")
    assert result["error"] == "Script timed out (soft limit: still running in the background)"
    assert sys.stdout is original_stdout

    # And a normal call afterward must still work — stdout wasn't left broken.
    assert run_snippet('print("still alive")') == {"stdout": "still alive\n", "error": None}
