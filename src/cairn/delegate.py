"""Local-model delegation — the engine behind ``cairn ask`` (SPEC Pillar 3).

Claude stays the driver; when a subtask is cheap and mechanical (summarize/classify/draft over
already-loaded data), it shells out to ``cairn ask`` which runs the task on a **local** model
(Ollama) for zero API tokens. The win is cost, not latency — so this is for bulk/mechanical work.

Key behaviors (per SPEC):
- **Fail loud and useful** when the endpoint is unreachable — raise :class:`DelegateUnreachable`
  with "run this task inline instead" so Claude falls back rather than hanging.
- Task → model mapping from ``[delegate].tasks``, falling back to ``[delegate].default``.
- The HTTP POST is injected (``post``) so tests assert the exact URL + payload + call count with
  no live server and no extra test dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cairn.config import DelegateConfig
from cairn.errors import CairnError

DELEGATE_TIMEOUT_SECONDS = 120

# Executes the model call: (url, json_payload) -> parsed JSON response. Injected for tests.
PostFn = Callable[[str, dict], dict]


class DelegateUnreachable(CairnError):
    """The local-model endpoint could not be reached; the caller should run the task inline."""


@dataclass(frozen=True)
class DelegateResult:
    """A completed delegation: which model ran and the text it returned."""

    model: str
    text: str


def _default_post(url: str, payload: dict) -> dict:
    """Real HTTP POST to Ollama, mapping connection failures to a useful CairnError."""
    import httpx

    try:
        response = httpx.post(url, json=payload, timeout=DELEGATE_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        raise DelegateUnreachable(
            f"delegate endpoint unreachable ({url}); run this task inline instead"
        ) from exc
    except httpx.HTTPError as exc:
        raise CairnError(f"delegate request failed: {exc}") from exc


class Delegator:
    """Resolves a task to a model and runs it on the configured local endpoint."""

    def __init__(self, config: DelegateConfig, *, post: PostFn = _default_post) -> None:
        self._cfg = config
        self._post = post

    def ask(self, task: str, prompt: str) -> DelegateResult:
        """Run ``prompt`` on the model mapped to ``task``; raises if delegation is off/unset."""
        if not self._cfg.enabled:
            raise CairnError("delegation disabled — set [delegate].enabled = true in cairn.toml")
        model = self._cfg.tasks.get(task) or self._cfg.default_model
        if not model:
            raise CairnError(
                f"no model mapped for task {task!r} and no [delegate].default set"
            )
        url = self._cfg.endpoint.rstrip("/") + "/api/generate"
        data = self._post(url, {"model": model, "prompt": prompt, "stream": False})
        return DelegateResult(model=model, text=data.get("response", ""))
