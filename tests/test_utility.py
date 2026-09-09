"""Utility tools: static, client-side pages served under /utility — except
Python Runner, which has a real POST endpoint (see test_variables.py for
the sandboxed-execution logic it calls into)."""


def test_aes_tool_listed_on_the_utility_index(client):
    page = client.get("/utility").text
    assert 'href="/utility/aes"' in page
    assert "AES Encrypt/Decrypt" in page


def test_aes_tool_page_renders_expected_controls(client):
    resp = client.get("/utility/aes")
    assert resp.status_code == 200
    page = resp.text
    assert "<title>AES Encrypt/Decrypt - QA Toolbox</title>" in page
    for element_id in (
        "aes-mode", "aes-key-format", "aes-output-format", "aes-key", "aes-iv",
        "aes-iv-field", "aes-iv-hint", "aes-ecb-hint",
        "aes-input", "aes-output", "aes-encrypt", "aes-decrypt", "aes-copy", "aes-unsupported",
    ):
        assert f'id="{element_id}"' in page
    for option in ("AES-CBC", "AES-GCM", "AES-CTR", "AES-ECB"):
        assert f'value="{option}"' in page
    assert 'value="passphrase-sha256"' in page
    assert 'value="passphrase-md5"' in page
    assert 'src="/static/js/vendor/crypto-js/crypto-js.min.js' in page
    # Local-only key-format extension: 404s harmlessly if the (gitignored)
    # file isn't present on this machine, so the page always references it.
    assert 'src="/static/js/utility/aes.local.js' in page


def test_aes_tool_js_asset_is_served(client):
    resp = client.get("/static/js/utility/aes.js")
    assert resp.status_code == 200
    assert "crypto.subtle" in resp.text
    assert "CryptoJS" in resp.text
    assert "passphrase-sha256" in resp.text
    assert "passphrase-md5" in resp.text
    assert "AesTool" in resp.text
    assert "registerKeyFormat" in resp.text


def test_aes_vendor_crypto_js_asset_is_served(client):
    resp = client.get("/static/js/vendor/crypto-js/crypto-js.min.js")
    assert resp.status_code == 200
    assert "CryptoJS" in resp.text


def test_aes_local_extension_example_documents_the_hook(client):
    with open("app/static/js/utility/aes.local.js.example", encoding="utf-8") as f:
        text = f.read()
    assert "AesTool.registerKeyFormat" in text


def test_python_runner_listed_on_the_utility_index(client):
    page = client.get("/utility").text
    assert 'href="/utility/python-runner"' in page
    assert "Python Runner" in page


def test_python_runner_page_renders_the_highlighted_editor(client):
    resp = client.get("/utility/python-runner")
    assert resp.status_code == 200
    page = resp.text
    assert "<title>Python Runner - QA Toolbox</title>" in page
    # Same editor markup/attributes as a variable's Script field, so the
    # existing unconditional api_client.js wiring picks it up for free.
    assert "data-ac-script-editor" in page
    assert "ac-code-editor" in page
    for element_id in ("py-input", "py-run", "py-output", "py-error", "py-copy-output"):
        assert f'id="{element_id}"' in page
    assert 'src="/static/js/api_client.js' in page
    assert 'src="/static/js/utility/python_runner.js' in page
    # Script/Output panels are equal-height on this page (unlike every
    # other tool's independent-height .tool-split), since a mismatch here
    # reads as visually broken rather than expected — see .is-balanced.
    assert 'class="tool-split is-balanced"' in page


def test_python_runner_run_endpoint_executes_and_captures_stdout(client):
    resp = client.post("/utility/python-runner/run", json={"code": "print(1 + 2)"})
    assert resp.status_code == 200
    assert resp.json() == {"stdout": "3\n", "error": None}


def test_python_runner_run_endpoint_reports_errors_without_a_500(client):
    resp = client.post("/utility/python-runner/run", json={"code": "raise ValueError('boom')"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "ValueError: boom"


def test_python_runner_js_asset_is_served(client):
    resp = client.get("/static/js/utility/python_runner.js")
    assert resp.status_code == 200
    assert "/utility/python-runner/run" in resp.text
