from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from docker.types import Mount

try:
    from airflow.sdk import Param, dag, get_current_context, task
except ImportError:
    from airflow.decorators import dag, task
    from airflow.models.param import Param
    from airflow.operators.python import get_current_context

from airflow.providers.docker.operators.docker import DockerOperator


PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.evaluate_agent import _read_dotenv, build_run_config, prepare_run_dir  # noqa: E402


DOCKER_IMAGE = os.environ.get("EVALUATION_IMAGE", "mlops-assignment:latest")
DOCKER_WORKDIR = "/mlops-assignment"
DOCKER_SOCKET = "/var/run/docker.sock"
DOCKER_NETWORK = os.environ.get("DOCKER_OPERATOR_NETWORK", "bridge")
DOTENV = _read_dotenv(PROJECT_ROOT / ".env")


def _env_value(name: str, default: str = "") -> str:
    return os.environ.get(name) or DOTENV.get(name, default)


def _container_environment() -> dict[str, str]:
    return {
        "NEBIUS_API_KEY": _env_value("NEBIUS_API_KEY"),
        "NEBIUS_ADMIN_KEY": _env_value("NEBIUS_ADMIN_KEY"),
        "OPENAI_API_KEY": _env_value("OPENAI_API_KEY"),
        "HF_TOKEN": _env_value("HF_TOKEN"),
        "MLFLOW_TRACKING_URI": _env_value(
            "MLFLOW_TRACKING_URI", "http://host.docker.internal:5001"
        ),
        "MLFLOW_EXPERIMENT_NAME": _env_value(
            "MLFLOW_EXPERIMENT_NAME", "coding-agent-evaluation"
        ),
        "PIPELINE_USE_UV": "0",
        "MSWEA_COST_TRACKING": "ignore_errors",
    }


def _mounts() -> list[Mount]:
    return [
        Mount(source=str(PROJECT_ROOT), target=str(PROJECT_ROOT), type="bind"),
        Mount(source=DOCKER_SOCKET, target=DOCKER_SOCKET, type="bind"),
    ]


@dag(
    dag_id="evaluate-agent-docker",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    params={
        "split": Param("test", type="string"),
        "subset": Param("verified", type="string"),
        "workers": Param(2, type="integer", minimum=1),
        "model": Param("nebius/moonshotai/Kimi-K2.6", type="string"),
        "task_slice": Param("0:1", type="string"),
        "run_id": Param("", type="string"),
        "cost_limit": Param(0.0, type="number", minimum=0),
        "mlflow_tracking_uri": Param("http://mlflow:5000", type="string"),
        "mlflow_experiment": Param("coding-agent-evaluation", type="string"),
    },
    tags=["swe-bench", "mini-swe-agent", "evaluation", "docker"],
)
def evaluate_agent_docker_dag():
    @task
    def prepare_run() -> dict[str, Any]:
        context = get_current_context()
        run_config = build_run_config(
            {
                **context["params"],
                "runs_root": str(PROJECT_ROOT / "runs"),
            }
        )
        run_dir = prepare_run_dir(run_config)
        return {**run_config, "run_dir": str(run_dir)}

    config = prepare_run()
    config_path = f"{PROJECT_ROOT}/runs/{{{{ ti.xcom_pull(task_ids='prepare_run')['run_id'] }}}}/config.json"

    run_agent = DockerOperator(
        task_id="run_agent",
        image=DOCKER_IMAGE,
        command=["python", "-m", "pipeline.docker_task", "run-agent", config_path],
        docker_url=f"unix://{DOCKER_SOCKET}",
        network_mode=DOCKER_NETWORK,
        working_dir=DOCKER_WORKDIR,
        auto_remove="success",
        mount_tmp_dir=False,
        mounts=_mounts(),
        environment=_container_environment(),
    )

    run_eval = DockerOperator(
        task_id="run_eval",
        image=DOCKER_IMAGE,
        command=["python", "-m", "pipeline.docker_task", "run-eval", config_path],
        docker_url=f"unix://{DOCKER_SOCKET}",
        network_mode=DOCKER_NETWORK,
        working_dir=DOCKER_WORKDIR,
        auto_remove="success",
        mount_tmp_dir=False,
        mounts=_mounts(),
        environment=_container_environment(),
    )

    summarize_and_log = DockerOperator(
        task_id="summarize_and_log",
        image=DOCKER_IMAGE,
        command=["python", "-m", "pipeline.docker_task", "summarize", config_path],
        docker_url=f"unix://{DOCKER_SOCKET}",
        network_mode=DOCKER_NETWORK,
        working_dir=DOCKER_WORKDIR,
        auto_remove="success",
        mount_tmp_dir=False,
        mounts=_mounts(),
        environment=_container_environment(),
    )

    config >> run_agent >> run_eval >> summarize_and_log


evaluate_agent_docker_dag()
