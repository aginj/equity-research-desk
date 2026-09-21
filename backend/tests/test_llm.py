import pytest

from app.agents.llm import sse_result_text
from app.config import Settings


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_cursor_is_selected_when_only_cursor_key_is_set():
    from app.agents.llm import LLMClient

    client = LLMClient(_settings(CURSOR_API_KEY="cursor_test_key"))
    assert client.enabled is True
    assert client.provider_name == "cursor"


def test_openai_still_wins_over_cursor_when_both_are_set():
    from app.agents.llm import LLMClient

    client = LLMClient(_settings(OPENAI_API_KEY="sk-test", CURSOR_API_KEY="cursor_test_key"))
    assert client.provider_name == "openai"


def test_sse_result_text_extracts_finished_assistant_reply():
    transcript = """event: status
data: {"runId":"run-1","status":"RUNNING"}

event: assistant
data: {"text":"working"}

event: result
data: {"runId":"run-1","status":"FINISHED","text":"hello"}

event: done
data: {}
"""
    assert sse_result_text(transcript.splitlines()) == "hello"


def test_sse_result_text_raises_on_failed_run():
    transcript = """event: result
data: {"runId":"run-1","status":"ERROR","text":""}

"""
    with pytest.raises(RuntimeError, match="ERROR"):
        sse_result_text(transcript.splitlines())
