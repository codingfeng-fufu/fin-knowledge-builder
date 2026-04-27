(function () {
  const { chip, displayRouteLabel, displayStatusLabel, escapeHtml } = window.Phase1UI;

  function renderOpsDetail(kind, detail) {
    if (!detail) {
      return `<div class="empty-state">暂无详情。</div>`;
    }
    if (kind === "run") {
      const retrievalDiagnostics = (detail.payload || {}).retrieval_diagnostics || {};
      const dense = retrievalDiagnostics.dense || {};
      const rerank = retrievalDiagnostics.cross_rerank || {};
      return `
        <div class="artifact-card focus">
          <h3>求解记录详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">结论</span><div class="headline-value">${escapeHtml(detail.decision_text || detail.final_decision || "-")}</div></div>
          <div class="detail-grid-3">
            <div class="detail-card warm"><span class="micro-label">当前处理方式</span><div class="section-copy">${escapeHtml(displayRouteLabel(detail.route_decision, detail.route_title))}</div></div>
            <div class="detail-card muted"><span class="micro-label">状态</span><div class="section-copy">${escapeHtml(displayStatusLabel(detail.status))}</div></div>
            <div class="detail-card muted"><span class="micro-label">问题</span><div class="section-copy">${escapeHtml(detail.question_text || "-")}</div></div>
          </div>
          ${(dense.model_name || rerank.model_name) ? `
            <div class="detail-grid-2" style="margin-top:12px;">
              <div class="detail-card key">
                <span class="micro-label">Dense 模型</span>
                <div class="section-copy">${escapeHtml(dense.model_name || "-")}</div>
                <div class="section-copy" style="margin-top:8px;">fallback：${escapeHtml(String(!!dense.fallback_used))}</div>
              </div>
              <div class="detail-card warm">
                <span class="micro-label">Rerank 模型</span>
                <div class="section-copy">${escapeHtml(rerank.model_name || "-")}</div>
                <div class="section-copy" style="margin-top:8px;">fallback：${escapeHtml(String(!!rerank.fallback_used))}</div>
              </div>
            </div>
          ` : ""}
        </div>
      `;
    }
    if (kind === "feedback") {
      return `
        <div class="artifact-card warm">
          <h3>反馈详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">建议动作</span><div class="headline-value">${escapeHtml((detail.payload || {}).recommended_action || "-")}</div></div>
          <div class="detail-grid-2">
            <div class="detail-card muted"><span class="micro-label">反馈类型</span><div class="section-copy">${escapeHtml(detail.feedback_type || "-")}</div></div>
            <div class="detail-card muted"><span class="micro-label">关联问题</span><div class="section-copy">${escapeHtml(detail.question_text || detail.trace_id || "-")}</div></div>
          </div>
        </div>
      `;
    }
    if (kind === "draft") {
      const testPreview = ((detail.payload || {}).feedback_context || {}).source_payload?.test_execution_preview
        || (detail.payload || {}).test_execution_preview
        || null;
      return `
        <div class="artifact-card soft">
          <h3>方法草稿详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">拟沉淀对象</span><div class="headline-value">${escapeHtml(detail.proposed_rule_id || detail.rule_family || "-")}</div></div>
          <div class="detail-grid-2">
            <div class="detail-card muted"><span class="micro-label">草稿编号</span><div class="section-copy">${escapeHtml(detail.draft_id || "-")}</div></div>
            <div class="detail-card warm"><span class="micro-label">当前状态</span><div class="section-copy">${escapeHtml(displayStatusLabel(detail.status))}</div></div>
          </div>
          ${testPreview ? `
            <div class="detail-card key" style="margin-top:12px;">
              <span class="micro-label">试跑摘要</span>
              <div class="section-copy">runtime：${escapeHtml(((testPreview.runtime_preview || {}).status) || "-")} · agent：${escapeHtml(((testPreview.agent_preview || {}).status) || "skipped")}</div>
            </div>
          ` : ""}
        </div>
      `;
    }
    if (kind === "review") {
      const preview = (detail.payload || {}).test_execution_preview || {};
      const runtimePreview = preview.runtime_preview || {};
      const methodDraftPreview = preview.method_draft_preview || {};
      const agentPreview = preview.agent_preview || {};
      return `
        <div class="artifact-card rust">
          <h3>审核任务详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">审核状态</span><div class="headline-value">${escapeHtml(displayStatusLabel(detail.status))}</div></div>
          <div class="detail-grid-2">
            <div class="detail-card muted"><span class="micro-label">审核编号</span><div class="section-copy">${escapeHtml(detail.review_task_id || "-")}</div></div>
            <div class="detail-card warm"><span class="micro-label">审核人</span><div class="section-copy">${escapeHtml(detail.assignee || "待分配")}</div></div>
          </div>
          ${preview && Object.keys(preview).length ? `
            <div class="detail-grid-3">
              <div class="detail-card key">
                <span class="micro-label">runtime 试跑</span>
                <div class="section-copy">${escapeHtml(runtimePreview.status || "-")} · ${escapeHtml(runtimePreview.final_decision || "-")}</div>
              </div>
              <div class="detail-card warm">
                <span class="micro-label">方法草稿</span>
                <div class="section-copy">${escapeHtml(methodDraftPreview.skill_name || "暂无")}</div>
              </div>
              <div class="detail-card muted">
                <span class="micro-label">agent 试跑</span>
                <div class="section-copy">${escapeHtml(agentPreview.status || "skipped")}</div>
              </div>
            </div>
          ` : ""}
        </div>
      `;
    }
    if (kind === "version") {
      return `
        <div class="artifact-card olive">
          <h3>已发布版本详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">方法编号</span><div class="headline-value">${escapeHtml(detail.rule_id || "-")}</div></div>
          <div class="detail-grid-2">
            <div class="detail-card muted"><span class="micro-label">版本编号</span><div class="section-copy">${escapeHtml(detail.rule_version_id || "-")}</div></div>
            <div class="detail-card warm"><span class="micro-label">版本状态</span><div class="section-copy">${escapeHtml(displayStatusLabel(detail.status))}</div></div>
          </div>
        </div>
      `;
    }
    if (kind === "community") {
      const report = detail.report || {};
      const metaRule = detail.meta_rule || {};
      const findings = (report.findings || []).map((item) => `<div class="section-copy">- ${escapeHtml(item)}</div>`).join("");
      const focusTerms = (report.focus_terms || []).map((item) => chip(item, "ok")).join("");
      const representativeRules = (report.representative_rules || []).map((item) => chip(item, "gold")).join("");
      return `
        <div class="artifact-card focus">
          <h3>社区报告详情</h3>
          <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">标题</span><div class="headline-value">${escapeHtml(report.title || metaRule.label || detail.community_id || "-")}</div></div>
          <div class="detail-grid-3">
            <div class="detail-card muted"><span class="micro-label">社区编号</span><div class="section-copy">${escapeHtml(detail.community_id || "-")}</div></div>
            <div class="detail-card warm"><span class="micro-label">层级</span><div class="section-copy">${escapeHtml(detail.level ?? "-")}</div></div>
            <div class="detail-card muted"><span class="micro-label">规则数</span><div class="section-copy">${escapeHtml((detail.rule_ids || []).length)}</div></div>
          </div>
          <div class="detail-card soft" style="margin-top:12px;">
            <span class="micro-label">摘要</span>
            <div class="section-copy">${escapeHtml(report.summary || metaRule.summary || "-")}</div>
          </div>
          <div class="detail-grid-2" style="margin-top:12px;">
            <div class="detail-card olive">
              <span class="micro-label">关键发现</span>
              ${findings || `<div class="section-copy">暂无。</div>`}
            </div>
            <div class="detail-card rust">
              <span class="micro-label">元规则</span>
              <div class="section-copy">${escapeHtml(metaRule.label || "-")}</div>
              <div class="section-copy" style="margin-top:8px;">dominant family: ${escapeHtml(metaRule.dominant_rule_family || "-")}</div>
            </div>
          </div>
          ${focusTerms ? `<div class="detail-card key" style="margin-top:12px;"><span class="micro-label">关注词</span><div class="chip-row">${focusTerms}</div></div>` : ""}
          ${representativeRules ? `<div class="detail-card warm" style="margin-top:12px;"><span class="micro-label">代表规则</span><div class="chip-row">${representativeRules}</div></div>` : ""}
        </div>
      `;
    }
    return `<div class="artifact-card"><h3>详情</h3><div class="section-copy">${escapeHtml(kind)}</div></div>`;
  }

  function renderOpsCards(items, kind) {
    if (!items.length) {
      const emptyLabel = {
        run: "求解记录",
        feedback: "反馈",
        draft: "方法草稿",
        review: "审核任务",
        version: "已发布版本",
      }[kind] || kind;
      return `<div class="empty-state">暂无${escapeHtml(emptyLabel)}。</div>`;
    }
    return items.map((item) => `
      <button class="data-card" data-kind="${kind}" data-id="${escapeHtml(item.workspace_run_id || item.feedback_id || item.draft_id || item.review_task_id || item.rule_version_id || "")}">
        <h3>${escapeHtml(item.title || item.question_text || item.feedback_type || item.proposed_rule_id || item.rule_id || kind)}</h3>
        <div class="chip-row">
          ${item.route_decision ? chip(displayRouteLabel(item.route_decision, item.route_title)) : ""}
          ${item.status ? chip(displayStatusLabel(item.status), item.status === "published" ? "ok" : "") : ""}
          ${item.feedback_type ? chip(item.feedback_type, "warn") : ""}
          ${kind === "review" && (item.payload || {}).test_execution_preview ? chip("已带试跑摘要", "ok") : ""}
        </div>
        <div class="section-copy">${escapeHtml(item.scenario_id || item.rule_family || item.assignee || item.version_label || "")}</div>
      </button>
    `).join("");
  }

  function renderOpsSummary(kpis) {
    return kpis.map((item) => `
      <div class="summary-card">
        <span class="kpi-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `).join("");
  }

  function renderRuleGraphSummary(view) {
    const items = [
      { label: "图后端", value: view.graph_backend || "-" },
      { label: "规则数", value: view.rule_count || 0 },
      { label: "社区数", value: view.community_count || 0 },
      { label: "层级深度", value: view.hierarchy_depth || 0 },
      { label: "RAG Passages", value: view.rag_passage_count || 0 },
      { label: "当前指纹", value: view.fingerprint || "-" },
      { label: "Dense 默认", value: ((view.retrieval_models || {}).dense || {}).model_name || "-" },
      { label: "Rerank 默认", value: ((view.retrieval_models || {}).cross_rerank || {}).model_name || "-" },
    ];
    return items.map((item) => `
      <div class="summary-card">
        <span class="kpi-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `).join("");
  }

  function renderCommunityNode(node) {
    const childHtml = (node.children || []).map(renderCommunityNode).join("");
    const findingsCount = ((node.report || {}).findings || []).length;
    return `
      <div class="stack" style="margin-left:${Math.max(0, (node.level || 0) * 18)}px;">
        <button class="data-card" data-community-id="${escapeHtml(node.community_id || "")}">
          <h3>${escapeHtml(((node.report || {}).title) || ((node.meta_rule || {}).label) || (node.community_id || "community"))}</h3>
          <div class="chip-row">
            ${chip(`L${escapeHtml(node.level ?? 0)}`, "ok")}
            ${chip(`${escapeHtml((node.rule_ids || []).length)} rules`, "gold")}
            ${chip(`${escapeHtml(findingsCount)} findings`)}
          </div>
          <div class="section-copy">${escapeHtml(((node.report || {}).summary) || ((node.meta_rule || {}).summary) || "-")}</div>
        </button>
        ${childHtml}
      </div>
    `;
  }

  function renderRuleGraphTree(view) {
    const roots = view.roots || [];
    if (!roots.length) {
      return `<div class="empty-state">暂无 Rule Graph 产物。</div>`;
    }
    return roots.map(renderCommunityNode).join("");
  }

  function renderReviewActionResult(action, payload, selectedReviewId) {
    return `
      <div class="artifact-card focus">
        <h3>${action === "approve" ? "审核已批准" : "审核已驳回"}</h3>
        <div class="detail-card key" style="margin-top:12px;"><span class="micro-label">审核任务</span><div class="headline-value">${escapeHtml(payload.review_task_id || selectedReviewId || "-")}</div></div>
        ${action === "reject" && payload.rerun ? `
          <div class="detail-grid-3">
            <div class="detail-card warm">
              <span class="micro-label">重新探索</span>
              <div class="section-copy">${escapeHtml((payload.rerun.exploration_runtime || {}).exploration_trace_id || "-")}</div>
            </div>
            <div class="detail-card key">
              <span class="micro-label">新草稿</span>
              <div class="section-copy">${escapeHtml((((payload.rerun.promotion || {}).draft) || {}).draft_id || "-")}</div>
            </div>
            <div class="detail-card muted">
              <span class="micro-label">新审核</span>
              <div class="section-copy">${escapeHtml(((payload.rerun.review || {}).review_task_id) || "-")}</div>
            </div>
          </div>
        ` : ""}
        ${action === "reject" && payload.rerun_error ? `
          <div class="detail-card warm" style="margin-top:12px;"><span class="micro-label">自动重跑结果</span><div class="section-copy">${escapeHtml(payload.rerun_error)}</div></div>
        ` : ""}
      </div>
    `;
  }

  window.Phase1OpsRenderers = {
    renderOpsCards,
    renderOpsDetail,
    renderOpsSummary,
    renderRuleGraphSummary,
    renderRuleGraphTree,
    renderReviewActionResult,
  };
})();
