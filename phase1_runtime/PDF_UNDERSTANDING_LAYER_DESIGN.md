# PDF Understanding Layer Design

## 1. Problem Statement

Current `/workspace` PDF handling is still a text-extraction pipeline:

- first try local `pdfplumber`
- if local extraction returns non-empty text, accept it
- only fall back to plugin/Kimi when local extraction returns no usable text
- convert extracted text lines into `line_items -> DocumentChunk[]`
- run signal detection, retrieval, rule binding, and runtime on top of those chunks

This works for simple PDFs, but it is insufficient for layout-heavy financial documents such as:

- equity research reports
- contracts with tables and numbered clauses
- scanned notices with headers/footers
- multi-column reports with charts and disclaimers

The core issue is not “whether Kimi is used”.
The core issue is that neither the local path nor the current plugin path produces the document representation the downstream system actually needs.

The target of this design is therefore:

**replace `PDF -> text` with `PDF -> layout-aware, evidence-ready document package`**


## 2. Design Goal

The PDF layer must produce a representation that downstream components can reliably consume for:

- scenario inference
- retrieval
- `TaskContext`
- `RuleBinding`
- LLM extraction steps
- evidence citation
- trace and review

This means the PDF layer must preserve:

- reading order
- semantic blocks
- table structure
- stable evidence identifiers
- section-level cues
- noise vs content separation


## 3. What “Success” Looks Like

For a PDF such as the equity research report `H3_AP202604031821011697_1.pdf`, the reader should preserve:

- document family: `equity_research_report`
- title block
- company name and ticker
- section blocks such as:
  - `公司简评`
  - `投资要点`
  - `评级`
  - `风险提示`
  - `估值`
  - `免责声明`
- table blocks such as:
  - valuation tables
  - indicator tables
- citation-sized evidence units such as:
  - `增持（维持）`
  - target-price sentences
  - valuation-method sentences
  - downside-risk sentences
- noise blocks such as:
  - page headers
  - footers
  - table of contents
  - legal disclaimer
  - contact info

The downstream system should then be able to:

- infer `equity_research`
- ground `analyst_rating`
- ground `key_risks`
- attempt `target_price` extraction only from valuation-related blocks
- avoid treating disclaimers and page furniture as first-class evidence


## 4. Downstream Contract Requirements

Current downstream code needs:

- stable `EvidenceRef(doc_id, locator, snippet_id, text)`
- coherent `DocumentChunk[]`
- usable `document_types`
- `fact_sheet` grounding for required rule inputs
- `evidence_packets`
- retrieval-facing text and key signals

Relevant current contracts:

- `DocumentChunk`: [document_chunk.py](/home/u2023312337/self_learning/phase1_runtime/document_chunk.py)
- `EvidenceRef`, `QuestionStruct`, `StepContract`: [schema.py](/home/u2023312337/self_learning/phase1_runtime/schema.py)
- parser contract: [document_parser_contract.py](/home/u2023312337/self_learning/phase1_runtime/document_parser_contract.py)
- `/workspace` ingestion and downstream usage: [workspace_flow.py](/home/u2023312337/self_learning/phase1_runtime/workspace_flow.py), [workspace_parser.py](/home/u2023312337/self_learning/phase1_runtime/workspace_parser.py)

Therefore, the new PDF layer does **not** need to fully populate final business facts on day 1.
But it **does** need to emit a richer document package from which:

- signal grounding
- retrieval
- evidence citation
- later value extraction

can all work reliably.


## 5. Target Output Schema

The PDF layer should produce a `PDFDocumentPackage`.

### 5.1 Top-level object

```json
{
  "doc_id": "upload_doc_001",
  "title": "工商银行（601398）：息差压力缓解，资产质量稳中有进",
  "source_type": "uploaded_pdf",
  "parse_status": "parsed_pdf_structured",
  "document_family": "equity_research_report",
  "page_count": 11,
  "quality_score": 0.87,
  "quality_flags": [],
  "blocks": [],
  "tables": [],
  "evidence_units": [],
  "semantic_signals": [],
  "noise_blocks": [],
  "metadata": {}
}
```

### 5.2 `blocks[]`

Each block is the minimum coherent semantic region.

```json
{
  "block_id": "block_001",
  "block_type": "title",
  "section": "cover",
  "text": "工商银行（601398）：息差压力缓解，资产质量稳中有进",
  "page": 1,
  "reading_order": 7,
  "bbox": [x1, y1, x2, y2],
  "source": "local_layout"
}
```

Supported `block_type` values:

- `title`
- `heading`
- `subheading`
- `paragraph`
- `bullet_list`
- `table_caption`
- `table_row`
- `disclaimer`
- `header`
- `footer`
- `toc`

### 5.3 `tables[]`

For tables that matter downstream, preserve rows and cells instead of flattening them into paragraphs.

```json
{
  "table_id": "table_001",
  "page": 10,
  "title": "盈利预测与估值简表",
  "columns": ["指标", "2025A", "2026E", "2027E", "2028E"],
  "rows": [
    ["PB", "0.66", "0.63", "0.59", "0.56"]
  ],
  "bbox": [x1, y1, x2, y2]
}
```

### 5.4 `evidence_units[]`

These are the citation-sized spans the rest of the system should use.

```json
{
  "snippet_id": "snippet_rating_001",
  "doc_id": "upload_doc_001",
  "block_id": "block_014",
  "text": "增持（维持）",
  "locator": {
    "page": 1,
    "reading_order": 8,
    "bbox": [x1, y1, x2, y2]
  },
  "evidence_type": "rating_candidate"
}
```

### 5.5 `semantic_signals[]`

These are parser-level cues for retrieval and grounding.

```json
{
  "signal_type": "rating_candidate",
  "value": "增持",
  "confidence": 0.96,
  "evidence_snippet_ids": ["snippet_rating_001"]
}
```

Suggested signal types:

- `document_family_candidate`
- `company_name_candidate`
- `ticker_candidate`
- `rating_candidate`
- `target_price_candidate`
- `valuation_method_candidate`
- `risk_section`
- `valuation_section`
- `summary_section`
- `disclaimer_section`


## 6. Output Adapters For Current System

The new PDF layer should not force immediate downstream rewrites.
Instead, add adapters that map `PDFDocumentPackage` into the current `/workspace` outputs.

### 6.1 `document_packet_preview`

Derived from:

- `doc_id`
- `title`
- `document_family` or fallback `doc_type`
- `source_type`
- `parse_status`
- `char_count`
- `line_count`
- `warnings`

### 6.2 `document_chunks`

Derived from semantic `blocks[]`, not raw PDF lines.

Mapping suggestion:

- `title`, `heading`, `subheading` -> `heading`
- `paragraph`, `bullet_list` -> `paragraph`
- `table_row` -> `table_row`
- legal clauses in contract PDFs -> `clause`

This preserves compatibility with `DocumentChunk`.

### 6.3 `evidence_packets`

Derived from `evidence_units[]`.

```json
{
  "doc_id": "...",
  "snippet_id": "...",
  "text": "...",
  "locator": {...},
  "chunk_type": "paragraph"
}
```

### 6.4 `fact_sheet`

Still signal-based in phase 1, but grounded from semantic signals and blocks rather than raw text-only line matching.

Example:

- `analyst_rating`: grounded if any `rating_candidate` signal exists
- `target_price`: grounded only if any `target_price_candidate` signal exists
- `key_risks`: grounded if `risk_section` or `risk_candidate` signal exists

This is stricter and more semantically meaningful than current substring matching.

### 6.5 `retrieval_fact_keys`

Derived from grounded fact ids exactly as today, but now grounded by semantic document understanding instead of naive text search.


## 7. Pipeline Architecture

The new PDF layer should be a staged pipeline.

### Stage A. File Inspection

Input:

- file bytes
- page count
- file size
- scan/text heuristic

Output:

- `inspection`
- `page_count`
- `is_scanned`
- `is_layout_heavy`
- `needs_external_recovery`

### Stage B. Primitive Extraction

Use local tools first to gather primitives:

- text lines
- words / spans with bbox
- tables
- page images if needed

Local candidates:

- `pdfplumber`
- `pypdf`
- `PyMuPDF`

Do **not** yet decide success solely on “non-empty text”.

### Stage C. Layout Reconstruction

Construct page-level regions:

- title areas
- headers / footers
- body columns
- table regions
- captions
- repeated boilerplate

This stage should assign:

- `reading_order`
- `bbox`
- `region_type`

### Stage D. Semantic Reconstruction

Merge primitive lines into semantic blocks:

- titles
- headings
- paragraphs
- bullet groups
- table rows
- disclaimers

Infer section labels such as:

- `投资要点`
- `评级`
- `估值`
- `风险提示`

### Stage E. Signal And Evidence Packaging

Generate:

- `semantic_signals[]`
- `evidence_units[]`
- noise suppression labels

This is where document-family and field-level candidates should be computed.

### Stage F. Adapter Layer

Convert `PDFDocumentPackage` into current `/workspace` payloads:

- `document_packet_preview`
- `document_chunks`
- `evidence_packets`
- `fact_sheet`
- `retrieval_fact_keys`


## 8. Local Parser And Kimi/Plugin Combination Strategy

The right strategy is **not** “always local” and **not** “always Kimi”.

It should be:

### 8.1 Local-first for primitives

Use local parsing to obtain:

- page count
- text spans
- bbox-aware words
- candidate tables
- repeated header/footer regions

Reasons:

- deterministic
- cheap
- debuggable
- no network dependency

### 8.2 Quality gate after local parse

Before accepting local results, score extraction quality.

Suggested heuristics:

- singleton-character ratio
- abnormal line-break ratio
- repeated page furniture ratio
- percentage of text assigned to body blocks
- table continuity score
- heading/body alternation sanity
- key-signal recoverability

If quality is high, use local result directly.

If quality is low, escalate.

### 8.3 Kimi/plugin for recovery, not just full-text fallback

Use Kimi/plugin when local quality is low, or when:

- scanned/OCR-heavy PDF
- strong multi-column disorder
- tables cannot be reconstructed locally
- semantic section recovery is weak

But the plugin should be asked for **structured recovery tasks**, not just “return full text”.

Examples:

- recover page reading order
- identify section titles
- extract table headers and rows
- label blocks as title/heading/paragraph/table/disclaimer
- return field candidates with evidence spans

That means plugin output should eventually target the same `PDFDocumentPackage` schema.

### 8.4 Fusion

Final output should fuse:

- local layout primitives
- local tables
- Kimi semantic labeling / recovery when needed

The Kimi path should enrich or repair local parsing, not replace all structure with plain text.


## 9. Quality Gate Design

Replace the current success condition:

- `non-empty extracted text == success`

with:

- `document understanding quality >= threshold == success`

Suggested fields:

```json
{
  "quality_score": 0.61,
  "quality_flags": [
    "high_singleton_line_ratio",
    "table_flattening_detected",
    "repeated_footer_noise",
    "reading_order_instability"
  ]
}
```

Suggested route:

- `quality_score >= 0.8` -> accept local package
- `0.5 <= score < 0.8` -> local package + semantic recovery
- `< 0.5` -> escalate to plugin/Kimi recovery or ask for human review


## 10. Minimal Initial Rollout

A practical rollout should be phased.

### Phase 1. Introduce `PDFDocumentPackage`

Without changing downstream contracts yet:

- build structured package
- keep existing adapter outputs
- log quality score and quality flags

### Phase 2. Replace line-based chunking

Switch `document_chunks` generation from raw lines to semantic blocks.

This alone should improve:

- retrieval
- signal grounding
- LLM extraction

### Phase 3. Replace text-only signal detection

Ground `fact_sheet` from:

- semantic signals
- labeled sections
- evidence units

instead of raw substring matching over flattened text.

### Phase 4. Add plugin-based semantic recovery

Keep local primitives, add Kimi recovery only when quality is low.

### Phase 5. Value-level extraction

Only after the above is stable, move selected facts from key-level grounding to value-level extraction.


## 11. Concrete Changes To Current Code

### 11.1 New module boundary

Add a new module, for example:

- `phase1_runtime/pdf_understanding.py`

Responsibilities:

- inspect PDF
- extract primitives
- reconstruct semantic blocks
- compute quality
- emit `PDFDocumentPackage`

### 11.2 Keep `document_parser_mvp.py` as adapter/orchestrator

`document_parser_mvp.py` should:

- delegate PDFs to the new understanding layer
- adapt structured package into current `parsed_materials`
- stop making “non-empty text” the success criterion

### 11.3 Update `workspace_parser.py`

Use semantic blocks/evidence units rather than raw lines for:

- `document_chunks`
- `evidence_packets`
- signal grounding

### 11.4 Keep retrieval/runtime contracts stable at first

Continue emitting:

- `document_chunks`
- `evidence_packets`
- `fact_sheet`

but generate them from the richer PDF package.


## 12. Acceptance Criteria

The PDF understanding layer is good enough when:

- a complex research PDF is classified into the right document family
- section boundaries are mostly stable
- disclaimers and page furniture are marked as noise
- rule-required keys are grounded from semantic evidence, not just random substring hits
- evidence units are stable and reusable across retrieval, extraction, trace, and review
- `/workspace` no longer treats “text exists” as equivalent to “PDF read correctly”


## 13. Non-Goals

This design does **not** require:

- perfect OCR for every scanned document in phase 1
- full value-level semantic extraction before routing
- replacing runtime with a skill-driven executor

It focuses on the one missing layer that the current system lacks:

**document understanding between raw PDF bytes and downstream reasoning.**
