"""A stand-in for Claude that answers the agent's prompts the way a good model should.

It lets the AI code path be tested without an API key. It does not measure real
model quality: run the scenarios with a real key for that.
"""
import json
import re


class FakeLLM:
    available = True
    model = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, prompt: str, max_tokens: int = 0) -> str:
        self.calls.append(prompt)
        if prompt.startswith("You read supplier emails"):
            ctx = json.loads(prompt.split("Open purchase orders in the ERP:\n")[1].split("\n")[0])
            FakeLLM.pos = {p["po"]: max(x.split(" on ")[1] for x in p["arrives"].split(", ")) for p in ctx}
            return json.dumps(self._read(prompt.split('Email:\n"""\n')[1].split('\n"""')[0]))
        if prompt.startswith("Write delay notices"):
            facts = json.loads(prompt.split("Use only these facts:\n")[1].split("\n\nFor each")[0])
            return "```json\n" + json.dumps([{"so": f["so"], "subject": f"Order {f['so']}: new date {f['new_date']}",
                                               "body": f"Hi {f['contact_first_name']}, order {f['so']} now arrives {f['new_date']} instead of {f['promised']}. {f['sender']}, Order desk",
                                               "crm_note": f"Delay notice sent for {f['so']}."} for f in facts]) + "\n```"
        raise AssertionError("Unexpected prompt")

    @staticmethod
    def _read(em: str) -> dict:
        """Answer like a careful model: reuse the rules engine's reading, with the ERP context from the prompt."""
        from app.rules_reader import read_email

        return {k: v for k, v in read_email(em, "2026-10-26", FakeLLM.pos).items() if k in ("type", "po", "new_date", "split", "confidence", "summary")}

    pos: dict = {}
