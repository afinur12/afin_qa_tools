"""Utility tools: static, client-side pages served under /utility."""


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
        "aes-input", "aes-output", "aes-encrypt", "aes-decrypt", "aes-copy", "aes-unsupported",
    ):
        assert f'id="{element_id}"' in page
    for option in ("AES-CBC", "AES-GCM", "AES-CTR"):
        assert f'value="{option}"' in page


def test_aes_tool_js_asset_is_served(client):
    resp = client.get("/static/js/utility/aes.js")
    assert resp.status_code == 200
    assert "crypto.subtle" in resp.text
