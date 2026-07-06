import json

from pipeline.evaluate_agent import (
    build_run_config,
    collect_metrics,
    prepare_run_dir,
    write_manifest,
)


def test_build_run_config_normalizes_required_airflow_params(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow.example:5000")

    config = build_run_config(
        {
            "split": "test",
            "subset": "verified",
            "workers": "3",
            "model": "nebius/example/model",
            "task_slice": "0:2",
            "run_id": "manual-run",
            "cost_limit": "0.25",
            "runs_root": str(tmp_path),
        }
    )

    assert config == {
        "run_id": "manual-run",
        "split": "test",
        "subset": "verified",
        "workers": 3,
        "model": "nebius/example/model",
        "task_slice": "0:2",
        "cost_limit": 0.25,
        "dataset_name": "princeton-nlp/SWE-bench_Verified",
        "mlflow_tracking_uri": "http://mlflow.example:5000",
        "mlflow_experiment": "coding-agent-evaluation",
        "runs_root": str(tmp_path),
    }


def test_prepare_run_dir_writes_reproducible_config(tmp_path):
    config = build_run_config({"run_id": "abc123", "runs_root": str(tmp_path)})

    run_dir = prepare_run_dir(config)

    assert run_dir == tmp_path / "abc123"
    assert (run_dir / "run-agent" / "trajectories").is_dir()
    assert (run_dir / "run-eval" / "logs").is_dir()
    assert json.loads((run_dir / "config.json").read_text())["run_id"] == "abc123"


def test_collect_metrics_aggregates_swebench_reports(tmp_path):
    reports_dir = tmp_path / "run-eval" / "logs" / "run_evaluation" / "test"
    first = reports_dir / "model" / "task-one"
    second = reports_dir / "model" / "task-two"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "report.json").write_text(
        json.dumps(
            {
                "task-one": {
                    "resolved": True,
                    "patch_exists": True,
                    "patch_successfully_applied": True,
                    "tests_status": {
                        "FAIL_TO_PASS": {"success": ["a"], "failure": []},
                        "PASS_TO_PASS": {"success": ["b", "c"], "failure": []},
                    },
                }
            }
        )
    )
    (second / "report.json").write_text(
        json.dumps(
            {
                "task-two": {
                    "resolved": False,
                    "patch_exists": True,
                    "patch_successfully_applied": False,
                    "tests_status": {
                        "FAIL_TO_PASS": {"success": [], "failure": ["d"]},
                        "PASS_TO_PASS": {"success": ["e"], "failure": ["f"]},
                    },
                }
            }
        )
    )

    metrics = collect_metrics(tmp_path / "run-eval")

    assert metrics == {
        "instances_total": 2,
        "instances_resolved": 1,
        "resolution_rate": 0.5,
        "patches_existing": 2,
        "patches_applied": 1,
        "fail_to_pass_success": 1,
        "fail_to_pass_failure": 1,
        "pass_to_pass_success": 3,
        "pass_to_pass_failure": 1,
    }


def test_write_manifest_records_core_artifacts(tmp_path):
    run_dir = tmp_path / "run-1"
    (run_dir / "run-agent" / "trajectories").mkdir(parents=True)
    (run_dir / "run-eval" / "logs").mkdir(parents=True)
    for relative_path in [
        "config.json",
        "run-agent/preds.json",
        "metrics.json",
    ]:
        path = run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")

    manifest_path = write_manifest(
        run_dir,
        config={"run_id": "run-1"},
        metrics={"instances_total": 0},
        artifact_uri=str(run_dir),
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["run_id"] == "run-1"
    assert manifest["artifact_uri"] == str(run_dir)
    assert manifest["files"]["config"] == "config.json"
    assert manifest["files"]["predictions"] == "run-agent/preds.json"
    assert manifest["files"]["metrics"] == "metrics.json"
    assert manifest["directories"]["trajectories"] == "run-agent/trajectories"
    assert manifest["metrics"]["instances_total"] == 0
