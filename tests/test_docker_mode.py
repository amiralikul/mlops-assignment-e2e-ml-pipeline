from pathlib import Path

from pipeline import docker_task


def test_docker_task_agent_dispatches_from_config_path(tmp_path, monkeypatch):
    called = {}
    config_path = tmp_path / "config.json"
    config_path.write_text('{"run_id": "docker-run", "runs_root": "%s"}' % tmp_path)

    def fake_run_agent_batch(config, run_dir):
        called["config"] = config
        called["run_dir"] = run_dir
        return run_dir / "run-agent" / "preds.json"

    monkeypatch.setattr(docker_task, "run_agent_batch", fake_run_agent_batch)

    docker_task.main(["run-agent", str(config_path)])

    assert called["config"]["run_id"] == "docker-run"
    assert called["run_dir"] == tmp_path / "docker-run"


def test_docker_task_eval_dispatches_from_config_path(tmp_path, monkeypatch):
    called = {}
    run_dir = tmp_path / "docker-run"
    preds_path = run_dir / "run-agent" / "preds.json"
    preds_path.parent.mkdir(parents=True)
    preds_path.write_text("{}")
    config_path = tmp_path / "config.json"
    config_path.write_text('{"run_id": "docker-run", "runs_root": "%s"}' % tmp_path)

    def fake_run_swebench_eval(config, preds, run_directory):
        called["config"] = config
        called["preds"] = preds
        called["run_dir"] = run_directory
        return run_directory / "run-eval"

    monkeypatch.setattr(docker_task, "run_swebench_eval", fake_run_swebench_eval)

    docker_task.main(["run-eval", str(config_path)])

    assert called["config"]["run_id"] == "docker-run"
    assert called["preds"] == preds_path
    assert called["run_dir"] == run_dir


def test_docker_dag_and_compose_expose_production_style_wiring():
    dag_source = Path("dags/evaluate_agent_docker.py").read_text()
    compose_source = Path("docker-compose.yaml").read_text()

    assert 'dag_id="evaluate-agent-docker"' in dag_source
    assert "DockerOperator" in dag_source
    assert "pipeline.docker_task" in dag_source
    assert "apache-airflow-providers-docker" in compose_source
    assert "/var/run/docker.sock:/var/run/docker.sock" in compose_source
    assert "- mlflow" in compose_source
    assert "- server" in compose_source
