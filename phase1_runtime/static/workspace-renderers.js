(function () {
  const {
    chip,
    displayAnswerSource,
    displayRouteLabel,
    displayStatusLabel,
    escapeHtml,
  } = window.Phase1UI;

  function formatInlineAnswer(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function renderAnswerParagraph(lines) {
    return `<p>${lines.map((line) => formatInlineAnswer(line)).join("<br />")}</p>`;
  }

  function renderAnswerList(lines, ordered = false) {
    const tag = ordered ? "ol" : "ul";
    const className = ordered ? "answer-ordered-list" : "answer-list";
    const cleaned = lines.map((line) => (
      ordered
        ? line.replace(/^\d+\.\s+/, "")
        : line.replace(/^[-*]\s+/, "")
    ));
    return `<${tag} class="${className}">${cleaned.map((line) => `<li>${formatInlineAnswer(line)}</li>`).join("")}</${tag}>`;
  }

  function parseTableCells(line) {
    let normalized = String(line || "").trim();
    if (!normalized.includes("|")) {
      return [];
    }
    if (normalized.startsWith("|")) {
      normalized = normalized.slice(1);
    }
    if (normalized.endsWith("|")) {
      normalized = normalized.slice(0, -1);
    }
    return normalized.split("|").map((cell) => cell.trim());
  }

  function isTableSeparatorRow(line) {
    const cells = parseTableCells(line);
    return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
  }

  function isMarkdownTable(lines) {
    if (!Array.isArray(lines) || lines.length < 2) {
      return false;
    }
    const headerCells = parseTableCells(lines[0]);
    const separatorCells = parseTableCells(lines[1]);
    return headerCells.length > 0 && headerCells.length === separatorCells.length && isTableSeparatorRow(lines[1]);
  }

  function tableAlignment(separatorCell) {
    const normalized = String(separatorCell || "").replace(/\s+/g, "");
    if (normalized.startsWith(":") && normalized.endsWith(":")) return "center";
    if (normalized.endsWith(":")) return "right";
    return "left";
  }

  function renderAnswerTable(lines) {
    const headerCells = parseTableCells(lines[0]);
    const separatorCells = parseTableCells(lines[1]);
    const alignments = separatorCells.map((cell) => tableAlignment(cell));
    const bodyRows = lines.slice(2)
      .map((line) => parseTableCells(line))
      .filter((cells) => cells.length);

    const renderCell = (tag, value, index) => `
      <${tag} class="answer-table-cell table-align-${alignments[index] || "left"}">${formatInlineAnswer(value || "")}</${tag}>
    `;

    return `
      <div class="answer-table-wrap">
        <table class="answer-table">
          <thead>
            <tr>
              ${headerCells.map((cell, index) => renderCell("th", cell, index)).join("")}
            </tr>
          </thead>
          <tbody>
            ${bodyRows.map((row) => `
              <tr>
                ${headerCells.map((_, index) => renderCell("td", row[index] || "", index)).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderAnswerCodeBlock(language, code) {
    const codeText = String(code || "").replace(/\s+$/, "");
    const codeLabel = language ? escapeHtml(language) : "代码";
    const languageClass = `language-${escapeHtml((language || "plaintext").toLowerCase())}`;
    return `
      <div class="answer-code-card">
        <div class="answer-code-head">
          <span class="answer-code-label">${codeLabel}</span>
          <button type="button" class="answer-code-copy-btn" data-copy-code="${escapeHtml(codeText)}">复制代码</button>
        </div>
        <pre><code class="answer-code-block ${languageClass}">${escapeHtml(codeText)}</code></pre>
      </div>
    `;
  }

  function renderExplorationActions(payload) {
    const exploration = payload.exploration_runtime || {};
    const review = payload.asset_pipeline?.review || null;
    const feedback = payload.asset_pipeline?.feedback || null;
    const candidateDrafts = Array.isArray(exploration.candidate_rule_drafts) ? exploration.candidate_rule_drafts : [];
    const primaryCandidate = candidateDrafts[0] || {};
    const stageCount = Array.isArray(exploration.external_stages) ? exploration.external_stages.length : 0;
    const taskId = exploration.external_task?.task_id || payload.exploration_links?.task_id || exploration.exploration_trace_id || "-";
    const recommendedAction = primaryCandidate.recommended_action || payload.feedback_defaults?.payload?.recommended_action || "-";
    const statusText = review?.status
      ? displayStatusLabel(review.status)
      : feedback?.feedback_id
        ? "候选规则已进入治理链"
        : "等待多智能体探索完成";
    const actionPending = Boolean(payload._reviewActionPending);
    const approveLabel = actionPending && payload._reviewAction === "approve" ? "正在接入规则库…" : "审核通过，接入规则库";
    const rejectLabel = actionPending && payload._reviewAction === "reject" ? "正在重新探索…" : "驳回并重新探索";
    return `
      <div class="artifact-card warm" style="margin-top:12px;">
        <h3>多智能体探索增长链</h3>
        <div class="section-copy">当前问题没有稳定规则可直接复用，系统已经启动多智能体探索。它会围绕当前问题、证据和已有规则，生成候选规则草稿，并送入后续审核发布链。</div>
        <div class="detail-grid-2" style="margin-top:12px;">
          <div class="detail-card key">
            <span class="micro-label">探索任务</span>
            <div class="section-copy">${escapeHtml(taskId)}</div>
          </div>
          <div class="detail-card warm">
            <span class="micro-label">当前状态</span>
            <div class="section-copy">${escapeHtml(statusText)}</div>
          </div>
          <div class="detail-card muted">
            <span class="micro-label">候选规则草稿</span>
            <div class="section-copy">${escapeHtml(String(candidateDrafts.length || 0))} 条</div>
          </div>
          <div class="detail-card key">
            <span class="micro-label">推荐动作</span>
            <div class="section-copy">${escapeHtml(recommendedAction)}</div>
          </div>
        </div>
        ${primaryCandidate.summary ? `
          <div class="detail-card soft" style="margin-top:12px;">
            <span class="micro-label">当前候选摘要</span>
            <div class="section-copy">${escapeHtml(primaryCandidate.summary)}</div>
          </div>
        ` : ""}
        <div class="chip-row" style="margin-top:12px;">
          ${chip(`增长引擎：多智能体探索`, "gold")}
          ${chip(`阶段数：${stageCount}`)}
          ${exploration.trigger_reason ? chip(`触发原因：${exploration.trigger_reason}`, "warn") : ""}
        </div>
        ${(payload.exploration_links?.workbench_url || payload.exploration_links?.report_url) ? `
          <div class="button-row" style="margin-top:14px;">
            ${payload.exploration_links?.workbench_url ? `<a class="nav-link" href="${escapeHtml(payload.exploration_links.workbench_url)}">打开探索工作台</a>` : ""}
            ${payload.exploration_links?.report_url ? `<a class="nav-link" href="${escapeHtml(payload.exploration_links.report_url)}">打开探索报告</a>` : ""}
          </div>
        ` : ""}
        <div class="button-row" style="margin-top:14px;">
          <button class="btn-primary" data-review-action="approve" ${actionPending ? "disabled" : ""}>${escapeHtml(approveLabel)}</button>
          <button class="btn-secondary" data-review-action="reject" ${actionPending ? "disabled" : ""}>${escapeHtml(rejectLabel)}</button>
        </div>
      </div>
    `;
  }

  function formatAnswerMarkup(value) {
    const normalized = String(value || "").replace(/\r\n/g, "\n").trim();
    if (!normalized) {
      return "<p>尚无最终回答。</p>";
    }
    const segments = [];
    const fencePattern = /```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;
    while ((match = fencePattern.exec(normalized)) !== null) {
      if (match.index > lastIndex) {
        segments.push({ type: "text", content: normalized.slice(lastIndex, match.index) });
      }
      segments.push({
        type: "code",
        language: (match[1] || "").trim(),
        content: match[2] || "",
      });
      lastIndex = fencePattern.lastIndex;
    }
    if (lastIndex < normalized.length) {
      segments.push({ type: "text", content: normalized.slice(lastIndex) });
    }

    return segments.map((segment) => {
      if (segment.type === "code") {
        return renderAnswerCodeBlock(segment.language, segment.content);
      }
      const blocks = String(segment.content || "")
        .split(/\n{2,}/)
        .map((block) => block.trim())
        .filter(Boolean);
      return blocks.map((block) => {
        const lines = block
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
        if (!lines.length) return "";

        const headingMatch = lines[0].match(/^(#{1,6})\s+(.+)$/);
        if (headingMatch) {
          const level = Math.min(4, headingMatch[1].length + 1);
          const heading = `<h${level} class="answer-heading">${formatInlineAnswer(headingMatch[2])}</h${level}>`;
          const remaining = lines.slice(1);
          if (!remaining.length) {
            return heading;
          }
          if (remaining.every((line) => /^[-*]\s+/.test(line))) {
            return heading + renderAnswerList(remaining, false);
          }
          if (remaining.every((line) => /^\d+\.\s+/.test(line))) {
            return heading + renderAnswerList(remaining, true);
          }
          if (isMarkdownTable(remaining)) {
            return heading + renderAnswerTable(remaining);
          }
          return heading + renderAnswerParagraph(remaining);
        }

        if (isMarkdownTable(lines)) {
          return renderAnswerTable(lines);
        }
        if (lines.every((line) => /^[-*]\s+/.test(line))) {
          return renderAnswerList(lines, false);
        }
        if (lines.every((line) => /^\d+\.\s+/.test(line))) {
          return renderAnswerList(lines, true);
        }
        return renderAnswerParagraph(lines);
      }).join("");
    }).join("");
  }

  function displayDecisionLabel(payload) {
    const rawLabel = String(payload.display_decision_text || payload.decision_text || payload.final_decision || "未生成");
    const finalAnswer = String(payload.final_answer || "").trim();
    const hasUsableSuperAgentAnswer = (
      payload.answer_engine === "super_agent"
      && payload.route_decision === "direct_match"
      && finalAnswer
      && !finalAnswer.startsWith("Stopped after reaching")
    );
    if (hasUsableSuperAgentAnswer && rawLabel === "建议先人工复核") {
      return "已生成最终答案";
    }
    return rawLabel;
  }

  function renderHeroStatusChips(backend) {
    return [
      chip("主入口：规则复用 + 规则生长", "gold"),
      chip(`Embedding: ${backend?.backend_id || "unknown"}`, "ok"),
      chip("样本一：规则直接复用", "ok"),
      chip("样本二：多智能体探索增长", "warn"),
    ].join("");
  }

  function renderScenarioOptions(items) {
    return `<option value="">自动识别</option>` + items.map((item) => (
      `<option value="${escapeHtml(item.scenario_id)}">${escapeHtml(item.title)}</option>`
    )).join("");
  }

  function renderFileList(files) {
    const visibleFiles = files.filter((file) => !file.hidden_in_ui);
    if (!visibleFiles.length) {
      return `<div class="empty-state">未选择文件。你可以直接运行推荐样本，或上传自己的文档后开始。</div>`;
    }
    return visibleFiles.map((file) => `
      <div class="sample-card">
        <h3>${escapeHtml(file.name)}</h3>
        <div class="meta-strip">
          ${chip(file.demo_source === "workspace_sample" ? "推荐样本材料" : "本地文件", file.demo_source === "workspace_sample" ? "ok" : "")}
          ${chip(`${((file.size || 0) / 1024).toFixed(1)} KB`)}
        </div>
      </div>
    `).join("");
  }

  function renderSampleList(items, selectedCaseRef) {
    if (!items.length) {
      return `<div class="empty-state">暂无样本。</div>`;
    }
    return items.map((item) => `
      <button type="button" class="sample-card ${item.featured ? "sample-card--featured" : ""} ${selectedCaseRef === item.case_ref ? "active" : ""}" data-case-ref="${escapeHtml(item.case_ref)}">
        ${item.featured ? `<span class="micro-label sample-card-label">${escapeHtml(item.featured_label || "重点样本")}</span>` : ""}
        <h3>${escapeHtml(item.title)}</h3>
        <div class="meta-strip">
          ${selectedCaseRef === item.case_ref ? chip("已载入", "ok") : ""}
          ${item.featured ? chip(item.featured_label || "重点样本", "gold") : ""}
          ${item.route_decision ? chip(displayRouteLabel(item.route_decision), item.route_decision === "exploration" ? "warn" : "ok") : ""}
          ${chip(item.case_ref === "workspace/equity_research_h3_code_upside_calc" ? "复杂规则 + 代码核验" : item.route_decision === "exploration" ? "探索样本" : "复用样本")}
        </div>
        <div class="section-copy">${escapeHtml(item.question_text || item.note || "")}</div>
      </button>
    `).join("");
  }

  function renderRelatedQuestionList(questions) {
    if (!questions.length) {
      return `<div class="empty-state">当前样本未提供可切换的任务模板。</div>`;
    }
    return questions.map((question, index) => `
      <button type="button" class="compact-question-btn ${index === 0 && String(question).includes("上涨空间") && String(question).includes("Python") ? "compact-question-btn--featured" : ""}" data-related-question="${escapeHtml(question)}">
        ${index === 0 && String(question).includes("上涨空间") && String(question).includes("Python") ? "复杂审计任务：" : ""}${escapeHtml(question)}
      </button>
    `).join("");
  }

  function renderAnswerStatus(payload) {
    return [
      chip(displayDecisionLabel(payload), "gold"),
      chip(`处理方式：${displayRouteLabel(payload.route_decision, payload.route_title)}`),
      chip(`结果来源：${displayAnswerSource(payload.answer_engine)}`, payload.answer_engine === "super_agent" ? "ok" : "warn"),
    ].join("");
  }

  function renderAnswerMeta(payload) {
    return `
      <div><strong>场景：</strong>${escapeHtml(payload.scenario_title || payload.scenario_id || "-")}</div>
      <div><strong>问题：</strong>${escapeHtml(payload.question_text || "-")}</div>
    `;
  }

  function readableRuleNarrative(binding) {
    const purpose = String(binding?.primary_goal || binding?.rule_scope || "").trim();
    const fit = String(binding?.context_summary || binding?.binding_status_text || "").trim();
    if (purpose && fit) {
      return `这条规则负责：${purpose} 当前之所以命中，是因为：${fit}`;
    }
    if (purpose) {
      return `这条规则负责：${purpose}`;
    }
    if (fit) {
      return `当前命中这条规则的原因是：${fit}`;
    }
    return "系统已命中一条可直接执行的规则。";
  }

  function displayChunkTypeLabel(value) {
    return {
      heading: "标题",
      paragraph: "正文段落",
      clause: "关键段落",
      table: "表格",
      list: "列表",
      quote: "引用",
      code: "代码",
    }[String(value || "").toLowerCase()] || "文档摘录";
  }

  function displayEvidenceLocator(locator) {
    if (!locator) return "位置待定位";
    if (locator.page) return `第 ${locator.page} 页`;
    if (locator.line) return `第 ${locator.line} 行`;
    if (locator.row) return `第 ${locator.row} 行`;
    return "位置待定位";
  }

  function displayChunkTitle(item) {
    const locator = item?.locator || {};
    const section = String(locator.section || "").trim();
    const typeLabel = displayChunkTypeLabel(item?.chunk_type || locator.block_type);
    const locationLabel = locator.page ? `第 ${locator.page} 页` : "摘录";
    if (section) {
      return `${section} · ${typeLabel}`;
    }
    return `${locationLabel} · ${typeLabel}`;
  }

  function renderDefaultDecisionSummary() {
    return `
      <div class="decision-highlight">
        <span class="micro-label">当前结论</span>
        <div class="headline-value">等待运行</div>
        <div class="section-copy">运行后，这里会先给出这次问题最重要的结论与当前状态。</div>
      </div>
      <div class="mini-stat-grid">
        ${[
          { label: "当前处理方式", value: "待判断" },
          { label: "结果来源", value: "待执行" },
          { label: "关键证据", value: "0" },
        ].map((item) => `
          <div class="mini-stat">
            <span class="kpi-label">${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderDecisionSummary(payload) {
    const evidenceCount = (payload.evidence_refs || []).length;
    const review = payload.asset_pipeline?.review || null;
    const draft = payload.asset_pipeline?.promotion?.draft || null;
    const feedback = payload.asset_pipeline?.feedback || null;
    const missingSlotItems = payload.missing_slot_items || [];
    const bindings = payload.rule_bindings || [];
    const primaryBinding = bindings.find((item) => item.rule_id === payload.matched_rule_id) || bindings[0] || null;
    let reviewStatusText = "当前无可审核对象";
    if (review?.status) {
      reviewStatusText = displayStatusLabel(review.status);
    } else if (draft?.draft_id) {
      reviewStatusText = "待创建审核";
    } else if (feedback?.feedback_id) {
      reviewStatusText = "待形成方法草稿";
    }
    return `
      <div class="decision-highlight">
        <span class="micro-label">当前结论</span>
        <div class="headline-value">${escapeHtml(displayDecisionLabel(payload))}</div>
        <div class="section-copy">${escapeHtml(payload.route_explanation || "系统已根据当前材料形成这次问题的处理结论。")}</div>
      </div>
      <div class="mini-stat-grid">
        ${[
          { label: "当前处理方式", value: displayRouteLabel(payload.route_decision, payload.route_title) || "待判断" },
          { label: "结果来源", value: displayAnswerSource(payload.answer_engine) || "待执行" },
          { label: "关键证据", value: String(evidenceCount) },
        ].map((item) => `
          <div class="mini-stat">
            <span class="kpi-label">${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
          </div>
        `).join("")}
      </div>
      ${payload.route_decision === "exploration" ? `
        <div class="section-copy" style="margin-top:12px;">
          <strong>多智能体探索状态：</strong>${escapeHtml(reviewStatusText)}
        </div>
      ` : ""}
      ${primaryBinding ? `
        <div class="artifact-card soft" style="margin-top:12px;">
          <span class="micro-label">本次命中的规则</span>
          <div class="section-copy" style="margin-top:8px;">${escapeHtml(readableRuleNarrative(primaryBinding))}</div>
          <div class="section-copy" style="margin-top:8px;"><strong>规则名称：</strong>${escapeHtml(primaryBinding.rule_name || primaryBinding.rule_id || "-")}</div>
          <div class="section-copy" style="margin-top:6px;"><strong>规则编号：</strong>${escapeHtml(primaryBinding.rule_id || "-")}</div>
        </div>
      ` : ""}
      ${missingSlotItems.length ? `
        <div class="artifact-card warm" style="margin-top:12px;">
          <span class="micro-label">还缺这些信息</span>
          <div class="chip-row" style="margin-top:8px;">
            ${missingSlotItems.map((item) => chip(item.label || item.slot_id, "warn")).join("")}
          </div>
        </div>
      ` : ""}
      ${payload.route_decision === "exploration" ? renderExplorationActions(payload) : ""}
    `;
  }

  function renderEvidence(payload) {
    const refs = payload.evidence_refs || [];
    if (!refs.length) {
      return `<div class="empty-state">暂无证据。</div>`;
    }
    const [primary, ...rest] = refs.slice(0, 6);
    return `
      <div class="evidence-item primary">
        <span class="micro-label">主证据</span>
        <div class="section-copy evidence-snippet">${escapeHtml(primary?.text || "")}</div>
        <div class="meta-strip">
          ${chip(primary?.doc_id || "evidence")}
          ${chip(displayEvidenceLocator(primary?.locator))}
        </div>
      </div>
      ${rest.length ? `
        <div class="card-list" style="margin-top:12px;">
          ${rest.map((item) => `
            <div class="evidence-item">
              <div class="section-copy evidence-snippet">${escapeHtml(item.text || "")}</div>
              <div class="meta-strip">
                ${chip(item.doc_id || "evidence")}
                ${chip(displayEvidenceLocator(item.locator))}
              </div>
            </div>
          `).join("")}
        </div>
      ` : ""}
    `;
  }

  function renderDecisionEvidence(payload) {
    const packet = payload.context_packet || {};
    const refs = payload.evidence_refs || [];
    const groundedFacts = (payload.fact_sheet || [])
      .filter((item) => item && item.value !== null && item.value !== undefined)
      .slice(0, 6);
    const topRefs = refs.slice(0, 4);
    return `
      <div class="stack">
        <div class="artifact-card featured focus">
          <h3>这次结论主要依据什么</h3>
          <div class="section-copy">${escapeHtml(packet.context_summary || payload.route_explanation || "当前还没有形成更完整的依据摘要。")}</div>
          ${groundedFacts.length ? `
            <div class="chip-row" style="margin-top:12px;">
              ${groundedFacts.map((item) => chip(`${item.fact_id}: ${String(item.value)}`)).join("")}
            </div>
          ` : ""}
        </div>
        <div class="artifact-card soft">
          <h3>关键证据展开</h3>
          ${topRefs.length ? `
            <div class="card-list" style="margin-top:12px;">
              ${topRefs.map((item, index) => `
                <div class="evidence-item ${index === 0 ? "primary" : ""}">
                  <span class="micro-label">${index === 0 ? "主证据" : "补充证据"}</span>
                  <div class="section-copy evidence-snippet">${escapeHtml(item.text || "")}</div>
                  <div class="meta-strip">
                    ${chip(item.doc_id || "evidence")}
                    ${chip(displayEvidenceLocator(item.locator))}
                  </div>
                </div>
              `).join("")}
            </div>
          ` : `<div class="empty-state">当前还没有可展开的关键证据。</div>`}
        </div>
        <div class="artifact-card">
          <h3>上下文摘要</h3>
          ${renderContext(payload)}
        </div>
      </div>
    `;
  }

  function renderDecisionStatus(payload) {
    const bindings = payload.rule_bindings || [];
    const primaryBinding = bindings.find((item) => item.rule_id === payload.matched_rule_id) || bindings[0] || null;
    const missingSlotItems = payload.missing_slot_items || [];
    const review = payload.asset_pipeline?.review || null;
    const skillMd = String(payload.runtime_skill_spec_preview?.skill_md || "").trim();
    const normalizedSkillMd = skillMd.replace(/^---[\s\S]*?---\s*/, "").trim();
    const skillPreview = normalizedSkillMd.split(/\n{2,}/).slice(0, 3).join("\n\n");
    return `
      <div class="stack">
        <div class="artifact-card focus">
          <h3>为什么是当前状态</h3>
          <div class="section-copy">${escapeHtml(payload.route_explanation || "系统已基于当前材料形成状态判断。")}</div>
          <div class="detail-grid-2">
            <div class="detail-card key">
              <span class="micro-label">当前结论</span>
              <div class="headline-value">${escapeHtml(displayDecisionLabel(payload))}</div>
            </div>
            <div class="detail-card warm">
              <span class="micro-label">结果来源</span>
              <div class="section-copy">${escapeHtml(displayAnswerSource(payload.answer_engine) || "-")}</div>
            </div>
            <div class="detail-card muted">
              <span class="micro-label">当前处理方式</span>
              <div class="section-copy">${escapeHtml(displayRouteLabel(payload.route_decision, payload.route_title) || "-")}</div>
            </div>
            <div class="detail-card ${payload.route_decision === "exploration" ? "warm" : "key"}">
              <span class="micro-label">${payload.route_decision === "exploration" ? "多智能体探索" : "当前状态"}</span>
              <div class="section-copy">${escapeHtml(payload.route_decision === "exploration" ? displayStatusLabel(review?.status || "pending") : "当前已形成可执行判断")}</div>
            </div>
          </div>
        </div>
        ${primaryBinding ? `
          <div class="artifact-card olive">
            <h3>命中或最接近的方法</h3>
            <div class="section-copy">${escapeHtml(primaryBinding.rule_name || primaryBinding.rule_id || "方法")}</div>
            <div class="section-copy" style="margin-top:8px;"><strong>当前判断：</strong>${escapeHtml(primaryBinding.context_summary || primaryBinding.binding_status_text || primaryBinding.binding_status || "-")}</div>
            <div class="chip-row" style="margin-top:12px;">
              ${chip(primaryBinding.rule_kind_text || primaryBinding.rule_kind || "规则")}
              ${chip(primaryBinding.binding_status_text || primaryBinding.binding_status || "未知状态", primaryBinding.binding_status === "bindable" ? "ok" : primaryBinding.binding_status === "partially_bindable" ? "warn" : "")}
              ${chip(`匹配分 ${primaryBinding.binding_score ?? "-"}`)}
            </div>
            ${(primaryBinding.display_reasons || []).length ? `
              <div class="chip-row" style="margin-top:12px;">
                ${(primaryBinding.display_reasons || []).slice(0, 4).map((reason) => chip(reason)).join("")}
              </div>
            ` : ""}
          </div>
        ` : ""}
        ${primaryBinding ? `
          <div class="artifact-card soft">
            <h3>命中规则内容</h3>
            <div class="section-copy"><strong>规则用途：</strong>${escapeHtml(primaryBinding.primary_goal || primaryBinding.rule_scope || "当前规则未提供说明。")}</div>
            ${primaryBinding.rule_scope ? `<div class="section-copy" style="margin-top:8px;"><strong>适用范围：</strong>${escapeHtml(primaryBinding.rule_scope)}</div>` : ""}
            ${primaryBinding.rule_non_scope ? `<div class="section-copy" style="margin-top:8px;"><strong>不适用：</strong>${escapeHtml(primaryBinding.rule_non_scope)}</div>` : ""}
            <div class="section-copy" style="margin-top:8px;"><strong>内部编号：</strong>${escapeHtml(primaryBinding.rule_id || "-")}</div>
            ${skillPreview ? `
              <div class="rule-content-card">
                <div class="micro-label">规则正文预览</div>
                <pre class="rule-content-block">${escapeHtml(skillPreview)}</pre>
              </div>
            ` : ""}
          </div>
        ` : ""}
        ${missingSlotItems.length ? `
          <div class="artifact-card warm">
            <h3>当前还缺什么</h3>
            <div class="chip-row" style="margin-top:10px;">
              ${missingSlotItems.map((item) => chip(item.label || item.slot_id, "warn")).join("")}
            </div>
          </div>
        ` : ""}
        ${payload.route_decision === "exploration" ? renderExplorationActions(payload) : ""}
      </div>
    `;
  }

  function renderContext(payload) {
    const packet = payload.context_packet || {};
    const blocks = packet.relevant_blocks || [];
    return `
      <div class="section-copy">${escapeHtml(packet.context_summary || "当前没有形成 query-aware context。")}</div>
      <div class="card-list">
        ${blocks.length ? blocks.map((item) => `
          <div class="artifact-card">
            <h3>${escapeHtml(displayChunkTitle(item))}</h3>
            <div class="section-copy">${escapeHtml(item.text || "")}</div>
            <div class="meta-strip" style="margin-top:10px;">
              ${chip(displayEvidenceLocator(item.locator))}
            </div>
          </div>
        `).join("") : `<div class="empty-state">暂无相关块。</div>`}
      </div>
    `;
  }

  function renderBindings(payload) {
    const bindings = payload.rule_bindings || [];
    if (!bindings.length) {
      return `<div class="empty-state">暂无方法匹配结果。</div>`;
    }
    return `
      <div class="card-list">
        ${bindings.slice(0, 6).map((item) => `
          <div class="artifact-card">
            <h3>${escapeHtml(item.rule_name || item.rule_id)}</h3>
            <div class="section-copy">${escapeHtml(item.rule_scope || item.primary_goal || "当前规则未提供说明。")}</div>
            <div class="section-copy" style="margin-top:8px;"><strong>当前判断：</strong>${escapeHtml(item.context_summary || item.binding_status_text || item.binding_status || "-")}</div>
            <div class="chip-row" style="margin-top:10px;">
              ${chip(item.rule_kind_text || item.rule_kind || "规则")}
              ${chip(item.binding_status_text || item.binding_status || "未知状态", item.binding_status === "bindable" ? "ok" : item.binding_status === "partially_bindable" ? "warn" : "")}
              ${chip(`匹配分 ${item.binding_score ?? "-"}`)}
              ${chip(`${item.step_count || 0} 个步骤`)}
            </div>
            <div class="chip-row" style="margin-top:10px;">
              ${(item.display_reasons || []).slice(0, 4).map((reason) => chip(reason)).join("")}
            </div>
            <div class="section-copy" style="margin-top:10px;">
              <strong>规则用途：</strong>${escapeHtml(item.primary_goal || item.rule_scope || "-")}
            </div>
            ${item.rule_non_scope ? `<div class="section-copy" style="margin-top:6px;"><strong>不适用：</strong>${escapeHtml(item.rule_non_scope)}</div>` : ""}
            <div class="section-copy" style="margin-top:8px;"><strong>内部编号：</strong>${escapeHtml(item.rule_id)}</div>
            <div class="chip-row" style="margin-top:10px;">
              ${(item.query_signals || []).slice(0, 6).map((signal) => chip(signal)).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderSkill(payload) {
    const artifact = payload.runtime_skill_artifact;
    const preview = payload.runtime_skill_spec_preview;
    if (!artifact && !preview) {
      return `<div class="empty-state">当前还没有形成本次方法草稿。</div>`;
    }
    const skillMdPreview = String(preview?.skill_md || "").trim().split("\n").slice(0, 8).join("\n");
    return `
      <div class="artifact-card soft">
        <h3>${escapeHtml(preview?.skill_name || artifact?.skill_name || "method draft")}</h3>
        <div class="section-copy">${escapeHtml(preview?.description || artifact?.description || "")}</div>
        <div class="meta-strip">
          ${artifact ? chip(`草稿文件: ${artifact.skill_md_path}`) : ""}
          ${artifact?.validation?.ok ? chip("已完成结构校验", "ok") : chip("尚未完成结构校验", "warn")}
        </div>
        <div class="detail-grid-2">
          ${preview?.source_rule_id || artifact?.source_rule_id ? `
            <div class="detail-card muted">
              <span class="micro-label">来源</span>
              <div class="section-copy">${escapeHtml(preview?.source_rule_id || artifact?.source_rule_id || "-")}</div>
            </div>
          ` : ""}
          ${preview?.skill_type || preview?.binding_status ? `
            <div class="detail-card warm">
              <span class="micro-label">当前状态</span>
              <div class="section-copy">类型：${escapeHtml(preview?.skill_type || "-")} · 绑定：${escapeHtml(preview?.binding_status || "-")}</div>
            </div>
          ` : ""}
          ${skillMdPreview ? `
            <div class="detail-card key">
              <span class="micro-label">草稿预览</span>
              <div class="section-copy">${escapeHtml(skillMdPreview)}</div>
            </div>
          ` : ""}
        </div>
      </div>
    `;
  }

  function renderAgent(payload) {
    const result = payload.super_agent_result;
    if (!result) {
      return `<div class="empty-state">本次没有更完整的求解记录可展示。</div>`;
    }
    const trace = result.agent_trace || [];
    const recentSteps = trace
      .slice(-4)
      .map((item) => {
        if (item.event === "tool_result") return `调用工具：${item.tool_name || "-"}`;
        if (item.event === "assistant_response") return "生成中间回答";
        if (item.event === "stop") return "达到当前停止条件";
        return item.event || "过程事件";
      });
    return `
      <div class="artifact-card focus">
        <h3>求解记录</h3>
        <div class="meta-strip">
          ${chip(`轮次：${result.turns}`)}
          ${chip(`工具调用：${result.tool_call_count}`)}
          ${chip(`答案来源：${displayAnswerSource(payload.answer_engine)}`)}
        </div>
        <div class="detail-grid-2">
          <div class="detail-card key">
            <span class="micro-label">最终输出</span>
            <div class="section-copy">${escapeHtml(String(result.final_text || payload.final_answer || "暂无最终输出").slice(0, 320))}</div>
          </div>
          <div class="detail-card muted">
            <span class="micro-label">最近动作</span>
            <div class="section-copy">${recentSteps.length ? escapeHtml(recentSteps.join(" → ")) : "暂无更多过程动作。"}</div>
          </div>
        </div>
      </div>
    `;
  }

  function renderAssets(payload) {
    const pipeline = payload.asset_pipeline || {};
    const feedback = pipeline.feedback || {};
    const promotion = pipeline.promotion || {};
    const review = pipeline.review || null;
    return `
      <div class="artifact-card warm">
        <h3>${payload.route_decision === "exploration" ? "规则生长记录" : "内部记录"}</h3>
        <div class="meta-strip">
          ${chip(`求解记录: ${pipeline.workspace_run?.workspace_run_id || "-"}`)}
          ${chip(`当前状态: ${pipeline.auto_status || "-"}`, pipeline.auto_status === "draft_promoted" ? "ok" : "warn")}
        </div>
        <div class="detail-grid-2">
          <div class="detail-card key">
            <span class="micro-label">${payload.route_decision === "exploration" ? "增长动作" : "记录摘要"}</span>
            <div class="section-copy">${escapeHtml((feedback.payload || {}).recommended_action || feedback.feedback_type || "当前没有新增内部记录。")}</div>
          </div>
          <div class="detail-card warm">
            <span class="micro-label">${payload.route_decision === "exploration" ? "下一步" : "后续处理"}</span>
            <div class="section-copy">${escapeHtml((promotion.draft || {}).draft_id || pipeline.auto_status || "当前没有额外的规则治理动作。")}</div>
          </div>
        </div>
        ${payload.route_decision === "exploration" ? `
          <div class="section-copy" style="margin-top:12px;">
            <strong>审核状态：</strong>${escapeHtml(displayStatusLabel(review?.status || "pending"))}
          </div>
        ` : ""}
      </div>
    `;
  }

  function renderInternalPanel(payload) {
    const pipeline = payload.asset_pipeline || {};
    const review = pipeline.review || null;
    const hasDraft = Boolean(payload.runtime_skill_artifact || payload.runtime_skill_spec_preview);
    const hasAgent = Boolean(payload.super_agent_result);
    const summaryText = payload.route_decision === "exploration"
      ? "这次问题已经进入多智能体探索增长链。下面展示的是候选规则、审核状态以及它如何继续回到规则库。"
      : "这次问题已经完成求解。下面这些内容保留为内部记录，默认不需要展开。";
    return `
      <div class="stack">
        <div class="artifact-card warm">
          <h3>内部状态摘要</h3>
          <div class="section-copy">${escapeHtml(summaryText)}</div>
          <div class="detail-grid-2">
            <div class="detail-card key">
              <span class="micro-label">求解记录</span>
              <div class="section-copy">${escapeHtml(pipeline.workspace_run?.workspace_run_id || payload.trace_id || "-")}</div>
            </div>
            <div class="detail-card warm">
              <span class="micro-label">当前内部状态</span>
              <div class="section-copy">${escapeHtml(pipeline.auto_status || (payload.route_decision === "exploration" ? "待进入规则增长链" : "已记录"))}</div>
            </div>
            ${payload.route_decision === "exploration" ? `
              <div class="detail-card muted">
                <span class="micro-label">探索 / 审核状态</span>
                <div class="section-copy">${escapeHtml(displayStatusLabel(review?.status || "pending"))}</div>
              </div>
            ` : `
              <div class="detail-card muted">
                <span class="micro-label">当前模式</span>
                <div class="section-copy">本次以求解完成为主，未继续进入方法治理动作。</div>
              </div>
            `}
            <div class="detail-card key">
              <span class="micro-label">可展开项</span>
              <div class="section-copy">${escapeHtml([
                hasDraft ? "方法草稿" : null,
                hasAgent ? "求解过程" : null,
                "内部记录详情",
              ].filter(Boolean).join("、"))}</div>
            </div>
          </div>
        </div>
        ${hasDraft ? `
          <details class="fold-card">
            <summary>查看方法草稿</summary>
            <div class="fold-content">
              ${renderSkill(payload)}
            </div>
          </details>
        ` : ""}
        ${hasAgent ? `
          <details class="fold-card">
            <summary>查看求解过程</summary>
            <div class="fold-content">
              ${renderAgent(payload)}
            </div>
          </details>
        ` : ""}
        <details class="fold-card">
          <summary>查看内部记录详情</summary>
          <div class="fold-content">
            ${renderAssets(payload)}
          </div>
        </details>
      </div>
    `;
  }

  window.Phase1WorkspaceRenderers = {
    displayDecisionLabel,
    formatAnswerMarkup,
    renderAgent,
    renderAnswerMeta,
    renderAnswerStatus,
    renderAssets,
    renderBindings,
    renderContext,
    renderDecisionEvidence,
    renderDecisionStatus,
    renderDefaultDecisionSummary,
    renderDecisionSummary,
    renderEvidence,
    renderFileList,
    renderHeroStatusChips,
    renderInternalPanel,
    renderRelatedQuestionList,
    renderSampleList,
    renderScenarioOptions,
    renderSkill,
    renderExplorationActions,
  };
})();
