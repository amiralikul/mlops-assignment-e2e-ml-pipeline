from pathlib import Path


def test_evaluate_agent_dag_exposes_assignment_tasks_and_params():
    dag_source = Path("dags/evaluate_agent.py").read_text()

    for task_name in [
        "prepare_run",
        "run_agent",
        "run_eval",
        "summarize_and_log",
    ]:
        assert f"def {task_name}" in dag_source

    for param_name in [
        "split",
        "subset",
        "workers",
        "model",
        "task_slice",
        "run_id",
        "cost_limit",
    ]:
        assert f'"{param_name}"' in dag_source

    assert 'dag_id="evaluate-agent"' in dag_source
