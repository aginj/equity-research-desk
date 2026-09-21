from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.llm import LLMClient
from app.agents.scoring import extract_events, filing_bias, news_bias
from app.domain import EventExtract, TickerIntel


class _NewsPack(BaseModel):
    news_bias: float = Field(ge=-1, le=1)
    narrative: str
    events: list[EventExtract] = Field(default_factory=list)


class NewsAnalyst:
    name = "news_analyst"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, intel: TickerIntel) -> TickerIntel:
        heuristic_events = extract_events(intel)
        bias = news_bias(intel.news)
        if not self.llm.enabled or not intel.news:
            return intel.model_copy(
                update={
                    "events": heuristic_events,
                    "news_bias": bias,
                    "narrative": _fallback_narrative(intel, bias),
                }
            )

        evidence = [
            {
                "id": n.id,
                "headline": n.headline,
                "summary": n.summary,
                "publisher": n.publisher,
                "published_at": n.published_at.isoformat(),
            }
            for n in intel.news[:8]
        ]
        prompt = (
            f"Ticker {intel.ticker} ({intel.profile.name}, {intel.profile.sector}).\n"
            f"Recent news evidence:\n{evidence}\n"
            "Extract the 3-6 most material events. news_bias is average sentiment from -1 to 1. "
            "narrative is 2 sentences for a PM. Use only this evidence."
        )
        pack = await self.llm.complete_json(prompt, _NewsPack)
        if pack is None:
            return intel.model_copy(
                update={
                    "events": heuristic_events,
                    "news_bias": bias,
                    "narrative": _fallback_narrative(intel, bias),
                }
            )
        return intel.model_copy(
            update={
                "events": pack.events or heuristic_events,
                "news_bias": pack.news_bias,
                "narrative": pack.narrative,
            }
        )


class FilingsAnalyst:
    name = "filings_analyst"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(self, intel: TickerIntel) -> TickerIntel:
        bias = filing_bias(intel.filings)
        if not intel.filings:
            return intel.model_copy(update={"filing_bias": 0.0})
        extra = ""
        if self.llm.enabled:
            evidence = [
                {
                    "id": f.id,
                    "form": f.form,
                    "filed_at": f.filed_at.isoformat(),
                    "description": f.description,
                    "url": f.url,
                }
                for f in intel.filings[:4]
            ]
            prompt = (
                f"Summarize SEC filings for {intel.ticker} in 2 sentences for a PM. "
                f"Evidence: {evidence}. Mention form types. Do not invent numbers."
            )

            class _FilingNote(BaseModel):
                note: str
                filing_bias: float = Field(ge=-1, le=1)

            pack = await self.llm.complete_json(prompt, _FilingNote)
            if pack:
                extra = pack.note
                bias = pack.filing_bias
        note = extra or (
            f"{len(intel.filings)} recent SEC form(s) on file, most recent "
            f"{intel.filings[0].form} dated {intel.filings[0].filed_at.date()}."
        )
        narrative = intel.narrative
        if note:
            narrative = f"{narrative} {note}".strip()
        return intel.model_copy(update={"filing_bias": bias, "narrative": narrative})


def _fallback_narrative(intel: TickerIntel, bias: float) -> str:
    tone = "constructive" if bias > 0.12 else "cautious" if bias < -0.12 else "mixed"
    latest = intel.news[0].headline if intel.news else "No fresh headlines in the lookback window."
    return f"Tape is {tone} for {intel.ticker}. Latest item: {latest}"
