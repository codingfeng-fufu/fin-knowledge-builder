(function () {
  const { apiRequest, byId, chip, escapeHtml, displayRouteLabel } = window.Phase1UI;

  const SCRIPT_STEPS = [
    { actId: "act-answer", label: "第一段：问题与结果", copy: "当前案例解决了什么问题，给出了什么结果。", delay: 0 },
    { actId: "act-composition", label: "第二段：规则与证据", copy: "规则如何发挥作用，证据如何支撑结果。", delay: 2600 },
    { actId: "act-assets", label: "第三段：规则生长", copy: "规则不足时如何进入探索，并继续回到规则库。", delay: 6200 },
  ];
  const GROWTH_CASE_REF = "workspace/workspace_exploration_new_atomic";
  const REUSE_WORKSPACE_URL = "/workspace?case_ref=workspace/fund_docx_direct_warn&autorun=1&demo=1";
  const GROWTH_WORKSPACE_URL = `/workspace?case_ref=${encodeURIComponent(GROWTH_CASE_REF)}&autorun=1&demo=1`;
  const GROWTH_WORKFLOW_URL = "/workflow";
  const OPERATOR_MODE = new URLSearchParams(window.location.search).get("operator") === "1";

  const state = {
    flows: [],
    graph: null,
    communityMap: new Map(),
    selectedFlowId: null,
    recommendedFlowId: null,
    latestResult: null,
    progressTimer: null,
    presenterTimers: [],
    activeActId: "act-answer",
    runToken: 0,
    growthCase: null,
  };

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function stopProgress() {
    if (state.progressTimer) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }
  }

  function clearPresenterTimers() {
    state.presenterTimers.forEach((timer) => clearTimeout(timer));
    state.presenterTimers = [];
    const button = byId("presenterModeBtn");
    if (button) {
      button.disabled = false;
      button.textContent = "浏览当前案例";
    }
  }

  function setProgressState(stateName, label) {
    const panel = document.querySelector(".demo-progress-panel");
    if (!panel) return;
    panel.classList.remove("thinking", "done", "error");
    if (stateName) {
      panel.classList.add(stateName);
    }
    const badge = byId("demoProgressState");
    if (badge) {
      badge.textContent = label;
    }
  }

  function setScriptStatus(label) {
    const target = byId("scriptModeStatus");
    if (target) {
      target.textContent = label;
    }
  }

  function setActiveAct(actId, options = {}) {
    state.activeActId = actId;
    document.querySelectorAll("[data-act-target]").forEach((card) => {
      card.classList.toggle("active", card.dataset.actTarget === actId);
    });
    if (options.status) {
      setScriptStatus(options.status);
    }
    if (options.scroll) {
      byId(actId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function setProgress(percent, label) {
    byId("demoProgressFill").style.width = `${Math.max(0, Math.min(100, percent))}%`;
    byId("demoProgressLabel").textContent = label;
    byId("demoProgressPercent").textContent = `${Math.round(percent)}%`;
  }

  function startProgress() {
    stopProgress();
    setProgressState("thinking", "思考中");
    let percent = 8;
    const stages = [
      { at: 8, label: "思考中 · 正在装载案例剧本…" },
      { at: 24, label: "思考中 · 正在读取问题与材料…" },
      { at: 46, label: "思考中 · 正在组织证据与方法…" },
      { at: 72, label: "思考中 · 正在生成案例结果…" },
      { at: 88, label: "思考中 · 正在整理案例分析页…" },
    ];
    setProgress(percent, stages[0].label);
    state.progressTimer = setInterval(() => {
      percent = Math.min(92, percent + (percent < 50 ? 4 : 2));
      const stage = [...stages].reverse().find((item) => percent >= item.at) || stages[0];
      setProgress(percent, stage.label);
    }, 420);
  }

  function flattenCommunities(nodes, bucket = new Map()) {
    safeArray(nodes).forEach((node) => {
      if (node && node.community_id) {
        bucket.set(node.community_id, node);
      }
      flattenCommunities(node?.children, bucket);
    });
    return bucket;
  }

  function metricCard(label, value, copy = "", tone = "") {
    return `
      <div class="demo-metric-card ${tone}">
        <span class="kpi-label">${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        ${copy ? `<p>${escapeHtml(copy)}</p>` : ""}
      </div>
    `;
  }

  function actionLink(label, href, tone = "") {
    return `<a class="nav-link ${tone}" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`;
  }

  function formatMode(mode) {
    return {
      atomic_composition: "原子规则组合",
      direct: "规则直接复用",
      exploration: "探索增长",
    }[String(mode || "")] || String(mode || "-");
  }

  function formatRole(role) {
    return {
      derive_value: "提取事实",
      condition_check: "判断条件",
      final_decision: "生成结论",
    }[String(role || "")] || String(role || "执行步骤");
  }

  function formatStatus(ok) {
    return ok ? "通过" : "待确认";
  }

  function formatComparison(comparison) {
    if (!comparison) {
      return [];
    }
    return [
      { label: "状态一致", value: comparison.same_status },
      { label: "路径一致", value: comparison.same_route_decision },
      { label: "结论一致", value: comparison.same_final_decision },
      { label: "答案一致", value: comparison.same_final_answer },
    ];
  }

  function uniqueRuleIds(result) {
    const ids = safeArray(result?.source_rule_ids).filter(Boolean);
    if (!ids.length && result?.matched_rule_id) {
      ids.push(result.matched_rule_id);
    }
    return [...new Set(ids)];
  }

  function findRelevantCommunity(result) {
    if (!state.graph) {
      return null;
    }
    const ruleIds = uniqueRuleIds(result);
    const communityId = ruleIds
      .map((ruleId) => state.graph.community_by_rule_id?.[ruleId])
      .find(Boolean);
    return communityId ? state.communityMap.get(communityId) || null : null;
  }

  function renderHero() {
    const result = state.latestResult;
    const routeLabel = result ? displayRouteLabel(result.route_decision) : "等待运行";
    const graphLabel = state.graph
      ? `${state.graph.rule_count} 条规则 / ${state.graph.community_count} 个社区`
      : "规则图谱装载中";
    const consistencyLabel = result?.workflow?.rerun_summary?.all_consistent ? "多次重跑一致" : "等待验证";

    byId("heroFlowTitle").textContent = result?.title || "正在载入案例";
    byId("heroFlowCopy").textContent = result?.description || "当前页面会优先展示最能说明系统能力的典型案例。";
    byId("heroRouteValue").textContent = routeLabel;
    byId("heroAssetValue").textContent = graphLabel;
    byId("heroConsistencyValue").textContent = consistencyLabel;
    byId("demoHeroChips").innerHTML = [
      chip("案例分析页"),
      chip(`${state.flows.length || 0} 条案例路径`),
      chip(graphLabel, "gold"),
      result ? chip(`当前案例：${result.case_title || result.title}`) : chip("等待案例运行"),
    ].join("");
    byId("demoRunBtn").textContent = result ? `重新载入 ${result.title}` : "载入案例";
  }

  function renderScriptSteps() {
    const target = byId("demoScriptSteps");
    if (!target) {
      return;
    }
    target.innerHTML = SCRIPT_STEPS.map((step, index) => `
      <button class="demo-script-card ${step.actId === state.activeActId ? "active" : ""}" data-act-target="${escapeHtml(step.actId)}" type="button">
        <span class="demo-script-number">${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(step.label.replace(/^第.幕：/, ""))}</strong>
        <p>${escapeHtml(step.copy)}</p>
      </button>
    `).join("");
    bindScriptCards();
  }

  function renderSummary() {
    const result = state.latestResult;
    const comparison = result?.workflow?.rerun_summary?.comparison || null;
    const summaryItems = result
      ? [
        {
          label: "当前案例",
          value: result.title || result.flow_id || "-",
          copy: result.case_title || "",
        },
        {
          label: "执行路径",
          value: displayRouteLabel(result.route_decision),
          copy: result.composition_pattern || formatMode(result.mode),
        },
        {
          label: "最终结论",
          value: result.final_decision || "-",
          copy: result.final_answer || "",
        },
        {
          label: "一致性验证",
          value: result.workflow?.rerun_summary?.all_consistent ? "全部一致" : "待确认",
          copy: comparison ? `${formatStatus(comparison.same_route_decision)}路径 / ${formatStatus(comparison.same_final_answer)}答案` : "",
        },
      ]
      : [
        { label: "第一部分", value: "问题与结果", copy: "先看当前案例解决了什么问题。" },
        { label: "第二部分", value: "规则与证据", copy: "再看结果是如何形成的。" },
        { label: "第三部分", value: "规则生长", copy: "再看系统如何继续增长。" },
        { label: "当前状态", value: "等待载入", copy: "默认会优先载入推荐案例。" },
      ];

    byId("demoSummaryGrid").innerHTML = summaryItems.map((item) => `
      <div class="summary-card">
        <span class="kpi-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
        ${item.copy ? `<p class="section-copy">${escapeHtml(item.copy)}</p>` : ""}
      </div>
    `).join("");
  }

  function renderEngineBoard() {
    const reuse = state.latestResult;
    const growthCase = state.growthCase;
    const growthExpected = growthCase?.expected || {};
    const candidateAction = growthExpected.asset_pipeline?.recommended_action || "create_new_atomic_rule";

    byId("engineBoard").innerHTML = `
      <div class="demo-brief-card">
        <span class="eyebrow">能力一</span>
        <h3>规则复用引擎</h3>
        <p class="section-copy">先尝试直接复用已有规则；没有整题规则时，再用 atomic rules 受控组合。</p>
        <div class="chip-row">
          ${reuse ? chip(`当前案例：${reuse.title || reuse.flow_id}`, "ok") : chip("等待复用案例", "warn")}
          ${reuse ? chip(`路径：${displayRouteLabel(reuse.route_decision)}`) : ""}
        </div>
        <div class="demo-bullet-list">
          <div>优先命中已有规则，而不是从零生成答案。</div>
          <div>证据、规则链和执行时间线都可以直接展开。</div>
          <div>当前推荐案例展示的是这条处理链。</div>
        </div>
        <div class="button-row" style="margin-top:14px;">
          ${actionLink("打开复用样本工作台", REUSE_WORKSPACE_URL)}
        </div>
      </div>
      <div class="demo-brief-card growth">
        <span class="eyebrow">能力二</span>
        <h3>多智能体探索增长引擎</h3>
        <p class="section-copy">当规则不足或组合链失败时，系统启动多智能体探索，把当前问题长成候选规则草稿。</p>
        <div class="chip-row">
          ${growthCase ? chip(`增长样本：${growthCase.case_name || GROWTH_CASE_REF}`, "gold") : chip("等待增长样本", "warn")}
          ${growthExpected.route_decision ? chip(`路径：${displayRouteLabel(growthExpected.route_decision)}`, "warn") : ""}
          ${growthExpected.asset_pipeline?.auto_status ? chip(`治理状态：${growthExpected.asset_pipeline.auto_status}`) : ""}
        </div>
        <div class="demo-bullet-list">
          <div>该样本展示的是：规则不足 -> 多智能体探索。</div>
          <div>当前推荐动作：${escapeHtml(candidateAction)}。</div>
          <div>当前治理状态：${escapeHtml(growthExpected.asset_pipeline?.auto_status || "draft_promoted")}，说明它会继续进入草稿与审核链。</div>
        </div>
        <div class="button-row" style="margin-top:14px;">
          ${actionLink("打开增长样本工作台", GROWTH_WORKSPACE_URL)}
          ${actionLink("打开解释页", GROWTH_WORKFLOW_URL)}
        </div>
      </div>
    `;
  }

  function renderRecordingBoard() {
    byId("recordingBoard").style.display = OPERATOR_MODE ? "grid" : "none";
    byId("engineBoard").style.gridColumn = OPERATOR_MODE ? "" : "1 / -1";
    if (!OPERATOR_MODE) {
      return;
    }
    byId("recordingBoard").innerHTML = `
      <div class="demo-brief-card recording">
        <span class="eyebrow">浏览参考</span>
        <h3>推荐浏览顺序</h3>
        <div class="demo-sequence-list">
          <div class="demo-sequence-step">
            <strong>01. 先看案例总览</strong>
            <p>先理解系统如何用已有规则解决问题。</p>
          </div>
          <div class="demo-sequence-step">
            <strong>02. 再看问题求解工作台</strong>
            <p>查看真实工作台，而不是只停留在案例总览页。</p>
          </div>
          <div class="demo-sequence-step">
            <strong>03. 再看规则生长样本</strong>
            <p>查看系统在规则不足时如何进入探索与治理链。</p>
          </div>
          <div class="demo-sequence-step">
            <strong>04. 最后看系统说明页</strong>
            <p>查看规则复用与规则生长两条主线如何形成闭环。</p>
          </div>
        </div>
        <div class="button-row" style="margin-top:14px;">
          ${actionLink("复用样本", REUSE_WORKSPACE_URL)}
          ${actionLink("增长样本", GROWTH_WORKSPACE_URL)}
          ${actionLink("系统说明", GROWTH_WORKFLOW_URL)}
        </div>
      </div>
    `;
  }

  function renderFlowRail() {
    const target = byId("flowRail");
    if (!state.flows.length) {
      target.innerHTML = `<div class="demo-placeholder">暂无演示 flow。</div>`;
      return;
    }
    target.innerHTML = state.flows.map((flow) => `
      <button class="demo-flow-card ${flow.flow_id === state.selectedFlowId ? "active" : ""}" data-flow-id="${escapeHtml(flow.flow_id)}" type="button">
        <div class="demo-flow-card-top">
          <span class="demo-flow-title">${escapeHtml(flow.title)}</span>
          ${flow.recommended ? `<span class="demo-badge">Recommended</span>` : ""}
        </div>
        <div class="section-copy">${escapeHtml(flow.description)}</div>
        <div class="chip-row">
          ${chip(formatMode(flow.mode))}
          ${chip(flow.flow_id)}
        </div>
      </button>
    `).join("");
    target.querySelectorAll("[data-flow-id]").forEach((button) => {
      button.addEventListener("click", () => {
        runFlow(button.dataset.flowId);
      });
    });
  }

  function renderCaseScene() {
    const result = state.latestResult;
    if (!result) {
      byId("caseBrief").innerHTML = `<div class="demo-placeholder">等待案例载入。</div>`;
      byId("answerSpotlight").innerHTML = `<div class="demo-placeholder">播放后展示最终答案。</div>`;
      return;
    }

    const input = result.solution_view?.input || {};
    const facts = result.solution_view?.structured_understanding?.facts || {};
    const documents = safeArray(input.documents);
    const factEntries = Object.entries(facts).slice(0, 6);
    const evidenceCount = input.evidence_count ?? safeArray(input.evidence_refs).length;
    const ruleCount = uniqueRuleIds(result).length;
    const allConsistent = Boolean(result.workflow?.rerun_summary?.all_consistent);

    byId("caseBrief").innerHTML = `
      <span class="eyebrow">问题摘要</span>
      <h3>${escapeHtml(result.case_title || result.title || result.flow_id)}</h3>
      <p class="section-copy">${escapeHtml(result.question_text || "暂无问题文本。")}</p>
      <div class="chip-row">
        ${chip(`处理方式：${displayRouteLabel(result.route_decision)}`)}
        ${chip(`模式：${formatMode(result.mode)}`)}
        ${result.composition_pattern ? chip(`组合：${result.composition_pattern}`, "gold") : ""}
      </div>
      <div class="demo-doc-grid">
        <div class="demo-mini-panel">
          <span class="eyebrow">Materials</span>
          <div class="demo-mini-list">
            ${documents.map((doc) => `
              <div class="demo-list-row">
                <strong>${escapeHtml(doc.title || doc.doc_id || "文档")}</strong>
                <span>${escapeHtml(doc.doc_type || "-")}</span>
              </div>
            `).join("") || `<div class="demo-placeholder small">暂无材料。</div>`}
          </div>
        </div>
        <div class="demo-mini-panel">
          <span class="eyebrow">Grounded Facts</span>
          <div class="demo-fact-grid">
            ${factEntries.map(([key, value]) => `
              <div class="demo-fact-card">
                <span>${escapeHtml(key)}</span>
                <strong>${escapeHtml(String(value))}</strong>
              </div>
            `).join("") || `<div class="demo-placeholder small">暂无结构化事实。</div>`}
          </div>
        </div>
      </div>
    `;

    byId("answerSpotlight").innerHTML = `
      <span class="eyebrow">结果摘要</span>
      <h3>${escapeHtml(result.final_decision || "待生成结论")}</h3>
      <div class="demo-answer-quote">${escapeHtml(result.final_answer || "当前暂无最终答案。")}</div>
      <div class="chip-row">
        ${chip(`案例：${result.flow_id}`)}
        ${chip(`rule ids：${ruleCount}`)}
        ${chip(allConsistent ? "多次重跑一致" : "待补一致性验证", allConsistent ? "ok" : "warn")}
      </div>
      <div class="demo-trust-grid">
        <div class="demo-trust-card">
          <span>证据数量</span>
          <strong>${escapeHtml(evidenceCount)}</strong>
        </div>
        <div class="demo-trust-card">
          <span>方法单元</span>
          <strong>${escapeHtml(ruleCount)}</strong>
        </div>
        <div class="demo-trust-card">
          <span>重跑验证</span>
          <strong>${escapeHtml(allConsistent ? "一致" : "待确认")}</strong>
        </div>
      </div>
      <p class="section-copy demo-answer-note">
        这一部分只说明一件事：系统已经在真实文档条件下完成了当前问题的求解。
      </p>
    `;
  }

  function renderCompositionScene() {
    const result = state.latestResult;
    if (!result) {
      byId("routeNarrative").innerHTML = `<div class="demo-placeholder">等待路径说明。</div>`;
      byId("ruleChain").innerHTML = `<div class="demo-placeholder">等待规则链路。</div>`;
      byId("retrievalProof").innerHTML = `<div class="demo-placeholder">等待匹配证明。</div>`;
      byId("executionTimeline").innerHTML = `<div class="demo-placeholder">等待执行时间线。</div>`;
      byId("evidencePanel").innerHTML = `<div class="demo-placeholder">等待证据摘录。</div>`;
      return;
    }

    const route = result.solution_view?.route || {};
    const retrieval = result.solution_view?.retrieval || {};
    const execution = result.solution_view?.execution || {};
    const timeline = safeArray(execution.timeline);
    const candidateRules = safeArray(retrieval.candidate_rules);
    const evidenceRefs = safeArray(result.solution_view?.input?.evidence_refs);
    const ruleIds = uniqueRuleIds(result);
    const comparison = result.workflow?.rerun_summary?.comparison || {};

    byId("routeNarrative").innerHTML = `
      <span class="eyebrow">处理路径</span>
      <h3>${escapeHtml(displayRouteLabel(result.route_decision))}</h3>
      <p class="section-copy">${escapeHtml(route.explanation || "当前暂无路径说明。")}</p>
      <p class="section-copy">${escapeHtml(result.route_decision === "exploration" ? "当前案例已经进入多智能体探索增长链。" : "当前案例仍停留在规则复用链。只有复用链覆盖不到问题时，系统才会切到多智能体探索。")}</p>
      <div class="chip-row">
        ${chip(`组合模式：${route.composition_pattern || formatMode(result.mode)}`)}
        ${result.matched_rule_id ? chip(`命中规则：${result.matched_rule_id}`) : chip("未命中完整规则")}
        ${chip(`候选规则：${candidateRules.length}`)}
      </div>
      <div class="demo-check-row">
        ${formatComparison(comparison).map((item) => `
          <div class="demo-check-card">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(formatStatus(item.value))}</strong>
          </div>
        `).join("")}
      </div>
    `;

    byId("ruleChain").innerHTML = `
      <span class="eyebrow">规则链路</span>
      <h3>系统用了哪些规则与方法单元</h3>
      <div class="demo-rule-row">
        ${ruleIds.map((ruleId, index) => {
          const sampleStep = timeline.find((step) => step.rule_id === ruleId);
          return `
            <div class="demo-rule-card">
              <div class="demo-rule-index">${index + 1}</div>
              <strong>${escapeHtml(ruleId)}</strong>
              <span>${escapeHtml(formatRole(sampleStep?.composition_role))}</span>
              <p>${escapeHtml(sampleStep?.goal || "用于本次求解链路。")}</p>
            </div>
          `;
        }).join("") || `<div class="demo-placeholder">当前没有可展示的规则链。</div>`}
      </div>
    `;

    byId("retrievalProof").innerHTML = [
      metricCard("候选规则", String(retrieval.asset_counts?.candidate_total ?? candidateRules.length), "系统先召回已有规则，再决定是直接复用、组合复用，还是进入增长链。"),
      metricCard("Atomic 候选", String(retrieval.asset_counts?.atomic_candidates ?? 0), "Atomic 单元足够时，系统会优先尝试组合，而不是立刻进入探索。"),
      metricCard("Full Rule 候选", String(retrieval.asset_counts?.composite_or_full_candidates ?? 0), "整题规则够强时，会走最短复用路径。"),
      metricCard("运行期规则数", String(result.workflow?.rerun_summary?.runtime_rule_count ?? 0), "复用链覆盖不到问题时，下一步才会切到多智能体探索增长链。"),
    ].join("");

    byId("executionTimeline").innerHTML = `
      <span class="eyebrow">执行过程</span>
      <h3>结果是怎样一步步形成的</h3>
      <div class="demo-timeline-list">
        ${timeline.map((step, index) => `
          <div class="demo-timeline-item">
            <div class="demo-timeline-index">${index + 1}</div>
            <div>
              <strong>${escapeHtml(step.step_id || step.rule_id || "step")}</strong>
              <div class="chip-row">
                ${chip(formatRole(step.composition_role))}
                ${step.rule_id ? chip(step.rule_id) : ""}
              </div>
              <p>${escapeHtml(step.goal || "暂无步骤说明。")}</p>
            </div>
          </div>
        `).join("") || `<div class="demo-placeholder">当前没有执行时间线。</div>`}
      </div>
    `;

    byId("evidencePanel").innerHTML = `
      <span class="eyebrow">关键证据</span>
      <h3>证据没有藏在日志里</h3>
      <div class="demo-evidence-list">
        ${evidenceRefs.map((item) => `
          <div class="demo-evidence-card">
            <strong>${escapeHtml(item.doc_id || "evidence")}</strong>
            <p>${escapeHtml(item.text || "暂无证据片段。")}</p>
          </div>
        `).join("") || `<div class="demo-placeholder">当前没有证据摘录。</div>`}
      </div>
    `;
  }

  function renderAssetScene() {
    const result = state.latestResult;
    if (!state.graph) {
      byId("assetSnapshot").innerHTML = `<div class="demo-placeholder">等待规则图谱。</div>`;
      byId("communityCard").innerHTML = `<div class="demo-placeholder">等待方法社区摘要。</div>`;
      byId("feedbackCard").innerHTML = `<div class="demo-placeholder">等待沉淀动作说明。</div>`;
      byId("takeawaysCard").innerHTML = `<div class="demo-placeholder">等待演示结论。</div>`;
      return;
    }

    const comparison = result?.workflow?.rerun_summary?.comparison || {};
    const relevantCommunity = result ? findRelevantCommunity(result) : null;
    const feedback = result?.feedback_defaults || {};

    byId("assetSnapshot").innerHTML = [
      metricCard("规则总数", String(state.graph.rule_count || 0), "这不是单次问答的缓存，而是方法网络。"),
      metricCard("社区数量", String(state.graph.community_count || 0), "说明规则已经开始按相似能力聚类。"),
      metricCard("叶子社区", String(state.graph.leaf_community_count || 0), "更像执行邻域，便于解释当前案例落在哪。"),
      metricCard("当前案例一致性", result?.workflow?.rerun_summary?.all_consistent ? "全部一致" : "待确认", comparison.same_final_answer ? "同案重跑，答案一致。" : "还需要更稳定的验证。"),
    ].join("");

    byId("communityCard").innerHTML = relevantCommunity ? `
      <span class="eyebrow">相关规则社区</span>
      <h3>${escapeHtml(relevantCommunity.title || relevantCommunity.community_id || "相关方法社区")}</h3>
      <p class="section-copy">${escapeHtml(relevantCommunity.summary || "当前没有更多社区摘要。")}</p>
      <div class="demo-bullet-list">
        ${safeArray(relevantCommunity.findings).slice(0, 4).map((item) => `<div>${escapeHtml(item)}</div>`).join("")}
      </div>
      <div class="chip-row">
        ${safeArray(relevantCommunity.focus_terms).slice(0, 6).map((item) => chip(item)).join("")}
      </div>
    ` : `
      <span class="eyebrow">Relevant Community</span>
      <h3>当前案例还没有明确的社区落点</h3>
      <p class="section-copy">这并不影响 demo 主线，只是说明方法图谱还可以继续被组织得更细。</p>
    `;

    byId("feedbackCard").innerHTML = `
      <span class="eyebrow">规则生长</span>
      <h3>规则库会怎样继续生长</h3>
      <div class="demo-bullet-list">
        <div>当前展示链：${escapeHtml(displayRouteLabel(result?.route_decision))}</div>
        <div>feedback type：${escapeHtml(feedback.feedback_type || "-")}</div>
        <div>route decision：${escapeHtml(feedback.route_decision || "-")}</div>
        <div>关联规则：${escapeHtml(safeArray(feedback.rule_ids).join(", ") || "-")}</div>
        <div>trace id：${escapeHtml(feedback.trace_id || "-")}</div>
      </div>
      <p class="section-copy">
        当前案例先展示规则复用；当复用链覆盖不到问题时，系统会启动多智能体探索，把候选规则送进 feedback、草稿、审核和发布闭环。
      </p>
      ${state.growthCase ? `
        <div class="detail-card warm" style="margin-top:12px;">
          <span class="micro-label">增长样本快照</span>
          <div class="section-copy">${escapeHtml(state.growthCase.question_text || "")}</div>
          <div class="chip-row" style="margin-top:10px;">
            ${chip(`预期路径：${displayRouteLabel(state.growthCase.expected?.route_decision)}`, "warn")}
            ${chip(`自动状态：${state.growthCase.expected?.asset_pipeline?.auto_status || "-"}`)}
          </div>
        </div>
      ` : ""}
      <div class="button-row" style="margin-top:14px;">
        ${actionLink("打开增长样本工作台", GROWTH_WORKSPACE_URL)}
        ${actionLink("打开系统说明页", GROWTH_WORKFLOW_URL)}
      </div>
    `;

    byId("takeawaysCard").innerHTML = `
      <span class="eyebrow">页面总结</span>
      <h3>这页最重要的三件事</h3>
      <div class="demo-bullet-list">
        <div>系统会先复用已有规则，而不是一上来就从零生成答案。</div>
        <div>已有规则不够时，它会继续进入多智能体探索，生成候选规则草稿。</div>
        <div>审核通过后的新规则会回到规则库，供下一次直接复用。</div>
      </div>
    `;
  }

  function renderAll() {
    renderHero();
    renderScriptSteps();
    renderSummary();
    renderEngineBoard();
    renderRecordingBoard();
    renderFlowRail();
    renderCaseScene();
    renderCompositionScene();
    renderAssetScene();
  }

  async function runFlow(flowId, options = {}) {
    if (!flowId) {
      return null;
    }
    if (!options.keepPresenter) {
      clearPresenterTimers();
      setActiveAct("act-answer", { status: "手动模式" });
    }
    const token = ++state.runToken;
    state.selectedFlowId = flowId;
    renderFlowRail();
    startProgress();
    let completed = false;
    try {
      const payload = await apiRequest("prototype.flow.run", { flow_id: flowId });
      if (token !== state.runToken) {
        return null;
      }
      state.latestResult = payload;
      setProgress(100, "导演版已就绪");
      setProgressState("done", "已完成");
      renderAll();
      completed = true;
      return payload;
    } catch (error) {
      if (token !== state.runToken) {
        return null;
      }
      setProgress(100, "播放失败");
      setProgressState("error", "载入失败");
      byId("answerSpotlight").innerHTML = `
        <span class="eyebrow">Playback Error</span>
        <h3>演示案例运行失败</h3>
        <p class="section-copy">${escapeHtml(error.message || String(error))}</p>
      `;
      return null;
    } finally {
      if (!completed && !document.querySelector(".demo-progress-panel.error")) {
        setProgressState("", "待机");
      }
      stopProgress();
    }
  }

  async function playPresenterMode() {
    const flowId = state.selectedFlowId || state.recommendedFlowId;
    if (!flowId) {
      setScriptStatus("暂无可播放案例");
      return;
    }
    clearPresenterTimers();
    const button = byId("presenterModeBtn");
    button.disabled = true;
    button.textContent = "正在浏览案例…";
    setScriptStatus("正在载入案例");

    const payload = await runFlow(flowId, { keepPresenter: true });
    if (!payload) {
      button.disabled = false;
      button.textContent = "按比赛三幕播放";
      return;
    }

    SCRIPT_STEPS.forEach((step) => {
      const timer = setTimeout(() => {
        setActiveAct(step.actId, { scroll: true, status: step.label });
      }, step.delay);
      state.presenterTimers.push(timer);
    });

    state.presenterTimers.push(setTimeout(() => {
      setScriptStatus("三幕播放完成");
      button.disabled = false;
      button.textContent = "重新浏览案例";
    }, 9000));
  }

  function bindScriptCards() {
    document.querySelectorAll("[data-act-target]").forEach((card) => {
      card.addEventListener("click", () => {
        clearPresenterTimers();
        const target = card.dataset.actTarget;
        const step = SCRIPT_STEPS.find((item) => item.actId === target);
        setActiveAct(target, { scroll: true, status: step?.label || "手动跳转" });
      });
    });
  }

  function bindStaticActions() {
    byId("presenterModeBtn").addEventListener("click", playPresenterMode);
    byId("demoRunBtn").addEventListener("click", () => {
      runFlow(state.selectedFlowId || state.recommendedFlowId);
    });
    byId("jumpCompositionBtn").addEventListener("click", () => {
      byId("act-composition").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    byId("jumpAssetBtn").addEventListener("click", () => {
      byId("act-assets").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function init() {
    document.body.classList.toggle("operator-mode", OPERATOR_MODE);
    bindStaticActions();
    setProgressState("", "待机");
    renderAll();
    try {
      const [flowPayload, graphPayload, growthCase] = await Promise.all([
        apiRequest("prototype.flow.list"),
        apiRequest("factory.rule_graph.view"),
        apiRequest("demo.workspace_case.get", { case_ref: GROWTH_CASE_REF }).catch(() => null),
      ]);
      state.flows = safeArray(flowPayload.flows);
      state.graph = graphPayload;
      state.growthCase = growthCase;
      state.communityMap = flattenCommunities(graphPayload.roots);
      state.recommendedFlowId = flowPayload.recommended_flow_id || state.flows[0]?.flow_id || null;
      state.selectedFlowId = state.recommendedFlowId;
      renderAll();
      if (state.recommendedFlowId) {
        runFlow(state.recommendedFlowId);
      }
    } catch (error) {
      setProgress(100, "初始化失败");
      byId("demoSummaryGrid").innerHTML = `
        <div class="summary-card">
          <span class="kpi-label">初始化失败</span>
          <strong>${escapeHtml(error.message || String(error))}</strong>
        </div>
      `;
    }
  }

  init();
})();
