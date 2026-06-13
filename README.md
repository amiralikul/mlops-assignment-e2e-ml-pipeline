# Home assignment: End-to-end ML pipeline

**What**: Home assignment.

**Where**: Nebius Academy course [AI Performance Engineering](https://academy.nebius.com/ai-engineering-il), MLOps module, lecture #6, “End-to-end ML pipeline”.

**Author**: Simon Karasik.

**Learning objective**: Get hands-on experience combining various ML workloads (training, inference, data processing, agents, etc.) into an automated, observable, and versioned pipeline with a structured data footprint (datasets, artifacts, metadata, metrics, and logs).

**Non-goals**: Deep dive into individual components.

**Inspired by**: https://github.com/GlebBerjoskin/mlops-assignment

## Problem framing: Making better coding agents

Imagine: you are an MLOps engineer in a team that strives to make better coding agents. Be it Claude Code / Codex / Cursor / OpenCode, you name it.

Quality of an agent depends on:
1. Harness: agentic loop, tools, prompts, skills, subagents, etc.
2. LLM that powers the agent

Your team wants to experiment with both harness and LLM. I.e.,: tune prompts, add tools, fine-tune the model, etc.

Agent quality is measured on [SWE-bench](TODO)-like tasks: agent is asked to solve a real-life GitHub issue in a Docker container, and real-life unit tests are used to evaluate the agent-generated solution.

Typical experiments look like:
1. tweak harness -> run agent -> evaluate
2. fine-tune a model -> deploy the model -> run agent -> evaluate

The researchers managed to implement ad-hoc scripts to run the experiments above on some VM. One can SSH to a VM, run the scripts in order by hand. One experiment at a time. No structure, no history, no reproducibility.

Now they need your help to enable experimentation **at scale**. At scale = a team of researchers, dozen of experiments in parallel, distributed across multiple machines.

Turn researcher's ad-hoc scripts into  **automated**, **durable**, and **scalable** **pipelines**. These pipelines connect the blocks in the right order, take care of the queue, resources, restarts, artifacts storage, etc. These pipelines enable a team of researchers to come up with a bunch of experiments, express them as simple configs, schedule them, and just come to see the results next morning, quitely relying on the system.

## Task

Implement production-grade pipelines to support experiments with harness and model fine-tuning. Then, run experiments with the help of these pipelines.

Pielines:
1. `evaluate-agent`. Agent evaluation on a set of SWE-bench-like tasks.
2. `train-model`. SFT-based LLM fine-tuning on a dataset of trajectories.
3. `train-model-and-evaluate-agent`. End-to-end pipeline a combination of `train-model` and `evaluate-agent`.

Use the pipelines above to run the following experiments: **TODO**
1. Harness: change prompt (3 versions)
2. Model: change temperature
3. Fine-tuning: 10/100/1000 trajectories from SWE-rebench-openhands-trajectories, evaluate.

**Inputs**:
1. Agent = `mini-swe-agent`, a simple research-friendly agent.
2. Agent evaluation = `swe-bench`, standard implementation of SWE-bench evaluation.

**Stack**:
1. **Airflow** as a pipeline engine.
2. Managed code sandboxes via API. For instance: Nebius Token Factory Sandboxes / Daytona / Modal / E2B.
3. Managed service for LLM inference via API. For instance: Nebius Token Factory Inference / AWS BedRock / Together AI.
4. Managed service for LLM tine-tuning via API. For instance: Nebius Token Factory Fine-Tuning / AWS BedRock / Together AI.

For simplicity, managed services are used where possible, while in practice they could be self-hosted, e.g. vLLM on Kubernets for inference.

### Sub-task 1: `evaluate-agent`

### Sub-task 2: `train-model`
