"""Hermes-style multimodal attachments: download → cache → typed inject."""

from tagopen.media.prepare import PreparedAttachments, prepare_slack_files
from tagopen.media.content import build_user_message_content

__all__ = [
    "PreparedAttachments",
    "prepare_slack_files",
    "build_user_message_content",
]
