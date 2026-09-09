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
