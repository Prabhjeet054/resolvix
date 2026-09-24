"""Agent self-check / groundedness score (second LLM pass).

Asks: “Did every troubleshooting step cite a retrieved ticket?”
If not, the resolver escalates to a human.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Require every checklist step to cite evidence (fraction of steps with a citation).
GROUNDEDNESS_PASS_SCORE = 1.0

_TICKET_CITE_RE = re.compile(
    r"(?:\[\s*)?[Tt]icket\s*#?\s*(\d+)\s*\]?"
    r"|#\s*(\d{2,})"
    r"|\[\s*(\d+)\s*\]",
)
_STEP_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:\d+[.)]\s+)"  # 1. / 1)
    r"|(?:[-*+]\s+)"  # bullets
    r")",
)


@dataclass
class GroundednessCheck:
    """Result of the citation / groundedness self-check."""

    score: float
    every_step_cited: bool
    step_count: int
    cited_step_count: int
    ungrounded_steps: list[str] = field(default_factory=list)
    cited_ticket_ids: list[int] = field(default_factory=list)
    allowed_ticket_ids: list[int] = field(default_factory=list)
    invented_ticket_ids: list[int] = field(default_factory=list)
    method: str = "heuristic"  # llm | heuristic
    summary: str = ""
    escalate: bool = False
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _allowed_ids(tickets: list[dict]) -> list[int]:
    ids: list[int] = []
    for t in tickets or []:
        tid = t.get("ticket_id")
        if tid is None:
            continue
        try:
            ids.append(int(tid))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


def _extract_cited_ids(text: str) -> list[int]:
    found: list[int] = []
    for match in _TICKET_CITE_RE.finditer(text or ""):
        for group in match.groups():
            if group is None:
                continue
            try:
                found.append(int(group))
            except ValueError:
                continue
    return sorted(set(found))


def _split_steps(resolution: str) -> list[str]:
    """Pull checklist / numbered / bullet lines from a Markdown resolution."""
    steps: list[str] = []
    for raw in (resolution or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _STEP_LINE_RE.match(line) or re.match(r"^\d+[.)]\s+", line):
            cleaned = re.sub(r"^\d+[.)]\s+", "", line)
            cleaned = re.sub(r"^[-*+]\s+", "", cleaned).strip()
            if cleaned:
                steps.append(cleaned)
    return steps


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def heuristic_groundedness(
    resolution: str,
    tickets: list[dict],
) -> GroundednessCheck:
    """Deterministic citation check used offline or as LLM fallback."""
    allowed = _allowed_ids(tickets)
    if not allowed:
        return GroundednessCheck(
            score=1.0,
            every_step_cited=True,
            step_count=0,
            cited_step_count=0,
            allowed_ticket_ids=[],
            method="heuristic",
            summary="No retrieved tickets to cite — groundedness N/A",
            escalate=False,
            reasoning="empty evidence set",
        )

    allowed_set = set(allowed)
    steps = _split_steps(resolution)
    all_cited = _extract_cited_ids(resolution)
    invented = sorted(set(all_cited) - allowed_set)
    valid_cited = sorted(set(all_cited) & allowed_set)

    if not steps:
        # Treat the whole resolution as one unit: need ≥1 valid citation.
        ok = len(valid_cited) > 0 and not invented
        return GroundednessCheck(
            score=1.0 if ok else 0.0,
            every_step_cited=ok,
            step_count=1,
            cited_step_count=1 if ok else 0,
            ungrounded_steps=[] if ok else ["(entire resolution lacks ticket citations)"],
            cited_ticket_ids=valid_cited,
            allowed_ticket_ids=allowed,
            invented_ticket_ids=invented,
            method="heuristic",
            summary=(
                "Groundedness PASS (body cites retrieved ticket(s))"
                if ok
                else "Groundedness FAIL — resolution does not cite retrieved tickets"
            ),
            escalate=not ok,
            reasoning="no checklist lines; whole-body citation check",
        )

    ungrounded: list[str] = []
    cited_n = 0
    for step in steps:
        step_ids = set(_extract_cited_ids(step)) & allowed_set
        if step_ids:
            cited_n += 1
        else:
            ungrounded.append(step[:160])

    score = cited_n / len(steps) if steps else 0.0
    every = cited_n == len(steps) and not invented
    escalate = not every

    if escalate:
        parts = []
        if ungrounded:
            parts.append(f"{len(ungrounded)}/{len(steps)} step(s) lack ticket citations")
        if invented:
            parts.append(f"invented ticket id(s): {invented}")
        summary = "Groundedness FAIL — " + "; ".join(parts)
    else:
        summary = (
            f"Groundedness PASS — all {len(steps)} step(s) cite retrieved ticket(s) "
            f"(score {score * 100:.0f}%)"
        )

    return GroundednessCheck(
        score=round(score, 4),
        every_step_cited=every,
        step_count=len(steps),
        cited_step_count=cited_n,
        ungrounded_steps=ungrounded,
        cited_ticket_ids=valid_cited,
        allowed_ticket_ids=allowed,
        invented_ticket_ids=invented,
        method="heuristic",
        summary=summary,
        escalate=escalate,
        reasoning="regex step/citation scan",
    )


def llm_groundedness(
    resolution: str,
    tickets: list[dict],
    llm: Any,
    prompt: str,
) -> GroundednessCheck | None:
    """Second LLM pass. Returns None if the response is unusable."""
    allowed = _allowed_ids(tickets)
    if not allowed:
        return heuristic_groundedness(resolution, tickets)

    try:
        raw = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a strict groundedness auditor for Resolvix. "
                        "Decide whether every troubleshooting step cites a retrieved ticket. "
                        "Return ONLY valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
    except Exception:
        return None

    data = _parse_llm_json(raw)
    if not data:
        return None

    step_count = int(data.get("step_count") or 0)
    cited_step_count = int(data.get("cited_step_count") or 0)
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = (cited_step_count / step_count) if step_count else 0.0
    score = max(0.0, min(1.0, score))

    every = bool(data.get("every_step_cited"))
    if "every_step_cited" not in data:
        every = score >= GROUNDEDNESS_PASS_SCORE

    ungrounded = [str(s) for s in (data.get("ungrounded_steps") or [])][:12]
    cited_ids = []
    for x in data.get("cited_ticket_ids") or []:
        try:
            cited_ids.append(int(x))
        except (TypeError, ValueError):
            pass
    invented = []
    for x in data.get("invented_ticket_ids") or []:
        try:
            invented.append(int(x))
        except (TypeError, ValueError):
            pass

    # Cross-check invented IDs against allowed set
    invented = sorted(set(invented) | (set(cited_ids) - set(allowed)))
    cited_ids = sorted(set(cited_ids) & set(allowed))
    every = every and score >= GROUNDEDNESS_PASS_SCORE and not invented
    escalate = not every

    reasoning = str(data.get("reasoning") or "").strip()
    if escalate:
        summary = (
            f"Groundedness FAIL (LLM self-check score {score * 100:.0f}%) — "
            "not every step cites a retrieved ticket"
        )
        if invented:
            summary += f"; invented ids={invented}"
    else:
        summary = (
            f"Groundedness PASS (LLM self-check score {score * 100:.0f}%) — "
            "every step cites retrieved ticket(s)"
        )

    return GroundednessCheck(
        score=round(score, 4),
        every_step_cited=every,
        step_count=step_count or len(_split_steps(resolution)),
        cited_step_count=cited_step_count,
        ungrounded_steps=ungrounded,
        cited_ticket_ids=cited_ids,
        allowed_ticket_ids=allowed,
        invented_ticket_ids=invented,
        method="llm",
        summary=summary,
        escalate=escalate,
        reasoning=reasoning,
    )


def check_groundedness(
    resolution: str,
    tickets: list[dict],
    llm: Any | None = None,
    prompt_builder: Any | None = None,
) -> GroundednessCheck:
    """Run LLM self-check when available; otherwise heuristic citation scan."""
    from agent.prompts import GROUNDEDNESS_PROMPT, format_evidence

    allowed = _allowed_ids(tickets)
    builder = prompt_builder or (
        lambda: GROUNDEDNESS_PROMPT.format(
            allowed_ids=", ".join(str(i) for i in allowed) or "(none)",
            evidence=format_evidence(tickets),
            resolution=resolution or "(empty)",
        )
    )

    if llm is not None:
        try:
            available = bool(llm.is_available())
        except Exception:
            available = False
        if available:
            result = llm_groundedness(
                resolution=resolution,
                tickets=tickets,
                llm=llm,
                prompt=builder(),
            )
            if result is not None:
                return result

    return heuristic_groundedness(resolution, tickets)
