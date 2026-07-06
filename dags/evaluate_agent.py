from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from airflow.sdk import Param, dag, get_current_context, task
except ImportError:
    from airflow.decorators import dag, task
    from airflow.models.param import Param
    from airflow.operators.python import get_current_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.evaluate_agent import (  # noqa: E402
    build_run_config,
    prepare_run_dir,
    run_agent_batch,
    run_swebench_eval,
    summarize_run,
)


@dag(
    dag_id="evaluate-agent",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    params={
        "split": Param("test", type="string"),
        "subset": Param("verified", type="string"),
        "workers": Param(5, type="integer", minimum=1),
        "model": Param("nebius/moonshotai/Kimi-K2.6", type="string"),
        "task_slice": Param("0:3", type="string"),
        "run_id": Param("", type="string"),
        "cost_limit": Param(0.0, type="number", minimum=0),
        "mlflow_tracking_uri": Param("http://localhost:5000", type="string"),
        "mlflow_experiment": Param("coding-agent-evaluation", type="string"),
    },
    tags=["swe-bench", "mini-swe-agent", "evaluation"],
)
def evaluate_agent_dag():
    @task
    def prepare_run() -> dict[str, Any]:
        context = get_current_context()
        run_config = build_run_config(context["params"])
        run_dir = prepare_run_dir(run_config)
        return {**run_config, "run_dir": str(run_dir)}

    @task
    def run_agent(run_config: dict[str, Any]) -> str:
        preds_path = run_agent_batch(run_config, Path(run_config["run_dir"]))
        return str(preds_path)

    @task
    def run_eval(run_config: dict[str, Any], preds_path: str) -> str:
        eval_dir = run_swebench_eval(
            run_config,
            Path(preds_path),
            Path(run_config["run_dir"]),
        )
        return str(eval_dir)

    @task
    def summarize_and_log(run_config: dict[str, Any], eval_dir: str) -> dict[str, str]:
        if not Path(eval_dir).exists():
            raise FileNotFoundError(eval_dir)
        return summarize_run(run_config)

    config = prepare_run()
    predictions = run_agent(config)
    evaluation = run_eval(config, predictions)
    summarize_and_log(config, evaluation)


evaluate_agent_dag()
