"""Unit tests for Hermes-style multimodal prepare / route / inject."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagopen.media.classify import classify_file
from tagopen.media.content import build_user_message_content, text_with_addon
from tagopen.media.prepare import PreparedAttachments
from tagopen.media.read_attachment import read_attachment
from tagopen.media.routing import decide_image_mode, model_supports_vision
from tagopen.tasks.worker import _strip_media_parts


def test_classify_image_by_ext():
    k = classify_file(filename="shot.PNG", mimetype="")
    assert k.kind == "image"


def test_classify_pdf_magic():
    k = classify_file(filename="x.bin", mimetype="", magic_prefix=b"%PDF-1.4")
    assert k.kind == "binary"


def test_classify_csv_text():
    k = classify_file(filename="data.csv", mimetype="text/csv")
    assert k.kind == "text"


def test_model_supports_vision_heuristics(monkeypatch):
    from tagopen import config as cfg

    monkeypatch.setattr(cfg.settings, "llm_vision_capability", "auto")
    monkeypatch.setattr(cfg.settings, "llm_vision_models", "")
    assert model_supports_vision("claude-sonnet-4-6") is True
    assert model_supports_vision("openai/kimi-k2.7-code") is False
    monkeypatch.setattr(cfg.settings, "llm_vision_capability", "true")
    assert model_supports_vision("openai/kimi-k2.7-code") is True


def test_decide_image_mode_text(monkeypatch):
    from tagopen import config as cfg

    monkeypatch.setattr(cfg.settings, "image_input_mode", "text")
    assert decide_image_mode(channel_id="C1") == "text"
    monkeypatch.setattr(cfg.settings, "image_input_mode", "native")
    assert decide_image_mode(channel_id="C1") == "native"


def test_build_user_message_native_images():
    prepared = PreparedAttachments(
        text_addon="--- Attached files ---\n[image native] a.png",
        native_images=[
            {
                "path": "/tmp/a.png",
                "mime": "image/png",
                "data_url": "data:image/png;base64,abc",
            }
        ],
    )
    content = build_user_message_content(
        display_name="Tosh", text="what is this?", prepared=prepared
    )
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "what is this?" in content[0]["text"]
    assert content[1]["type"] == "image_url"


def test_text_with_addon():
    p = PreparedAttachments(text_addon="note")
    assert "note" in text_with_addon("hi", p)


def test_read_attachment_rejects_outside_cache(tmp_path, monkeypatch):
    from tagopen import config as cfg

    monkeypatch.setattr(cfg.settings, "data_dir", tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    out = read_attachment(str(outside))
    assert "rejected" in out.lower() or "Path rejected" in out


def test_read_attachment_text(tmp_path, monkeypatch):
    from tagopen import config as cfg

    monkeypatch.setattr(cfg.settings, "data_dir", tmp_path)
    path = tmp_path / "media" / "T" / "C" / "note.txt"
    path.parent.mkdir(parents=True)
    path.write_text("hello attachment")
    assert "hello attachment" in read_attachment(str(path))


def test_strip_media_parts():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
        ],
    }
    out = _strip_media_parts(msg)
    assert isinstance(out["content"], str)
    assert "hi" in out["content"]
    assert "omitted" in out["content"]


@pytest.mark.asyncio
async def test_prepare_slack_files_text_inline(tmp_path, monkeypatch):
    from tagopen import config as cfg
    from tagopen.media import prepare as prep

    monkeypatch.setattr(cfg.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cfg.settings, "image_input_mode", "text")
    monkeypatch.setattr(cfg.settings, "media_inline_text_max_bytes", 10_000)

    async def fake_download(**kwargs):
        dest = Path(kwargs["dest_dir"]) / "f.csv"
        data = b"a,b\n1,2\n"
        dest.write_bytes(data)
        return dest, data

    monkeypatch.setattr(prep, "download_slack_file", fake_download)

    result = await prep.prepare_slack_files(
        files=[
            {
                "id": "F1",
                "name": "f.csv",
                "mimetype": "text/csv",
                "url_private_download": "https://files.slack.com/x",
            }
        ],
        bot_token="xoxb-test",
        workspace_id="T1",
        channel_id="C1",
    )
    assert "1,2" in result.text_addon
    assert result.native_images == []
