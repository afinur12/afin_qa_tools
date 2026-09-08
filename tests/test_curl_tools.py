"""app/curl_tools.py: parsing a pasted curl command into request fields."""

from app.curl_tools import parse_curl


def test_parse_curl_basic_get():
    result = parse_curl("curl https://example.com/api")
    assert result == {"method": "GET", "url": "https://example.com/api", "headers": [], "body": ""}


def test_parse_curl_reads_method_headers_and_plain_data():
    result = parse_curl(
        "curl -X POST 'https://example.com/api' -H 'Accept: application/json' -d 'raw body'"
    )
    assert result["method"] == "POST"
    assert result["url"] == "https://example.com/api"
    assert result["headers"] == [["Accept", "application/json"]]
    assert result["body"] == "raw body"


def test_parse_curl_multiple_plain_data_flags_accumulate_with_ampersand():
    # Real curl joins repeated -d/--data occurrences with "&" rather than
    # letting the last one win.
    result = parse_curl("curl 'https://example.com/api' -d 'a=1' -d 'b=2'")
    assert result["body"] == "a=1&b=2"


def test_parse_curl_data_urlencode_single_field():
    result = parse_curl("curl 'https://example.com/token' --data-urlencode 'grant_type=client_credentials'")
    assert result["method"] == "POST"
    assert result["body"] == "grant_type=client_credentials"
    assert ["Content-Type", "application/x-www-form-urlencoded"] in result["headers"]


def test_parse_curl_data_urlencode_multiple_fields_join_with_ampersand():
    result = parse_curl(
        "curl 'https://example.com/token' "
        "--data-urlencode 'grant_type=client_credentials' "
        "--data-urlencode 'client_id=abc123' "
        "--data-urlencode 'client_secret=s3cr3t value'"
    )
    assert result["body"] == "grant_type=client_credentials&client_id=abc123&client_secret=s3cr3t+value"


def test_parse_curl_data_urlencode_value_never_becomes_the_url():
    # Regression: --data-urlencode wasn't recognized at all, so its value
    # token fell through to the "else" branch and was mis-parsed as the URL
    # whenever it came before the real URL, or otherwise silently vanished.
    result = parse_curl(
        "curl --data-urlencode 'grant_type=client_credentials' -X POST 'https://example.com/token'"
    )
    assert result["url"] == "https://example.com/token"
    assert result["body"] == "grant_type=client_credentials"


def test_parse_curl_data_urlencode_bare_value_with_no_name():
    result = parse_curl("curl 'https://example.com/api' --data-urlencode 'just a value'")
    assert result["body"] == "just+a+value"


def test_parse_curl_data_urlencode_leading_equals_has_no_name():
    result = parse_curl("curl 'https://example.com/api' --data-urlencode '=hello world'")
    assert result["body"] == "hello+world"


def test_parse_curl_data_urlencode_does_not_override_explicit_content_type():
    result = parse_curl(
        "curl 'https://example.com/api' "
        "-H 'Content-Type: application/x-www-form-urlencoded; charset=utf-8' "
        "--data-urlencode 'a=b'"
    )
    content_types = [v for k, v in result["headers"] if k.lower() == "content-type"]
    assert content_types == ["application/x-www-form-urlencoded; charset=utf-8"]


def test_parse_curl_mixes_plain_data_and_data_urlencode():
    result = parse_curl("curl 'https://example.com/api' -d 'plain=1' --data-urlencode 'enc=a b'")
    assert result["body"] == "plain=1&enc=a+b"
    assert ["Content-Type", "application/x-www-form-urlencoded"] in result["headers"]
