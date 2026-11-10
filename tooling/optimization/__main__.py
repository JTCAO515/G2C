import argparse
import json
from pathlib import Path

from .checkpoint import load_checkpoint, verify_artifacts
from .contracts import Limits
from .runner import run


def main():
    parser = argparse.ArgumentParser(description="#763 offline Fake GEPA only")
    parser.add_argument("command", choices=("run", "resume", "stop", "status"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--clear-stop", action="store_true")
    parser.add_argument("--task-calls", type=int, default=48)
    parser.add_argument("--score-calls", type=int, default=48)
    parser.add_argument("--reflection-calls", type=int, default=6)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.command == "stop":
        if not (args.run_dir / "checkpoint.json").exists():
            parser.error("run does not exist")
        (args.run_dir / "STOP").touch()
        print(json.dumps({"status": "STOP_REQUESTED"}))
        return 0
    if args.command == "status":
        state = load_checkpoint(args.run_dir / "checkpoint.json")
        verify_artifacts(args.run_dir, state)
    else:
        state = run(args.run_dir, Limits(args.task_calls, args.score_calls, args.reflection_calls,
                                        args.seconds, args.seed), resume=args.command == "resume",
                    clear_stop=args.clear_stop)
    print(json.dumps({"run_id": state["run_id"], "status": state["status"],
                      "reason": state.get("reason"), "attempts": len(state["operations"]),
                      "evidence": "FAKE_ONLY"}))
    return 0 if state["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
