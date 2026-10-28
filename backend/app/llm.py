"""Claude access. If ANTHROPIC_API_KEY is not set, the agent runs in rules mode."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .config import settings


def parse_json(text: str) -> Any:
    """Read a JSON value from a model reply: whole text, a ``` fence, or first {/[ to last }/]."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    f = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if f:
        try:
            return json.loads(f.group(1))
        except ValueError:
            pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    end = max(text.rfind("}"), text.rfind("]"))
    if starts and end > min(starts):
        return json.loads(text[min(starts): end + 1])
    raise ValueError("No JSON found in the model reply")


class LLM:
    def __init__(self, api_key: str | None, model: str):
        self.model = model
        self.client = None
        if api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)

    @property
    def available(self) -> bool:
        return self.client is not None

    def complete(self, prompt: str, max_tokens: int = 2500) -> str:
        msg = self.client.messages.create(model=self.model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    def chat(self, system: str, messages: list[dict], tools: list[dict], run_tool: Callable[[str, dict], Any], max_rounds: int = 6) -> tuple[str, list[str]]:
        """Tool-use loop: Claude calls our read-only tools until it can answer."""
        used: list[str] = []
        convo = [dict(x) for x in messages]
        for _ in range(max_rounds):
            msg = self.client.messages.create(model=self.model, max_tokens=1500, system=system, tools=tools, messages=convo)
            if msg.stop_reason != "tool_use":
                return "".join(b.text for b in msg.content if b.type == "text").strip(), used
            convo.append({"role": "assistant", "content": [b.model_dump() for b in msg.content]})
            results = []
            for b in msg.content:
                if b.type == "tool_use":
                    used.append(b.name)
                    try:
                        out, err = run_tool(b.name, b.input or {}), False
                    except Exception as e:  # tool errors go back to Claude, not to the user
                        out, err = f"Error: {e}", True
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str)[:30000], "is_error": err})
            convo.append({"role": "user", "content": results})
        return "I could not finish looking that up. Try a narrower question.", used


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM(settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL)
    return _llm


def set_llm(llm) -> None:
    """Swap the model client (used by tests)."""
    global _llm
    _llm = llm
