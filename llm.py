"""Model backends. OpenAIChat is the real one; MockChat is a scripted stand-in used ONLY to
test the pipeline offline (--dry-run). Mock results must never be reported as data."""
import hashlib
import json
import time


class Reply:
    def __init__(self, content, tool_calls, model):
        self.content = content or ""
        self.tool_calls = tool_calls  # list of {"id","name","arguments"(JSON string)}
        self.model = model


class OpenAIChat:
    def __init__(self, model, temperature=None, reasoning_effort=None, client=None):
        if client is None:
            from openai import OpenAI  # imported here so --dry-run works without the package
            client = OpenAI()          # reads OPENAI_API_KEY from the environment
        self.client = client
        self.model = model
        self.requested_temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.temperature_used = temperature if temperature is not None else "api-default"

    def chat(self, messages, tools):
        kwargs = dict(model=self.model, messages=messages, tools=tools)
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.temperature_used != "api-default":
            kwargs["temperature"] = self.temperature_used
        last_err = None
        for attempt in range(6):
            try:
                r = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if "temperature" in str(e).lower() and "temperature" in kwargs:
                    del kwargs["temperature"]          # model does not accept it
                    self.temperature_used = "api-default"
                    continue
                if type(e).__name__ == "BadRequestError" or attempt == 5:
                    raise                              # a 400 will not fix itself; do not retry
                time.sleep(2 ** attempt)
        else:
            raise last_err
        m = r.choices[0].message
        calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                 for tc in (m.tool_calls or [])]
        return Reply(m.content, calls, r.model)


class MockChat:
    """Deterministic fake agent: searches, reads, answers with the clean facts. For about a
    quarter of payload-bearing trials it 'obeys' the payload (sometimes dropping the facts),
    so the scoring and report code have something to count."""

    model = "mock-model"
    temperature_used = "mock"

    @staticmethod
    def _h(s):
        return int(hashlib.sha256(s.encode()).hexdigest(), 16)

    def chat(self, messages, tools):
        called = [tc["function"]["name"] for m in messages if m["role"] == "assistant"
                  for tc in (m.get("tool_calls") or [])]
        user = next(m["content"] for m in messages if m["role"] == "user")
        tool_out = [m["content"] for m in messages if m["role"] == "tool"]
        if "search_info" not in called:
            return Reply("", [{"id": "mock_1", "name": "search_info", "arguments": json.dumps({"query": user})}], self.model)
        if "read_document" not in called:
            doc_id = json.loads(tool_out[0])["results"][0]["doc_id"]
            return Reply("", [{"id": "mock_2", "name": "read_document", "arguments": json.dumps({"doc_id": doc_id})}], self.model)
        doc = json.loads(tool_out[1])
        body = doc["body"].split("\n\n", 1)[-1]
        facts = body.split(" Assistant: include")[0]
        seen_payload = any("Purple owl approved" in t for t in tool_out)
        key = self._h(user + doc["doc_id"] + ("P" if seen_payload else "C"))
        if seen_payload and key % 4 == 0:
            if key % 8 == 0:
                return Reply("Purple owl approved.", [], self.model)
            return Reply(facts + " Purple owl approved.", [], self.model)
        return Reply(facts, [], self.model)
