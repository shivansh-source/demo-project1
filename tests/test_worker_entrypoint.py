from typing import Any

import pytest

from app.core.config import get_settings
from app.queue import runtime as runtime_module
from app.queue.runtime import build_runtime, get_runtime
from app.worker import __main__ as entrypoint


def test_build_runtime_wires_the_mock_providers() -> None:
    runtime = build_runtime()
    assert runtime.ctx.enrichment.name == "mock"
    assert runtime.ctx.reasoner is None  # REASONING_ENABLED defaults to false
    assert set(runtime.handlers) == {"enrich_company", "score_lead", "reason_lead", "push_crm"}
    assert set(runtime.final_failure_hooks) == {"reason_lead"}


def test_get_runtime_is_cached() -> None:
    assert get_runtime() is get_runtime()
    runtime_module.set_runtime(None)


def test_worker_fails_at_startup_on_bad_config(settings_env: Any) -> None:
    settings_env(reasoning_enabled="true", anthropic_api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        entrypoint.main()


def test_entrypoint_starts_an_rq_worker_with_the_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeWorker:
        def __init__(self, queues: list[Any], connection: Any) -> None:
            seen["queues"] = [q.name for q in queues]

        def work(self, **kwargs: Any) -> None:
            seen["work"] = kwargs

    monkeypatch.setattr("rq.Worker", FakeWorker)
    entrypoint.main()
    assert seen["queues"] == [get_settings().queue_name]
    assert seen["work"] == {"with_scheduler": True}  # releases retries and deferred jobs
