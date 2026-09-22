"""Thin LLM adapter. Structured JSON only. Never lets the model invent a schema."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_CURSOR_API = "https://api.cursor.com"
_CURSOR_RUN_FAILED = frozenset({"ERROR", "CANCELLED", "EXPIRED"})

SYSTEM_GUARDRAILS = """You are a senior equity research associate at a buy-side desk.
Rules you must follow:
- Use ONLY the evidence provided. If evidence is thin, say so and lower conviction.
- Never invent prices, filings, dates, or quotes.
- Cite source ids that appear in the evidence when you mention a fact.
- This is research, not a solicitation to buy or sell securities.
- Prefer precise, institutional language over hype.
- If bull and bear cases are balanced, do not force a strong rating.
"""


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._openai_clients: dict[tuple[str, str | None], object] = {}
        self.calls = 0
        self.tokens = 0

    def reset_usage(self) -> None:
        self.calls = 0
        self.tokens = 0

    @property
    def enabled(self) -> bool:
        return self.settings.has_llm

    @property
    def provider_name(self) -> str:
        gateway_key = self.settings.llm_api_key or self.settings.openai_api_key
        if self.settings.llm_base_url and gateway_key:
            return "openai-compatible"
        if self.settings.openai_api_key:
            return "openai"
        if self.settings.anthropic_api_key:
            return "anthropic"
        if self.settings.cursor_api_key:
            return "cursor"
        return "heuristic"

    async def complete_json(
        self,
        user: str,
        schema: type[T],
        *,
        system: str = SYSTEM_GUARDRAILS,
    ) -> T | None:
        if not self.enabled:
            return None
        cap = self.settings.llm_max_calls_per_run
        if cap and self.calls >= cap:
            logger.info("LLM call cap reached for this run (%s)", cap)
            return None
        try:
            raw = await self._complete(system, user, schema)
            self.calls += 1
            if not raw:
                return None
            payload = _extract_json(raw)
            return schema.model_validate(payload)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("LLM JSON validation failed: %s", exc)
            return None
        except Exception:
            logger.exception("LLM call failed")
            return None

    async def _complete(self, system: str, user: str, schema: type[BaseModel]) -> str:
        schema_hint = json.dumps(schema.model_json_schema(), indent=2)
        prompt = (
            f"{user}\n\nReturn ONLY valid JSON matching this schema:\n{schema_hint}\n"
            "No markdown. No commentary."
        )

        if self.settings.llm_base_url:
            return await self._openai(
                system,
                prompt,
                api_key=self.settings.llm_api_key or self.settings.openai_api_key or "",
                model=self.settings.llm_model or self.settings.openai_model,
                base_url=self.settings.llm_base_url,
            )
        if self.settings.openai_api_key:
            return await self._openai(
                system,
                prompt,
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model,
                base_url=None,
            )
        if self.settings.anthropic_api_key:
            return await self._anthropic(system, prompt)
        if self.settings.cursor_api_key:
            return await self._cursor(system, prompt)
        return ""

    async def _openai(
        self,
        system: str,
        user: str,
        *,
        api_key: str,
        model: str,
        base_url: str | None,
        json_object: bool = True,
    ) -> str:
        from openai import AsyncOpenAI

        cache_key = (api_key, base_url)
        client = self._openai_clients.get(cache_key)
        if client is None:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=2,
            )
            self._openai_clients[cache_key] = client
        assert isinstance(client, AsyncOpenAI)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if json_object:
            response = await client.chat.completions.create(
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=messages,
            )
        else:
            response = await client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=messages,
            )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return response.choices[0].message.content or ""

    async def _anthropic(self, system: str, user: str) -> str:
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.settings.anthropic_model,
                    "max_tokens": 2500,
                    "temperature": 0.2,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            self.tokens += int(usage.get("input_tokens") or 0) + int(
                usage.get("output_tokens") or 0
            )
            parts = data.get("content") or []
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

    async def _cursor(self, system: str, user: str) -> str:
        if self.settings.cursor_base_url:
            return await self._openai(
                system,
                user,
                api_key=self.settings.cursor_api_key or "",
                model=self.settings.cursor_model,
                base_url=self.settings.cursor_base_url,
                json_object=False,
            )
        return await self._cursor_cloud(system, user)

    async def _cursor_cloud(self, system: str, user: str) -> str:
        """No-repo Cloud Agent run. Cursor has no public chat-completions API."""
        api_key = self.settings.cursor_api_key or ""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        prompt = (
            f"{system}\n\n{user}\n\n"
            "You have no workspace and must not use tools, browse, or edit files. "
            "Reply with the JSON object only."
        )
        timeout = httpx.Timeout(
            self.settings.llm_timeout_seconds,
            connect=15.0,
        )
        agent_id: str | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            created = await client.post(
                f"{_CURSOR_API}/v1/agents",
                headers=headers,
                json={
                    "name": "Equity Research Desk synthesis",
                    "prompt": {"text": prompt},
                    "model": {"id": self.settings.cursor_model},
                },
            )
            created.raise_for_status()
            body = created.json()
            agent = body.get("agent") or {}
            run = body.get("run") or {}
            agent_id = agent.get("id")
            run_id = run.get("id") or agent.get("latestRunId")
            if not agent_id or not run_id:
                raise RuntimeError("Cursor create-agent response missing agent or run id")
            try:
                return await self._cursor_wait_for_run(client, headers, agent_id, run_id)
            finally:
                try:
                    await client.delete(
                        f"{_CURSOR_API}/v1/agents/{agent_id}",
                        headers=headers,
                    )
                except httpx.HTTPError:
                    logger.warning("Failed to delete Cursor cloud agent %s", agent_id)

    async def _cursor_wait_for_run(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        agent_id: str,
        run_id: str,
    ) -> str:
        stream_url = f"{_CURSOR_API}/v1/agents/{agent_id}/runs/{run_id}/stream"
        try:
            async with client.stream(
                "GET",
                stream_url,
                headers={**headers, "Accept": "text/event-stream"},
            ) as response:
                if response.status_code == 200:
                    return await _sse_result_from_response(response)
                if response.status_code not in {404, 410}:
                    response.raise_for_status()
        except httpx.HTTPError:
            logger.info("Cursor run stream unavailable; polling Get A Run instead")

        run_url = f"{_CURSOR_API}/v1/agents/{agent_id}/runs/{run_id}"
        poll_interval = min(2.0, max(0.5, self.settings.llm_timeout_seconds / 30))
        deadline = asyncio.get_running_loop().time() + self.settings.llm_timeout_seconds
        while True:
            polled = await client.get(run_url, headers=headers)
            polled.raise_for_status()
            payload = polled.json()
            status = str(payload.get("status") or "")
            if status == "FINISHED":
                return str(payload.get("result") or "")
            if status in _CURSOR_RUN_FAILED:
                raise RuntimeError(f"Cursor run ended with status {status}")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Cursor run {run_id} did not finish in time")
            await asyncio.sleep(poll_interval)


async def _sse_result_from_response(response: httpx.Response) -> str:
    lines: list[str] = []
    async for line in response.aiter_lines():
        lines.append(line)
    return sse_result_text(lines)


def sse_result_text(lines: Iterable[str]) -> str:
    """Parse a Cursor run SSE transcript and return the terminal assistant text."""
    event = "message"
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if event in {"result", "error"}:
                return _sse_block_text(event, data)
            event = "message"
            data = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    return _sse_block_text(event, data)


def _sse_block_text(event: str, data: list[str]) -> str:
    if event == "result":
        payload = json.loads("\n".join(data) or "{}")
        status = str(payload.get("status") or "")
        if status in _CURSOR_RUN_FAILED:
            raise RuntimeError(f"Cursor run ended with status {status}")
        return str(payload.get("text") or "")
    if event == "error":
        payload = json.loads("\n".join(data) or "{}")
        raise RuntimeError(str(payload.get("message") or "Cursor stream error"))
    raise ValueError("Cursor stream ended without a result")


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start : end + 1])
