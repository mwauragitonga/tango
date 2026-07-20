from tagopen.tools.web_search import _format_results


def test_format_results():
    out = _format_results(
        [
            {"title": "AI News", "url": "https://example.com", "snippet": "Latest"},
        ]
    )
    assert "AI News" in out
    assert "https://example.com" in out
    assert "Latest" in out
