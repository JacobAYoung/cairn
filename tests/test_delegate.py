"""Tests for local-model delegation (:mod:`cairn.delegate`).

The HTTP POST is injected and recording, so we assert the exact URL and payload (model name,
prompt, ``stream: False``) and that it's called exactly once — plus task→model resolution and the
fail-loud behaviors (disabled, no model, unreachable).
"""

from __future__ import annotations

import pytest

from cairn.config import DelegateConfig
from cairn.delegate import DelegateUnreachable, Delegator
from cairn.errors import CairnError


class RecordingPost:
    def __init__(self, response_text: str = "done") -> None:
        self.calls: list[tuple[str, dict]] = []
        self._response = response_text

    def __call__(self, url: str, payload: dict) -> dict:
        self.calls.append((url, payload))
        return {"response": self._response}


def _config(**over) -> DelegateConfig:
    base = dict(
        enabled=True,
        endpoint="http://mac-mini.local:11434",
        default_model="qwen2.5:14b",
        tasks={"summarize": "qwen-sum"},
    )
    base.update(over)
    return DelegateConfig(**base)


def test_ask_posts_expected_payload_once_and_returns_text():
    # Arrange
    post = RecordingPost("a concise summary")
    delegator = Delegator(_config(), post=post)

    # Act
    result = delegator.ask("summarize", "long text here")

    # Assert OUTPUT: model chosen from tasks map, text returned
    assert result.model == "qwen-sum"
    assert result.text == "a concise summary"
    # Assert INTERACTION: one call, exact url + payload
    assert len(post.calls) == 1
    url, payload = post.calls[0]
    assert url == "http://mac-mini.local:11434/api/generate"
    assert payload == {"model": "qwen-sum", "prompt": "long text here", "stream": False}


def test_unmapped_task_falls_back_to_default_model():
    post = RecordingPost()
    Delegator(_config(), post=post).ask("translate", "hola")
    assert post.calls[0][1]["model"] == "qwen2.5:14b"  # default


def test_endpoint_trailing_slash_is_normalized():
    post = RecordingPost()
    Delegator(_config(endpoint="http://host:11434/"), post=post).ask("summarize", "x")
    assert post.calls[0][0] == "http://host:11434/api/generate"


def test_disabled_raises_and_never_calls():
    post = RecordingPost()
    with pytest.raises(CairnError, match="delegation disabled"):
        Delegator(_config(enabled=False), post=post).ask("summarize", "x")
    assert post.calls == []


def test_no_model_and_no_default_raises():
    post = RecordingPost()
    cfg = _config(default_model=None, tasks={})
    with pytest.raises(CairnError, match="no model mapped"):
        Delegator(cfg, post=post).ask("summarize", "x")
    assert post.calls == []


def test_unreachable_endpoint_propagates_as_delegate_unreachable():
    def unreachable(url, payload):
        raise DelegateUnreachable("delegate endpoint unreachable; run this task inline instead")

    with pytest.raises(DelegateUnreachable, match="run this task inline"):
        Delegator(_config(), post=unreachable).ask("summarize", "x")
