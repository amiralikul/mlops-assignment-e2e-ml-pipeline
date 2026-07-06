from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pipeline.evaluate_agent import run_agent_batch, run_swebench_eval, summarize_run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run one evaluation pipeline phase.")
    parser.add_argument("phase", choices=["run-agent", "run-eval", "summarize"])
    parser.add_argument("config_path")
    args = parser.parse_args(argv)

    os.environ.setdefault("PIPELINE_USE_UV", "0")
    config_path = Path(args.config_path)
    config = json.loads(config_path.read_text())
    run_dir = Path(config["runs_root"]) / config["run_id"]

    if args.phase == "run-agent":
        run_agent_batch(config, run_dir)
        return

    if args.phase == "run-eval":
        run_swebench_eval(config, run_dir / "run-agent" / "preds.json", run_dir)
        return

    summarize_run(config)


if __name__ == "__main__":
    main()
