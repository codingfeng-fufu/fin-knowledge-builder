const path = require('path');
const PptxGenJS = require('../../one_pager_slide/node_modules/pptxgenjs');
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require('./pptxgenjs_helpers/layout');

const pptx = new PptxGenJS();
pptx.author = 'OpenAI Codex';
pptx.company = 'OpenAI';
pptx.subject = 'Phase 1 Runtime MVP Demo';
pptx.title = 'Rule-Driven QA MVP Demo';
pptx.theme = {
  headFontFace: 'DejaVu Sans',
  bodyFontFace: 'DejaVu Sans',
  lang: 'en-US',
};
pptx.defineLayout({ name: 'WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'WIDE';
pptx.layout = 'WIDE';

const C = {
  bg: 'F7F1E8',
  paper: 'FFFDF8',
  ink: '1E1C18',
  muted: '6D655A',
  line: 'D9D1C5',
  navy: '18344A',
  rust: '9F4A22',
  olive: '50663D',
  gold: 'B4883C',
  blueFade: 'EAF0F6',
  warmFade: 'FAEFE7',
  greenFade: 'EDF5EA',
  white: 'FFFFFF',
};

const FONT = 'DejaVu Sans';
const MONO = 'DejaVu Sans Mono';
const slides = [];

function makeSlide(title, kicker, bg = C.bg) {
  const slide = pptx.addSlide();
  slides.push(slide);
  slide.background = { color: bg };
  slide.addText(kicker, {
    x: 0.62,
    y: 0.36,
    w: 3.8,
    h: 0.18,
    fontFace: FONT,
    fontSize: 11,
    bold: true,
    color: C.rust,
    margin: 0,
    charSpace: 1.5,
  });
  slide.addText(title, {
    x: 0.62,
    y: 0.6,
    w: 8.4,
    h: 0.42,
    fontFace: FONT,
    fontSize: 23,
    bold: true,
    color: C.ink,
    margin: 0,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.62,
    y: 1.1,
    w: 12.1,
    h: 0,
    line: { color: C.line, pt: 1.2 },
  });
  return slide;
}

function panel(slide, x, y, w, h, fill = C.paper, line = C.line) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: line, pt: 1 },
  });
}

function pill(slide, x, y, w, text, fill, color = C.white) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.28,
    fill: { color: fill },
    line: { color: fill, transparency: 100 },
  });
  slide.addText(text, {
    x,
    y: y + 0.02,
    w,
    h: 0.18,
    fontFace: FONT,
    fontSize: 10,
    bold: true,
    color,
    align: 'center',
    margin: 0,
  });
}

function body(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x,
    y,
    w,
    h,
    fontFace: opts.fontFace || FONT,
    fontSize: opts.fontSize || 11,
    color: opts.color || C.ink,
    bold: opts.bold || false,
    italic: opts.italic || false,
    align: opts.align || 'left',
    valign: opts.valign || 'top',
    margin: opts.margin == null ? 0 : opts.margin,
    breakLine: opts.breakLine || false,
    fit: 'shrink',
  });
}

function bullets(slide, items, x, y, w, color = C.ink, bulletColor = C.navy, lineGap = 0.36) {
  items.forEach((item, index) => {
    slide.addShape(pptx.ShapeType.ellipse, {
      x,
      y: y + index * lineGap + 0.06,
      w: 0.08,
      h: 0.08,
      fill: { color: bulletColor },
      line: { color: bulletColor, transparency: 100 },
    });
    body(slide, item, x + 0.16, y + index * lineGap, w - 0.16, 0.24, {
      fontSize: 11,
      color,
    });
  });
}

function metric(slide, x, y, w, title, value, fill, accent) {
  panel(slide, x, y, w, 1.02, fill, accent);
  body(slide, title, x + 0.16, y + 0.14, w - 0.32, 0.16, {
    fontSize: 10,
    color: C.muted,
  });
  body(slide, value, x + 0.16, y + 0.4, w - 0.32, 0.3, {
    fontSize: 19,
    bold: true,
    color: accent,
  });
}

function codeBlock(slide, code, x, y, w, h) {
  panel(slide, x, y, w, h, 'F2F4F7', C.line);
  body(slide, code, x + 0.18, y + 0.16, w - 0.36, h - 0.28, {
    fontFace: MONO,
    fontSize: 9.5,
    color: C.navy,
    margin: 0,
  });
}

function finalizeSlides() {
  slides.forEach((slide) => {
    warnIfSlideHasOverlaps(slide, pptx);
    warnIfSlideElementsOutOfBounds(slide, pptx);
  });
}

// Slide 1
{
  const slide = pptx.addSlide();
  slides.push(slide);
  slide.background = { color: C.bg };
  slide.addText('Rule-Driven QA MVP', {
    x: 0.68,
    y: 0.54,
    w: 6.6,
    h: 0.5,
    fontFace: FONT,
    fontSize: 28,
    bold: true,
    color: C.ink,
    margin: 0,
  });
  slide.addText('From typed rules to validated datasets, async jobs, and a browser console', {
    x: 0.68,
    y: 1.06,
    w: 8.6,
    h: 0.22,
    fontFace: FONT,
    fontSize: 12,
    color: C.muted,
    margin: 0,
  });
  slide.addText('Prototype status: two real demo cases, one shared system skeleton, end-to-end path verified.', {
    x: 0.68,
    y: 1.34,
    w: 9.8,
    h: 0.18,
    fontFace: FONT,
    fontSize: 10.5,
    color: C.navy,
    italic: true,
    margin: 0,
  });

  metric(slide, 0.68, 1.88, 2.1, 'Validated Cases', '2', C.paper, C.rust);
  metric(slide, 2.98, 1.88, 2.1, 'JSON Schemas', '16', C.paper, C.navy);
  metric(slide, 5.28, 1.88, 2.1, 'Automated Tests', '29', C.paper, C.olive);
  metric(slide, 7.58, 1.88, 2.3, 'Registries', '2 SQLite tables', C.paper, C.gold);

  const stages = [
    ['Rule DSL', C.navy],
    ['Dataset', C.rust],
    ['Validation', C.gold],
    ['Import', C.olive],
    ['Workflow', C.navy],
    ['API', C.rust],
    ['Console', C.olive],
  ];
  let x = 0.82;
  stages.forEach(([label, fill], index) => {
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 3.36,
      w: 1.56,
      h: 0.72,
      fill: { color: fill },
      line: { color: fill, transparency: 100 },
    });
    body(slide, label, x, 3.58, 1.56, 0.16, {
      fontSize: 12,
      bold: true,
      color: fill === C.gold ? C.ink : C.white,
      align: 'center',
      valign: 'mid',
    });
    if (index < stages.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, {
        x: x + 1.61,
        y: 3.52,
        w: 0.18,
        h: 0.4,
        fill: { color: C.line },
        line: { color: C.line, transparency: 100 },
      });
    }
    x += 1.8;
  });

  panel(slide, 0.68, 4.54, 12.02, 1.86, C.paper, C.line);
  body(slide, 'What this deck covers', 0.9, 4.76, 3.1, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  bullets(slide, [
    'what was built',
    'the two validated business cases',
    'the current async workflow and registry model',
    'how to demo the system in five minutes',
  ], 0.9, 5.08, 3.7, C.ink, C.rust);

  codeBlock(slide, [
    'python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8011',
    'open http://127.0.0.1:8011/console',
  ].join('\n'), 7.1, 4.82, 5.12, 1.18);
}

// Slide 2
{
  const slide = makeSlide('System Map', 'ARCHITECTURE');
  const layers = [
    ['Rule Layer', 'schema.py, fixtures, rule JSON', C.navy],
    ['Runtime Layer', 'retrieval, compiler, executors, validators', C.rust],
    ['Data Layer', 'data models, JSON Schema, dataset validation', C.gold],
    ['Simulation Layer', 'fund case + credit case datasets', C.olive],
    ['Import/Consume', 'import, replay, rerun compare, workflow', C.navy],
    ['Service Layer', 'function API, HTTP API, browser console', C.rust],
    ['Registry Layer', 'SQLite datasets + workflow jobs + worker', C.olive],
  ];
  layers.forEach((layer, index) => {
    const y = 1.34 + index * 0.72;
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.78,
      y,
      w: 4.76,
      h: 0.54,
      fill: { color: layer[2] },
      line: { color: layer[2], transparency: 100 },
    });
    body(slide, layer[0], 0.96, y + 0.14, 1.06, 0.16, {
      fontSize: 13,
      bold: true,
      color: layer[2] === C.gold ? C.ink : C.white,
    });
    body(slide, layer[1], 2.18, y + 0.14, 2.96, 0.16, {
      fontSize: 10.5,
      color: layer[2] === C.gold ? C.ink : 'F4EFE8',
    });
  });

  panel(slide, 6.0, 1.34, 6.55, 2.18, C.paper, C.line);
  body(slide, 'Stable now', 6.24, 1.56, 2.4, 0.18, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  bullets(slide, [
    'two business cases use one shared runtime skeleton',
    'datasets are schema-guarded before import',
    'workflow jobs can be submitted, tracked, and replayed',
    'browser console already talks to the live HTTP API',
  ], 6.24, 1.9, 5.9, C.ink, C.olive, 0.34);

  panel(slide, 6.0, 3.74, 6.55, 2.26, C.paper, C.line);
  body(slide, 'Intentionally not built yet', 6.24, 3.96, 3.2, 0.18, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  bullets(slide, [
    'rule composition and exploration runtime',
    'multi-user auth and permissions',
    'real OCR/PDF parsing pipelines',
    'distributed queue and production deployment',
  ], 6.24, 4.3, 5.9, C.ink, C.rust, 0.34);
}

// Slide 3
{
  const slide = makeSlide('Two Validated Cases', 'BUSINESS CASES');
  panel(slide, 0.74, 1.34, 6.0, 4.86, C.paper, C.line);
  pill(slide, 0.94, 1.54, 1.9, 'CASE 01', C.rust);
  body(slide, 'Private Fund NAV Warning', 0.94, 1.94, 3.8, 0.24, {
    fontSize: 17,
    bold: true,
    color: C.navy,
  });
  body(slide, 'Question', 0.94, 2.34, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  body(slide, 'If NAV falls below the contractual threshold, does the manager need to issue a risk warning to investors?', 0.94, 2.56, 5.1, 0.52, { fontSize: 11 });
  body(slide, 'Evidence', 0.94, 3.26, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  bullets(slide, [
    'contract clause: warning is required below threshold',
    'NAV report: current unit NAV is 0.78',
  ], 0.94, 3.48, 4.9, C.ink, C.rust, 0.34);
  body(slide, 'Decision', 0.94, 4.4, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  body(slide, 'must_warn', 0.94, 4.64, 1.8, 0.22, { fontSize: 18, bold: true, color: C.rust });
  body(slide, 'Matched rule: private_fund.nav_risk_warning.v1', 0.94, 5.08, 4.6, 0.18, { fontSize: 10.5, color: C.navy });

  panel(slide, 6.92, 1.34, 5.66, 4.86, C.paper, C.line);
  pill(slide, 7.12, 1.54, 1.9, 'CASE 02', C.olive);
  body(slide, 'Credit Loan Extension Notice', 7.12, 1.94, 4.0, 0.24, {
    fontSize: 17,
    bold: true,
    color: C.navy,
  });
  body(slide, 'Question', 7.12, 2.34, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  body(slide, 'If the loan is within 30 days of maturity and the contract requires notice, should the lender notify the borrower now?', 7.12, 2.56, 4.8, 0.52, { fontSize: 11 });
  body(slide, 'Evidence', 7.12, 3.26, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  bullets(slide, [
    'notice clause: notify borrower within 30 days of maturity',
    'repayment schedule: 20 days remain before maturity',
  ], 7.12, 3.48, 4.5, C.ink, C.olive, 0.34);
  body(slide, 'Decision', 7.12, 4.4, 1.0, 0.16, { fontSize: 11, bold: true, color: C.muted });
  body(slide, 'must_notify', 7.12, 4.64, 2.0, 0.22, { fontSize: 18, bold: true, color: C.olive });
  body(slide, 'Matched rule: credit.loan_extension_notice.v1', 7.12, 5.08, 4.3, 0.18, { fontSize: 10.5, color: C.navy });
}

// Slide 4
{
  const slide = makeSlide('Dataset Package And Guardrails', 'DATASET MODEL');
  panel(slide, 0.78, 1.34, 4.8, 4.96, C.paper, C.line);
  body(slide, 'A demo dataset always includes', 1.0, 1.58, 2.8, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  bullets(slide, [
    'question_struct.json',
    'document_bundle.json',
    'case_record.json',
    'rule_pool.json',
    'review_task.json',
    'execution_trace.json',
    'simulation_dataset.json',
    'dataset_manifest.json',
    'validation_summary.json',
  ], 1.0, 1.98, 3.9, C.ink, C.navy, 0.3);

  panel(slide, 5.9, 1.34, 6.58, 2.26, C.paper, C.line);
  body(slide, 'Schema guardrails', 6.16, 1.58, 2.2, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  bullets(slide, [
    '16 formal JSON Schemas are generated from the current model set',
    'import refuses malformed datasets',
    'validation_summary.json records file-by-file status',
    'this prevents the registry from accepting structurally broken datasets',
  ], 6.16, 1.9, 5.8, C.ink, C.rust, 0.34);

  panel(slide, 5.9, 3.88, 6.58, 2.42, C.paper, C.line);
  body(slide, 'Lifecycle for one dataset', 6.16, 4.12, 2.6, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.olive,
  });
  const flow = ['generate', 'validate', 'import', 'consume', 'replay', 'rerun', 'register'];
  flow.forEach((step, index) => {
    const x = 6.16 + index * 0.86;
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 4.7,
      w: 0.74,
      h: 0.48,
      fill: { color: index % 2 === 0 ? C.olive : C.navy },
      line: { color: index % 2 === 0 ? C.olive : C.navy, transparency: 100 },
    });
    body(slide, step, x, 4.87, 0.74, 0.12, {
      fontSize: 8.8,
      bold: true,
      color: C.white,
      align: 'center',
      valign: 'mid',
    });
    if (index < flow.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, {
        x: x + 0.76,
        y: 4.8,
        w: 0.08,
        h: 0.28,
        fill: { color: C.line },
        line: { color: C.line, transparency: 100 },
      });
    }
  });
  body(slide, 'Current prototype already completes this chain for both demo cases.', 6.16, 5.46, 5.7, 0.18, {
    fontSize: 10.5,
    color: C.muted,
  });
}

// Slide 5
{
  const slide = makeSlide('Execution And Async Jobs', 'WORKFLOW');
  panel(slide, 0.78, 1.34, 6.0, 4.92, C.paper, C.line);
  body(slide, 'Direct-match path', 1.0, 1.58, 2.0, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  const flow = [
    'dataset.validate',
    'dataset.import',
    'dataset.summary',
    'dataset.replay',
    'dataset.rerun',
  ];
  flow.forEach((step, index) => {
    const y = 1.96 + index * 0.66;
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 1.0,
      y,
      w: 2.2,
      h: 0.42,
      fill: { color: index % 2 === 0 ? C.navy : C.rust },
      line: { color: index % 2 === 0 ? C.navy : C.rust, transparency: 100 },
    });
    body(slide, step, 1.0, y + 0.13, 2.2, 0.12, {
      fontSize: 10.5,
      bold: true,
      color: C.white,
      align: 'center',
      valign: 'mid',
    });
    if (index < flow.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, {
        x: 1.92,
        y: y + 0.44,
        w: 0.18,
        h: 0.16,
        rotate: 90,
        fill: { color: C.line },
        line: { color: C.line, transparency: 100 },
      });
    }
  });
  bullets(slide, [
    'rerun compares the fresh runtime result with the stored execution trace',
    'the current system proves result consistency on both demo cases',
  ], 3.56, 2.02, 2.8, C.ink, C.olive, 0.42);

  panel(slide, 7.0, 1.34, 5.48, 4.92, C.paper, C.line);
  body(slide, 'Registry-backed async job path', 7.24, 1.58, 2.8, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  const statuses = [
    ['queued', C.gold],
    ['running', C.navy],
    ['completed', C.olive],
  ];
  statuses.forEach((item, index) => {
    const x = 7.24 + index * 1.55;
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 2.12,
      w: 1.26,
      h: 0.56,
      fill: { color: item[1] },
      line: { color: item[1], transparency: 100 },
    });
    body(slide, item[0], x, 2.32, 1.26, 0.14, {
      fontSize: 11,
      bold: true,
      color: item[1] === C.gold ? C.ink : C.white,
      align: 'center',
      valign: 'mid',
    });
    if (index < statuses.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, {
        x: x + 1.3,
        y: 2.24,
        w: 0.18,
        h: 0.28,
        fill: { color: C.line },
        line: { color: C.line, transparency: 100 },
      });
    }
  });
  bullets(slide, [
    'registry.workflow.run now returns immediately as a queued job',
    'a background worker process picks the run up and writes final state to SQLite',
    'the browser console polls and updates list/detail panels automatically',
  ], 7.24, 3.16, 4.6, C.ink, C.rust, 0.42);
  codeBlock(slide, [
    'POST /api/phase1',
    '{',
    '  "action": "registry.workflow.run",',
    '  "dataset_id": "demo_set_001",',
    '  "request_id": "job_001"',
    '}',
  ].join('\n'), 7.24, 4.92, 4.8, 1.08);
}

// Slide 6
{
  const slide = makeSlide('Service Surfaces', 'API AND UI');
  panel(slide, 0.78, 1.34, 3.86, 5.0, C.paper, C.line);
  body(slide, 'Function API', 1.0, 1.58, 1.8, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  bullets(slide, [
    'handle_request(payload)',
    'stable envelope: ok / data / error',
    'used by CLI, HTTP, tests, and now registry console',
  ], 1.0, 1.98, 3.0, C.ink, C.navy, 0.4);
  codeBlock(slide, '{"action":"dataset.summary"}', 1.0, 3.54, 3.4, 0.76);

  panel(slide, 4.74, 1.34, 3.86, 5.0, C.paper, C.line);
  body(slide, 'HTTP API', 4.96, 1.58, 1.8, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  bullets(slide, [
    'GET /health',
    'POST /api/phase1',
    'same actions as function API',
    'usable from curl, browser, or another service',
  ], 4.96, 1.98, 3.0, C.ink, C.rust, 0.4);
  codeBlock(slide, 'curl -s -X POST http://127.0.0.1:8011/api/phase1', 4.96, 3.54, 3.4, 0.76);

  panel(slide, 8.7, 1.34, 3.78, 5.0, C.paper, C.line);
  body(slide, 'Browser Console', 8.94, 1.58, 2.1, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.olive,
  });
  bullets(slide, [
    'register datasets',
    'list datasets and runs',
    'view dataset and run detail panels',
    'submit jobs and watch status updates',
  ], 8.94, 1.98, 2.9, C.ink, C.olive, 0.4);
  codeBlock(slide, 'http://127.0.0.1:8011/console', 8.94, 3.54, 3.2, 0.76);
}

// Slide 7
{
  const slide = makeSlide('How To Demo In Five Minutes', 'LIVE DEMO SCRIPT');
  panel(slide, 0.78, 1.34, 5.82, 4.92, C.paper, C.line);
  body(slide, 'Live sequence', 1.02, 1.58, 2.0, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  const scriptSteps = [
    'Start the HTTP service and open /console',
    'Register the fund dataset, then the credit dataset',
    'Open each dataset detail panel to show different matched rules',
    'Launch one workflow job and watch it move from queued to completed',
    'Open the run detail panel and show the stored result payload',
  ];
  bullets(slide, scriptSteps, 1.02, 1.96, 4.9, C.ink, C.navy, 0.46);

  panel(slide, 6.84, 1.34, 5.62, 4.92, C.paper, C.line);
  body(slide, 'Commands to keep ready', 7.08, 1.58, 2.6, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  codeBlock(slide, [
    'python3 -m phase1_runtime.api.api_http --host 127.0.0.1 --port 8011',
    'python3 -m phase1_runtime.tools.mock_data single',
    'python3 -m phase1_runtime.tools.mock_data_credit',
    'python3 -m unittest discover -s phase1_runtime/tests',
  ].join('\n'), 7.08, 2.0, 4.94, 1.52);
  codeBlock(slide, [
    'API example',
    '{"action":"registry.workflow.run",',
    ' "dataset_id":"demo_set_001",',
    ' "request_id":"job_demo"}',
  ].join('\n'), 7.08, 4.06, 4.94, 1.06);
}

// Slide 8
{
  const slide = makeSlide('Next Phase', 'RECOMMENDED PLAN');
  panel(slide, 0.78, 1.34, 4.0, 4.9, C.paper, C.line);
  body(slide, 'What is already good enough', 1.02, 1.58, 2.6, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.olive,
  });
  bullets(slide, [
    'two distinct cases run on the same core skeleton',
    'datasets, jobs, and traces are all inspectable',
    'browser console is usable for demos and review',
    'the system can now be handed off for MVP packaging',
  ], 1.02, 1.96, 3.3, C.ink, C.olive, 0.42);

  panel(slide, 5.08, 1.34, 3.54, 4.9, C.paper, C.line);
  body(slide, 'Immediate next priorities', 5.3, 1.58, 2.4, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.navy,
  });
  bullets(slide, [
    'package the service for repeatable startup',
    'add one or two real samples beyond simulation',
    'polish run detail UI for review and triage',
    'define deployment and operator guide',
  ], 5.3, 1.96, 2.9, C.ink, C.navy, 0.42);

  panel(slide, 8.92, 1.34, 3.56, 4.9, C.paper, C.line);
  body(slide, 'What not to do next', 9.16, 1.58, 2.2, 0.2, {
    fontSize: 15,
    bold: true,
    color: C.rust,
  });
  bullets(slide, [
    'do not keep polishing one more internal abstraction',
    'do not add many static demo cases before using real data',
    'do not overbuild multi-agent or production infra yet',
  ], 9.16, 1.96, 2.8, C.ink, C.rust, 0.48);
  body(slide, 'The right move now is productization, not more prototype depth.', 9.16, 5.26, 2.8, 0.28, {
    fontSize: 11,
    italic: true,
    color: C.navy,
  });
}

finalizeSlides();

const outPath = path.join(__dirname, 'phase1_runtime_mvp_demo.pptx');
pptx.writeFile({ fileName: outPath });
