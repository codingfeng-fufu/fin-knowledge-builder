# API Contract

## Scope

This document describes the current contract for:
- function-style API: `handle_request(payload)`
- HTTP API: `POST /api/phase1`
- HTTP health check: `GET /health`

The contract reflects the code as it exists now.
It is not a future-state design document.

## Function Contract

Entry point:
- `phase1_runtime.api.handle_request(payload)`

Input:
- `payload` must be a JSON-like object

Output envelope:
- `ok: boolean`
- `action: string | null`
- `request_id: string | null`
- `timestamp: string`
- `data: object | null`
- `error: object | null`

Error object shape:
- `code: string`
- `message: string`
- `details: object`

## HTTP Contract

### `GET /ops`

Purpose:
- serve the minimal operations console for workspace runs, feedback, drafts, reviews, and published versions


### `GET /health`

Purpose:
- service health check

Success response:
- HTTP `200`
- JSON body with `ok = true`

Example:

```json
{
  "ok": true,
  "service": "phase1_runtime_http",
  "status": "healthy",
  "path": "/health"
}
```

### `POST /api/phase1`

Purpose:
- execute a function-style API action through HTTP

Request requirements:
- `Content-Type: application/json`
- JSON object body

Success:
- HTTP `200`
- response envelope with `ok = true`

Typical client error cases:
- malformed JSON
- unsupported action
- invalid dataset
- missing required request fields

Typical client error status:
- HTTP `400`

Not found case:
- HTTP `404`

## Common Payload Fields

These fields may appear depending on action:
- `action: string`
- `request_id: string`
- `dataset_dir: string`
- `dataset_id: string`
- `scenario_id: string`
- `question_text: string`
- `materials: object[]`
  item fields may include `name`, `content`, `content_base64`, `media_type`, `size`
- `run_id: string`
- `case_id: string`
- `draft_id: string`
- `review_task_id: string`
- `rule_version_id: string`
- `trace_id: string`
- `feedback_id: string`
- `feedback_type: string`
- `route_decision: string`
- `rule_ids: string[]`
- `trace_dir: string`
- `db_path: string`
- `metadata: object`
- `source: string`
- `assignee: string`
- `note: string`
- `reason: string`

Defaults:
- `dataset_dir` defaults to the fund demo dataset
- `trace_dir` defaults to `phase1_runtime/consumption_traces`
- `db_path` defaults to `phase1_runtime/state/registry.db`
- `source` defaults to `manual`

## Non-Registry Actions

### `dataset.validate`

Purpose:
- validate one dataset directory against local JSON Schemas

### `dataset.import`

Purpose:
- validate and import one dataset directory, then return a summary

### `dataset.summary`

Purpose:
- import dataset and return a richer summary than `dataset.import`

### `dataset.replay`

Purpose:
- summarize stored execution trace from imported dataset

### `dataset.rerun`

Purpose:
- rerun runtime from imported dataset assets and compare with stored trace

Behavior:
- when `db_path` points to a rule-factory database, published rule versions are merged into the runtime rule pool before rerun

### `workflow.full`

Purpose:
- run the full sequence in one call

Sequence:
- validate dataset
- import dataset
- summarize import
- replay stored trace
- rerun compare

Behavior:
- the rerun stage uses published factory rules from `db_path` when available
- when composition succeeds, the response may include `composition_pattern` and `source_rule_ids` through the rerun summary

## Product Actions

### `product.scenario.list`

Purpose:
- list workspace reference scenarios
- return the current workspace entry metadata

### `product.solve.preview`

Purpose:
- run one scenario-backed preview without uploaded materials

Optional fields:
- `scenario_id`
- `question_text`
- `work_dir`
- `db_path`

### `product.workspace.contract`

Purpose:
- return the current `/workspace` main-entry contract
- expose the document parser TODO boundary and target output contract

### `product.workspace.solve`

Purpose:
- use `/workspace` as the expert workbench entry
- accept question text plus text or binary document uploads
- parse uploaded materials into document preview, question packet preview, signal-based `fact_sheet`, and `evidence_packets` before runtime execution
- automatically persist a workspace run, create a workspace case, and record/promote feedback when the route calls for it
- query historical `workspace_run` records and return `similar_cases`
- only reuse a `shortcut_case` when the current request has no uploaded materials and a high-confidence historical case is available
- when exploration is triggered, include `exploration_runtime` output with `exploration_trace_id`, `case_draft`, `candidate_rule_drafts`, `evidence_pattern_suggestions`, and `validator_pattern_suggestions`
- return the current parser previews together with the runtime suggestion
- return `orchestration_view` with planner/context/template/skill/validator summaries
- return `embedding_backend`
- return `task_context`
- return `rule_bindings`
- return `runtime_skill_spec_preview`
- return `asset_pipeline`

### `retrieval.embedding_backend.status`

Purpose:
- return the current active retrieval embedding backend
- return all available embedding backends and availability status

### `demo.workspace_case.list`

Purpose:
- list built-in workspace demo cases
- return the default demo case used by `/workspace`

### `demo.workspace_case.get`

Purpose:
- load one built-in workspace demo case
- return question text, materials, and expected summary

Required fields:
- `case_ref`

Required fields:
- `question_text`

Optional fields:
- `scenario_id`
- `materials`
- `work_dir`
- `db_path`

## Registry Actions

### `registry.dataset.register`

Purpose:
- register one validated dataset into SQLite

Required fields:
- `action`
- `dataset_dir`

Optional fields:
- `db_path`
- `source`
- `metadata`

### `registry.dataset.list`

Purpose:
- list all dataset registry rows

### `registry.dataset.get`

Purpose:
- fetch one dataset registry row

Required fields:
- `dataset_id`

### `registry.workflow.run`

Purpose:
- submit an asynchronous workflow job for a registered dataset

Required fields:
- `dataset_id`

Behavior:
- inserts a workflow run row with `status = queued`
- spawns a background worker process
- worker transitions run to `running`, then `completed` or `failed`

Immediate response data:
- `run_id`
- `dataset_id`
- `status = queued`
- `started_at`

### `registry.workflow.run_sync`

Purpose:
- execute the same registered workflow synchronously

This exists mainly for internal/debug use.
It is not the normal product path.

### `registry.workflow.list`

Purpose:
- list workflow run rows from SQLite

### `registry.workflow.get`

Purpose:
- fetch one workflow run row

Required fields:
- `run_id`

Response data includes:
- `run_id`
- `dataset_id`
- `request_id`
- `status`
- `started_at`
- `finished_at`
- `result`
- `error`
- `rerun_trace_path`
- `final_decision`

## Factory Actions

### `factory.case.ingest`

Purpose:
- import one validated dataset case into the rule-factory case store

Required fields:
- `dataset_dir`

Optional fields:
- `db_path`
- `source`

### `factory.case.list`

Purpose:
- list ingested factory cases

### `factory.case.get`

Purpose:
- fetch one factory case

Required fields:
- `case_id`

### `factory.draft.generate`

Purpose:
- generate one candidate rule draft from an ingested case

Required fields:
- `case_id`

### `factory.draft.list`
- list candidate rule drafts

### `factory.draft.get`
- fetch one candidate rule draft

Required fields:
- `draft_id`

### `factory.review.create`

Purpose:
- create a review task and move the draft to `under_review`

Required fields:
- `draft_id`

Optional fields:
- `assignee`

### `factory.review.list`
- list review tasks

### `factory.review.get`
- fetch one review task

Required fields:
- `review_task_id`

### `factory.review.approve`

Purpose:
- approve a review, publish a rule version, and create the source case link

Required fields:
- `review_task_id`

Optional fields:
- `note`

### `factory.review.reject`

Purpose:
- reject a review and mark the draft as rejected

Required fields:
- `review_task_id`

Optional fields:
- `note`

### `factory.rule_version.list`
- list published rule versions

### `factory.rule_version.get`
- fetch one rule version

Required fields:
- `rule_version_id`

### `factory.rule_version.rollback`

Purpose:
- mark a published rule version as rolled back and store a rollback record

Required fields:
- `rule_version_id`
- `reason`

### `factory.case_rule_link.list`
- list case-to-rule provenance links

### `factory.rollback.list`
- list rollback records

### `factory.workspace_run.list`

Purpose:
- list persisted workspace run records that have entered the Rule Factory side of the pipeline

### `factory.workspace_run.get`

Purpose:
- fetch one persisted workspace run record

Required fields:
- `workspace_run_id`

### `factory.feedback.promote_to_draft`

Purpose:
- classify one persisted feedback row and materialize a candidate asset draft

Required fields:
- `feedback_id`

Optional fields:
- `db_path`

### `factory.retrieval_asset_view`

Purpose:
- build the retrieval-facing asset view from current published asset versions
- return the asset-level payload that direct match and rule composition consume

Optional fields:
- `db_path`

## Status Model For Workflow Runs

Current statuses:
- `queued`
- `running`
- `completed`
- `failed`

Expected client behavior:
1. call `registry.workflow.run`
2. receive `run_id`
3. poll `registry.workflow.get`
4. stop polling when status becomes `completed` or `failed`

## Error Codes

Current error codes used by the API envelope:
- `bad_request`
- `unsupported_action`
- `invalid_dataset`
- `not_found`
- `internal_error`

## Example Payloads

### Register Fund Dataset

```json
{
  "action": "registry.dataset.register",
  "dataset_dir": "phase1_runtime/sim_data/demo_set_001"
}
```

### Register Credit Dataset

```json
{
  "action": "registry.dataset.register",
  "dataset_dir": "phase1_runtime/sim_data/demo_set_credit_001"
}
```

### Submit Async Workflow Job

```json
{
  "action": "registry.workflow.run",
  "dataset_id": "demo_set_001",
  "request_id": "job_001"
}
```

### Poll Workflow Job

```json
{
  "action": "registry.workflow.get",
  "run_id": "run_xxx"
}
```

### Full Workflow On Credit Case

```json
{
  "action": "workflow.full",
  "dataset_dir": "phase1_runtime/sim_data/demo_set_credit_001",
  "request_id": "req_credit_001"
}
```

## Stability Notes

Stable enough for:
- demo
- integration testing
- internal tools
- service wrapping

Not yet stable enough for:
- public API exposure
- backwards-compatibility guarantees
- multi-user production workloads

## Feedback Actions

### `feedback.record`

Purpose:
- persist one structured feedback record into the rule-factory store

Required fields:
- `trace_id`
- `route_decision`
- `feedback_type`

Optional fields:
- `case_id`
- `rule_ids`
- `payload`
- `db_path`

### `feedback.list`

Purpose:
- list persisted feedback rows

### `feedback.get`

Purpose:
- fetch one persisted feedback row

Required fields:
- `feedback_id`
