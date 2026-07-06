# Evaluation Pipeline Report

## Architecture

The submission implements the speedrun Airflow pipeline:

```text
prepare_run -> run_agent -> run_eval -> summarize_and_log
```

The Airflow DAG lives in `dags/evaluate_agent.py`. It stays thin and delegates
reusable behavior to `pipeline/evaluate_agent.py`, where run configuration,
artifact layout, subprocess calls, metrics parsing, manifest writing, and MLflow
logging are implemented.

The DAG accepts Airflow params for `split`, `subset`, `workers`, `model`,
`task_slice`, `run_id`, `cost_limit`, `mlflow_tracking_uri`, and
`mlflow_experiment`. Defaults run a small SWE-bench Verified test slice with
`nebius/moonshotai/Kimi-K2.6`.

## How to Run

Install dependencies:

```bash
uv sync
cp .env.example .env
```

Set `NEBIUS_API_KEY` in `.env`.

Start MLflow in a separate shell:

```bash
uv run mlflow server \
  --host 127.0.0.1 \
  --port 5001 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns
```

Start Airflow:

```bash
bash run-airflow-standalone.sh
```

Open Airflow at `http://localhost:8080`, enable the `evaluate-agent` DAG, and
trigger it with params such as:

```json
{
  "split": "test",
  "subset": "verified",
  "workers": 2,
  "model": "nebius/moonshotai/Kimi-K2.6",
  "task_slice": "0:1",
  "run_id": "local-small-test-3",
  "cost_limit": 0,
  "mlflow_tracking_uri": "http://localhost:5001",
  "mlflow_experiment": "coding-agent-evaluation"
}
```

## Artifact Layout

Each run is written under `runs/<run-id>/`:

```text
runs/<run-id>/
  config.json
  run-agent/
    preds.json
    trajectories/
  run-eval/
    logs/
  metrics.json
  manifest.json
```

`config.json` records the full Airflow-derived configuration. `run-agent/`
contains mini-swe-agent trajectories and predictions. `run-eval/logs/` contains
SWE-bench evaluation logs and per-instance `report.json` files. `metrics.json`
contains aggregate metrics parsed from those reports. `manifest.json` records
the important files, directories, metrics, config, and local artifact URI.

For remote storage, the same `runs/<run-id>/` directory can be uploaded as a
folder or compressed archive to S3/Object Storage. The resulting URI should be
used as the `artifact_uri` logged to MLflow.

## MLflow Tracking

The `summarize_and_log` task logs these MLflow params:

- `run_id`
- `split`
- `subset`
- `workers`
- `model`
- `task_slice`
- `cost_limit`
- `dataset_name`

It logs aggregate metrics from `metrics.json`, sets an `artifact_uri` tag, and
uploads `config.json` plus `metrics.json` as MLflow artifacts.

If MLflow is not available in the Airflow environment, the helper writes
`mlflow-skipped.json` in the run folder. The provided Airflow launcher uses
`uv run --with apache-airflow ...`, so project dependencies such as MLflow are
available to the DAG.

## Completed Real Run

The completed local Airflow run is `local-small-test-3`.

- Airflow DAG run:
  `manual__2026-07-06T14:42:01.087690+00:00`
- MLflow run ID: `7228ac3df8384fd69e57160ef43e1553`
- Artifact folder: `runs/local-small-test-3/`
- Manifest: `runs/local-small-test-3/manifest.json`

Evidence screenshots:

- `screenshots/airflow-local-small-test-3.png`
- `screenshots/mlflow-runs-local-small-test-3.png`
- `screenshots/mlflow-run-detail-local-small-test-3.png`

Run metrics:

```json
{
  "instances_total": 1,
  "instances_resolved": 1,
  "resolution_rate": 1.0,
  "patches_existing": 1,
  "patches_applied": 1,
  "fail_to_pass_success": 2,
  "fail_to_pass_failure": 0,
  "pass_to_pass_success": 13,
  "pass_to_pass_failure": 0
}
```

This run produced a non-empty patch for `astropy__astropy-12907`, evaluated it
with SWE-bench, wrote per-instance evaluation logs and `report.json`, wrote
aggregate metrics and a manifest, and logged parameters plus metrics to MLflow.

## Bundled Sample Run

The repository includes `runs/sample-kimi-k2-6-test/`, rebuilt from the provided
sample outputs. It demonstrates the required artifact layout and metrics parsing
without requiring a live API call.

Sample metrics:

```json
{
  "instances_total": 3,
  "instances_resolved": 1,
  "resolution_rate": 0.3333333333333333,
  "patches_existing": 3,
  "patches_applied": 3,
  "fail_to_pass_success": 2,
  "fail_to_pass_failure": 3,
  "pass_to_pass_success": 677,
  "pass_to_pass_failure": 0
}
```

To reproduce another fresh run, trigger the Airflow DAG with a new `run_id`. The
new folder under `runs/` should contain the full input config, agent
trajectories, predictions, evaluation logs, aggregate metrics, and manifest.
