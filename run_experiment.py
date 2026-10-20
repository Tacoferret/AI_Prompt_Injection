"""Run the experiment: 20 tasks x 3 conditions (E1 clean, E2 document injection, E3 search injection).

  python run_experiment.py --dry-run     # offline pipeline test with a scripted fake model
  python run_experiment.py --limit 3     # smoke test: first 3 trials only, real model
  python run_experiment.py               # full run: 60 trials, real model
  python run_experiment.py --repeats 3   # 180 trials
  python run_experiment.py --mode free   # model chooses its own tools (it may skip the document)

Per trial (the plan's procedure): reset agent state -> load task and source condition ->
run with fixed model settings -> save tool trace and final answer -> score (score.py).
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from agent import run_agent
from llm import MockChat, OpenAIChat
from tools import TOOL_SCHEMAS, MockTools


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["openai", "ollama"], default="openai",
                    help="openai = hosted API (needs OPENAI_API_KEY); ollama = local model, no key")
    ap.add_argument("--model", default=None, help="default: gpt-6-luna (openai) or llama3.1 (ollama)")
    ap.add_argument("--dry-run", action="store_true", help="use the scripted mock model (no API calls)")
    ap.add_argument("--conditions", default="E1,E2,E3")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None, help="only run the first N trials (smoke test)")
    ap.add_argument("--mode", choices=["forced", "free"], default=config.AGENT_MODE,
                    help="forced = harness always runs search then read_document; free = model picks tools")
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args()
    if a.model is None:
        a.model = config.MODEL if a.backend == "openai" else config.OLLAMA_MODEL

    conditions = set(a.conditions.split(","))
    recs = [json.loads(l) for l in open(config.DATASET_PATH, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if r["condition"] in conditions]
    trials = [(rep, r) for rep in range(a.repeats) for r in recs]
    random.Random(config.SEED).shuffle(trials)
    if a.limit:
        trials = trials[: a.limit]

    model_name = "mock" if a.dry_run else a.model
    run_dir = Path(config.RESULTS_DIR) / (("dryrun_" if a.dry_run else "run_")
                                           + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + model_name.replace("/", "-").replace(":", "-"))
    run_dir.mkdir(parents=True, exist_ok=True)

    if a.dry_run:
        llm = MockChat()
    elif a.backend == "ollama":
        # Local server, no real key. reasoning_effort is an OpenAI-only setting, so it is not sent.
        from openai import OpenAI
        client = OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
        llm = OpenAIChat(a.model, config.TEMPERATURE, None, client=client)
    else:
        llm = OpenAIChat(a.model, config.TEMPERATURE, config.REASONING_EFFORT)
    if a.dry_run:
        print("DRY RUN: scripted mock model. Results are for pipeline testing only, never for the report.\n")

    with open(run_dir / "traces.jsonl", "w", encoding="utf-8") as out:
        for idx, (rep, rec) in enumerate(trials, start=1):
            tools = MockTools(rec)                      # fresh tools and fresh messages every trial
            entry = {"agent_mode": a.mode, "trial_index": idx, "repeat": rep, "record": rec,
                     "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                res = run_agent(llm, tools, TOOL_SCHEMAS, config.SYSTEM_PROMPT, rec["user_request"], config.MAX_STEPS,
                                forced=(a.mode == "forced"))
                entry.update(res)
                entry["model_returned"] = next((e["model"] for e in res["trace"] if e["type"] == "assistant" and not e.get("forced")), "")
                entry["temperature_used"] = llm.temperature_used
            except Exception as e:  # noqa: BLE001  (record the failure, keep going)
                entry.update({"error": f"{type(e).__name__}: {e}", "final_answer": "", "trace": [],
                              "n_model_calls": 0, "step_limit_hit": False,
                              "model_returned": "", "temperature_used": getattr(llm, "temperature_used", "")})
            out.write(json.dumps(entry, ensure_ascii=False) + "\n"); out.flush()
            print(f"[{idx}/{len(trials)}] {rec['task_id']} {rec['condition']}: "
                  f"{(entry.get('error') or entry['final_answer']).strip()[:80]!r}")

    print(f"\n{len(trials)} trials run. Saved to {run_dir}")
    import score
    score.score_run(run_dir)
    if not a.no_report:
        import report
        report.make_chart(run_dir)


if __name__ == "__main__":
    sys.exit(main())
