# MVP Handoff

## What You Are Receiving

You are receiving a runnable experimental system under `phase1_runtime`.

Current stable surfaces:
- `/workspace`
- `/prototype`
- `/ops`
- `/api/phase1`

Current major backend capabilities:
- document parser MVP
- hybrid retrieval
- runtime execution
- task context + rule binding
- rule factory lifecycle
- rule-to-skill preview generation


## Important Reality Check

At the current code baseline:
- the main workspace / retrieval / runtime / factory chains are usable
- the **full** test suite is currently green

Latest verified result:

```bash
python3 -m unittest discover -s phase1_runtime/tests
```

- `Ran 138 tests`
- `OK`

This is still an experimental platform, not a production handoff, but the current code baseline is clean.


## Directory Guide

Read these files first:
- `phase1_runtime/SYSTEM_OVERVIEW.md`
- `phase1_runtime/README.md`
- `phase1_runtime/API_CONTRACT.md`
- `CURRENT_PROJECT_STATUS.md`

Most important modules:
- `phase1_runtime/product/workspace_flow.py`
- `phase1_runtime/runtime_core/runtime.py`
- `phase1_runtime/retrieval/hybrid_retrieval.py`
- `phase1_runtime/factory/rule_factory_service.py`
- `phase1_runtime/skills/rule_to_skill_creator.py`


## Quick Start

### 1. Start HTTP service

```bash
python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8013
```

### 2. Open the main workspace

Open:
- `http://127.0.0.1:8013/workspace`

This is the current primary entrypoint.

### 3. Open the prototype page

Open:
- `http://127.0.0.1:8013/prototype`

Use this to demonstrate system capability and rule composition flows.

### 4. Open the ops page

Open:
- `http://127.0.0.1:8013/ops`

Use this to inspect:
- workspace runs
- feedback
- drafts
- reviews
- published versions


## Recommended Smoke Checks

### Workspace smoke

Run one demo case:

```bash
python3 -m phase1_runtime.tools.demo_case_runner demo_cases/workspace/fund_docx_direct_warn --check-expected
```

### API smoke

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"retrieval.embedding_backend.status"}'
python3 -m phase1_runtime.api.api_service --payload '{"action":"demo.workspace_case.list"}'
```

### Rule Factory smoke

Use `/ops`, or inspect:

```bash
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.draft.list"}'
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.review.list"}'
python3 -m phase1_runtime.api.api_service --payload '{"action":"factory.rule_version.list"}'
```


## Runtime Model To Keep In Mind

Current execution layers are:

1. document parsing / chunking
2. hybrid retrieval
3. task context
4. rule binding
5. runtime route + execution
6. trace + feedback
7. draft / review / publish

There is also a parallel preview chain:

`rule + task_context + rule_binding -> runtime_skill_spec_preview`

Important:
- this preview chain does **not** execute the runtime yet
- runtime is still driven by the existing execution path


## What Not To Assume

Do not assume:
- all tests are green
- parser is a final semantic extractor
- rule-to-skill preview already drives execution
- generation/mock-data paths are aligned with the latest schema


## Recommended Next Owner Tasks

First wave:
- confirm `/workspace`, `/prototype`, `/ops` all load locally
- inspect one successful workspace run end to end
- inspect one draft / review / published version in `/ops`
- confirm the current embedding backend status API

Second wave:
- repair generation/mock-data paths
- align stale docs with the codebase
- decide whether the next milestone is
  - execution-layer migration to skill-driven runtime
  - or stabilization of the current rule runtime first
