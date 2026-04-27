# Data Structures

This file defines the business-facing data objects used by the thicker Phase 1 prototype.

## Core Objects

### `QuestionStruct`
- Purpose: normalized user question for retrieval and runtime.
- Defined in: `phase1_runtime/schema.py`
- Key fields: `question_text`, `question_types`, `intents`, `document_types`, `extracted_inputs`

### `Rule`
- Purpose: published direct-match rule asset.
- Defined in: `phase1_runtime/schema.py`
- Key fields: `rule_id`, `trigger`, `applicability`, `inputs`, `steps`, `outputs`, `validators`, `provenance`

### `DocumentBundleRecord`
- Purpose: one scenario's document package, facts, and evidence snippets.
- Defined in: `phase1_runtime/data_models.py`
- Key fields: `bundle_id`, `scenario_id`, `documents`, `facts`, `evidence_refs`, `created_at`, `notes`

### `CaseRecord`
- Purpose: reviewed learning sample derived from one question and its expected answer.
- Defined in: `phase1_runtime/data_models.py`
- Key fields: `case_id`, `question`, `document_bundle_id`, `gold_answer`, `solution_steps`, `linked_rule_ids`, `review_status`

### `ReviewTask`
- Purpose: simulated human review object for a case or rule version.
- Defined in: `phase1_runtime/data_models.py`
- Key fields: `review_task_id`, `target_type`, `target_id`, `status`, `assignee`, `checklist`, `comments`

### `ExecutionTraceRecord`
- Purpose: persisted runtime trace for one direct-match execution.
- Defined in: `phase1_runtime/data_models.py`
- Key fields: `trace_id`, `route_decision`, `status`, `retrieval`, `step_contracts`, `step_results`, `validator_results`, `final_result`

### `SimulationDataset`
- Purpose: packaged scenario dataset combining question, docs, case, rules, review task, and execution trace.
- Defined in: `phase1_runtime/data_models.py`
- Output files: `simulation_dataset.json`, `question_struct.json`, `document_bundle.json`, `case_record.json`, `rule_pool.json`, `review_task.json`, `execution_trace.json`, `dataset_manifest.json`

## Formal JSON Schemas

Generate JSON Schema files with:

```bash
python3 -m phase1_runtime.contracts.formal_schemas
```

Default output directory:

```text
phase1_runtime/json_schemas
```

## Mock Data Generation

Generate one complete dataset with:

```bash
python3 -m phase1_runtime.tools.mock_data single
```

Generate a batch of simulated datasets with:

```bash
python3 -m phase1_runtime.tools.mock_data batch --count 10
```

Default batch output directory:

```text
phase1_runtime/sim_data/batch_demo_001
```
