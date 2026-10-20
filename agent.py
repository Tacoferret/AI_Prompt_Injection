"""A small tool-using agent loop: the model may call tools, sees their results, and answers.

The agent holds no state between calls to run_agent(): every trial starts from a fresh
message list and a fresh MockTools object (step 1 of the plan's trial procedure).
"""
import json


def _forced_lookup(tools_obj, messages, trace, user_request):
    """Forced mode: the harness itself runs search_info(user_request) and then read_document(doc_id)
    and puts both results in front of the model before it answers. This guarantees that every trial
    exposes the payload exactly once, in its condition's location (snippet for E3, document for E2),
    whatever the model would have chosen to do. The model still writes the final answer."""
    def step(i, name, args):
        call_id = f"forced_{i}"
        arguments = json.dumps(args)
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}]})
        trace.append({"type": "assistant", "step": f"forced_{i}", "content": "", "forced": True, "model": "harness",
                      "tool_calls": [{"id": call_id, "name": name, "arguments": arguments}]})
        output = tools_obj.call(name, args)
        trace.append({"type": "tool_result", "step": f"forced_{i}", "tool": name, "arguments": args, "output": output})
        messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
        return output

    found = json.loads(step(1, "search_info", {"query": user_request}))
    doc_id = found["results"][0]["doc_id"]
    step(2, "read_document", {"doc_id": doc_id})


def run_agent(llm, tools_obj, tool_schemas, system_prompt, user_request, max_steps, forced=False):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    trace = [
        {"type": "system", "content": system_prompt},
        {"type": "user", "content": user_request},
    ]
    if forced:
        _forced_lookup(tools_obj, messages, trace, user_request)
    final_answer = ""
    step_limit_hit = False
    n_model_calls = 0

    for step in range(max_steps):
        reply = llm.chat(messages, tool_schemas)
        n_model_calls += 1
        trace.append({"type": "assistant", "step": step, "content": reply.content,
                      "tool_calls": reply.tool_calls, "model": reply.model})
        if not reply.tool_calls:
            final_answer = reply.content
            break
        messages.append({
            "role": "assistant",
            "content": reply.content or None,
            "tool_calls": [{"id": tc["id"], "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                           for tc in reply.tool_calls],
        })
        for tc in reply.tool_calls:
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
                output = json.dumps({"error": "Invalid JSON arguments"})
            else:
                output = tools_obj.call(tc["name"], args)
            trace.append({"type": "tool_result", "step": step, "tool": tc["name"],
                          "arguments": args, "output": output})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})
    else:
        step_limit_hit = True

    return {"final_answer": final_answer, "trace": trace,
            "step_limit_hit": step_limit_hit, "n_model_calls": n_model_calls}
