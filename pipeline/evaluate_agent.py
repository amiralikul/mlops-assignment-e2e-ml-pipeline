from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "nebius/moonshotai/Kimi-K2.6"
DEFAULT_EXPERIMENT = "coding-agent-evaluation"


def build_run_config(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    subset = str(params.get("subset") or "verified")
    split = str(params.get("split") or "test")
    run_id = str(params.get("run_id") or _default_run_id())

    return {
        "run_id": run_id,
        "split": split,
        "subset": subset,
        "workers": int(params.get("workers") or 5),
        "model": str(params.get("model") or DEFAULT_MODEL),
        "task_slice": str(params.get("task_slice") or "0:3"),
        "cost_limit": float(params.get("cost_limit") or 0),
        "dataset_name": str(
            params.get("dataset_name") or dataset_name_for_subset(subset)
        ),
        "mlflow_tracking_uri": str(
            params.get("mlflow_tracking_uri")
            or os.environ.get("MLFLOW_TRACKING_URI")
            or "http://localhost:5000"
        ),
        "mlflow_experiment": str(
            params.get("mlflow_experiment")
            or os.environ.get("MLFLOW_EXPERIMENT_NAME")
            or DEFAULT_EXPERIMENT
        ),
        "runs_root": str(params.get("runs_root") or PROJECT_ROOT / "runs"),
    }


def dataset_name_for_subset(subset: str) -> str:
    normalized = subset.strip().lower()
    if normalized == "verified":
        return "princeton-nlp/SWE-bench_Verified"
    if normalized == "lite":
        return "princeton-nlp/SWE-bench_Lite"
    return "princeton-nlp/SWE-bench"


def prepare_run_dir(run_config: dict[str, Any]) -> Path:
    run_dir = Path(run_config["runs_root"]) / run_config["run_id"]
    (run_dir / "run-agent" / "trajectories").mkdir(parents=True, exist_ok=True)
    (run_dir / "run-eval" / "logs").mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "config.json", run_config)
    return run_dir


def run_agent_batch(run_config: dict[str, Any], run_dir: Path) -> Path:
    trajectories_dir = run_dir / "run-agent" / "trajectories"
    trajectories_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "uv",
        "run",
        "mini-extra",
        "swebench",
        "--subset",
        run_config["subset"],
        "--split",
        run_config["split"],
        "--model",
        run_config["model"],
        "--workers",
        str(run_config["workers"]),
        "-o",
        str(trajectories_dir),
    ]
    if run_config.get("task_slice"):
        command.extend(["--slice", str(run_config["task_slice"])])

    benchmark_config = (
        PROJECT_ROOT
        / "mini-swe-agent"
        / "src"
        / "minisweagent"
        / "config"
        / "benchmarks"
        / "swebench.yaml"
    )
    if benchmark_config.exists():
        command.extend(["--config", str(benchmark_config)])

    _run(command, cwd=PROJECT_ROOT)

    generated_preds = trajectories_dir / "preds.json"
    preds_path = run_dir / "run-agent" / "preds.json"
    if not generated_preds.exists():
        raise FileNotFoundError(f"mini-swe-agent did not write {generated_preds}")
    shutil.copy2(generated_preds, preds_path)
    return preds_path


def run_swebench_eval(
    run_config: dict[str, Any], preds_path: Path, run_dir: Path
) -> Path:
    eval_dir = run_dir / "run-eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        run_config["dataset_name"],
        "--predictions_path",
        str(preds_path),
        "--max_workers",
        str(run_config["workers"]),
        "--run_id",
        run_config["run_id"],
    ]
    _run(command, cwd=eval_dir)
    return eval_dir


def collect_metrics(eval_dir: Path) -> dict[str, int | float]:
    reports = []
    for report_path in sorted(eval_dir.rglob("report.json")):
        report = json.loads(report_path.read_text())
        reports.extend(report.values())

    if not reports:
        summary_metrics = _collect_summary_metrics(eval_dir)
        if summary_metrics is not None:
            return summary_metrics

    total = len(reports)
    resolved = sum(1 for report in reports if report.get("resolved"))
    metrics: dict[str, int | float] = {
        "instances_total": total,
        "instances_resolved": resolved,
        "resolution_rate": resolved / total if total else 0.0,
        "patches_existing": sum(1 for report in reports if report.get("patch_exists")),
        "patches_applied": sum(
            1 for report in reports if report.get("patch_successfully_applied")
        ),
        "fail_to_pass_success": 0,
        "fail_to_pass_failure": 0,
        "pass_to_pass_success": 0,
        "pass_to_pass_failure": 0,
    }

    for report in reports:
        statuses = report.get("tests_status") or {}
        fail_to_pass = statuses.get("FAIL_TO_PASS") or {}
        pass_to_pass = statuses.get("PASS_TO_PASS") or {}
        metrics["fail_to_pass_success"] += len(fail_to_pass.get("success") or [])
        metrics["fail_to_pass_failure"] += len(fail_to_pass.get("failure") or [])
        metrics["pass_to_pass_success"] += len(pass_to_pass.get("success") or [])
        metrics["pass_to_pass_failure"] += len(pass_to_pass.get("failure") or [])

    return metrics


def _collect_summary_metrics(eval_dir: Path) -> dict[str, int | float] | None:
    for summary_path in sorted(eval_dir.glob("*.json")):
        summary = json.loads(summary_path.read_text())
        if "submitted_instances" not in summary:
            continue
        submitted = int(summary.get("submitted_instances") or 0)
        resolved = int(summary.get("resolved_instances") or 0)
        return {
            "instances_total": submitted,
            "instances_resolved": resolved,
            "resolution_rate": resolved / submitted if submitted else 0.0,
            "patches_existing": submitted
            - int(summary.get("empty_patch_instances") or 0),
            "patches_applied": int(summary.get("completed_instances") or 0),
            "fail_to_pass_success": 0,
            "fail_to_pass_failure": 0,
            "pass_to_pass_success": 0,
            "pass_to_pass_failure": 0,
            "empty_patch_instances": int(summary.get("empty_patch_instances") or 0),
            "error_instances": int(summary.get("error_instances") or 0),
        }
    return None


def summarize_run(run_config: dict[str, Any]) -> dict[str, str]:
    run_dir = Path(run_config["runs_root"]) / run_config["run_id"]
    metrics = collect_metrics(run_dir / "run-eval")
    _write_json(run_dir / "metrics.json", metrics)
    artifact_uri = log_mlflow_run(run_config, metrics, run_dir)
    manifest_path = write_manifest(run_dir, run_config, metrics, artifact_uri)
    return {
        "run_dir": str(run_dir),
        "metrics_path": str(run_dir / "metrics.json"),
        "manifest_path": str(manifest_path),
        "artifact_uri": artifact_uri,
    }


def write_manifest(
    run_dir: Path,
    config: dict[str, Any],
    metrics: dict[str, Any],
    artifact_uri: str,
) -> Path:
    manifest = {
        "run_id": config["run_id"],
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_uri": artifact_uri,
        "files": {
            "config": _relative_if_exists(run_dir, run_dir / "config.json"),
            "predictions": _relative_if_exists(
                run_dir, run_dir / "run-agent" / "preds.json"
            ),
            "metrics": _relative_if_exists(run_dir, run_dir / "metrics.json"),
        },
        "directories": {
            "trajectories": _relative_if_exists(
                run_dir, run_dir / "run-agent" / "trajectories"
            ),
            "evaluation_logs": _relative_if_exists(
                run_dir, run_dir / "run-eval" / "logs"
            ),
            "evaluation": _relative_if_exists(run_dir, run_dir / "run-eval"),
        },
        "config": config,
        "metrics": metrics,
    }
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def log_mlflow_run(
    run_config: dict[str, Any],
    metrics: dict[str, int | float],
    run_dir: Path,
) -> str:
    artifact_uri = str(run_dir.resolve())
    try:
        import mlflow
    except ImportError:
        _write_json(
            run_dir / "mlflow-skipped.json",
            {
                "reason": "mlflow package is not installed",
                "tracking_uri": run_config["mlflow_tracking_uri"],
                "experiment": run_config["mlflow_experiment"],
            },
        )
        return artifact_uri

    mlflow.set_tracking_uri(run_config["mlflow_tracking_uri"])
    mlflow.set_experiment(run_config["mlflow_experiment"])
    with mlflow.start_run(run_name=run_config["run_id"]):
        mlflow.log_params(
            {
                "run_id": run_config["run_id"],
                "split": run_config["split"],
                "subset": run_config["subset"],
                "workers": run_config["workers"],
                "model": run_config["model"],
                "task_slice": run_config["task_slice"],
                "cost_limit": run_config["cost_limit"],
                "dataset_name": run_config["dataset_name"],
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.set_tag("artifact_uri", artifact_uri)
        mlflow.log_artifact(str(run_dir / "config.json"), artifact_path="run")
        mlflow.log_artifact(str(run_dir / "metrics.json"), artifact_path="run")
    return artifact_uri


def _run(command: list[str], cwd: Path) -> None:
    env = {
        **os.environ,
        **_read_dotenv(PROJECT_ROOT / ".env"),
        "MSWEA_COST_TRACKING": "ignore_errors",
    }
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _default_run_id() -> str:
    return datetime.now(UTC).strftime("manual__%Y%m%dT%H%M%SZ")


def _relative_if_exists(run_dir: Path, path: Path) -> str | None:
    if not path.exists():
        return None
    return path.relative_to(run_dir).as_posix()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
