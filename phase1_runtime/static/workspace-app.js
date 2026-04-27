(function () {
  const {
    apiRequest,
    byId,
    chip,
    copyText,
    escapeHtml,
    fileToMaterial,
    saveWorkspaceSnapshot,
  } = window.Phase1UI;
  const {
    renderDecisionEvidence,
    renderDecisionStatus,
    formatAnswerMarkup,
    renderAgent,
    renderAnswerMeta,
    renderAnswerStatus,
    renderAssets,
    renderBindings,
    renderContext,
    renderDefaultDecisionSummary,
    renderDecisionSummary,
    renderEvidence,
    renderFileList,
    renderHeroStatusChips,
    renderInternalPanel,
    renderRelatedQuestionList,
    renderSampleList,
    renderScenarioOptions: renderScenarioOptionsHtml,
    renderSkill,
  } = window.Phase1WorkspaceRenderers;

  const state = {
    scenarios: [],
    sampleCases: [],
    selectedSample: null,
    defaultSampleRef: null,
    startIntent: "sample",
    uploadedFiles: [],
    latestPayload: null,
    progressTimer: null,
    activeDetailTab: "evidence",
    reviewActionPending: false,
    explorationOverlayTaskId: "",
    launchConfig: {
      caseRef: null,
      autorun: false,
      demoMode: false,
      operatorMode: false,
    },
  };

  function readLaunchConfig() {
    const params = new URLSearchParams(window.location.search);
    const caseRef = params.get("case_ref");
    const autorun = ["1", "true", "yes"].includes(String(params.get("autorun") || "").toLowerCase());
    const demoMode = ["1", "true", "yes"].includes(String(params.get("demo") || "").toLowerCase());
    const operatorMode = ["1", "true", "yes"].includes(String(params.get("operator") || "").toLowerCase());
    return {
      caseRef: caseRef || null,
      autorun,
      demoMode,
      operatorMode,
    };
  }

  function selectedSampleMaterials() {
    return state.selectedSample?.materials || [];
  }

  function syncQuestionFieldState() {
    const questionInput = byId("questionInput");
    const questionStatus = byId("questionStatus");
    if (!questionInput) return;
    questionInput.style.height = "auto";
    questionInput.style.height = `${Math.max(154, questionInput.scrollHeight)}px`;
    const hasValue = Boolean(String(questionInput.value || "").trim());
    questionInput.classList.toggle("textarea-loaded", hasValue);
    if (!questionStatus) return;
    if (!hasValue) {
      questionStatus.textContent = "载入样本后，这里会显示当前问题。";
      questionStatus.classList.remove("strong");
      return;
    }
    const isFeatured = Boolean(state.selectedSample?.featured);
    questionStatus.textContent = isFeatured
      ? "当前重点任务已载入，运行时将先提取规则字段，再进行代码核验。"
      : "当前样本问题已载入，你可以直接运行，或继续手动修改问法。";
    questionStatus.classList.toggle("strong", true);
  }

  function activeSolveInputs() {
    if (state.startIntent === "upload") {
      return state.uploadedFiles;
    }
    return selectedSampleMaterials();
  }

  function canRunCurrentSolve() {
    if (isUploadMode()) {
      return activeSolveInputs().length > 0;
    }
    return Boolean(state.selectedSample);
  }

  function isUploadMode() {
    return state.startIntent === "upload";
  }

  function renderStartPathCards() {
    byId("sampleStartBtn").classList.toggle("active", !isUploadMode());
    byId("uploadStartBtn").classList.toggle("active", isUploadMode());
  }

  function renderStartModeStatus() {
    const target = byId("startModeStatus");
    if (!target) return;
    if (isUploadMode()) {
      const hasFiles = state.uploadedFiles.length > 0;
      target.innerHTML = `
        <div class="mini-note">
          <strong>当前模式：上传自己的文件</strong>
          <span>${hasFiles ? "系统将只使用你刚才选择的本地文件；如果问题沿用了样本问法，记得一起改成自己的业务问题。" : "请先选择本地文件。样本问题仍保留在输入框里，你可以继续修改，但在选好文件之前不会执行。"}</span>
        </div>
      `;
      return;
    }
    const sampleTitle = state.selectedSample?.case_name || state.selectedSample?.case_ref || "推荐样本";
    const isFeatured = Boolean(state.selectedSample?.featured);
    target.innerHTML = `
      <div class="mini-note">
        <strong>当前模式：推荐样本${isFeatured ? " · 重点样本已载入" : ""}</strong>
        <span>${state.selectedSample ? `${isFeatured ? "当前已载入重点样本 " : "当前已载入 "}${escapeHtml(sampleTitle)}，${isFeatured ? "点击下方“运行重点样本”即可开始这次复杂规则与代码核验任务。" : "可以直接运行；如果你上传自己的文件，系统会切换到上传模式。"}`
          : "点击左侧推荐样本，或直接使用默认样本开始。你也可以随时切到上传模式。 "}</span>
      </div>
    `;
  }

  function stopProgress() {
    if (state.progressTimer) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }
  }

  function setProgressState(stateName, label) {
    const panel = document.querySelector(".progress-panel");
    if (!panel) return;
    panel.classList.remove("thinking", "done", "error");
    if (stateName) {
      panel.classList.add(stateName);
    }
    const badge = byId("runProgressState");
    if (badge) {
      badge.textContent = label;
    }
  }

  function setProgress(percent, label) {
    byId("runProgressFill").style.width = `${Math.max(0, Math.min(100, percent))}%`;
    byId("runProgressLabel").textContent = label;
    byId("runProgressPercent").textContent = `${Math.round(percent)}%`;
  }

  function startProgress() {
    stopProgress();
    setProgressState("thinking", "思考中");
    let percent = 6;
    const stages = [
      { at: 8, label: "思考中 · 正在接收问题与材料…" },
      { at: 22, label: "思考中 · 正在理解文档内容…" },
      { at: 42, label: "思考中 · 正在构建问题上下文…" },
      { at: 58, label: "思考中 · 正在匹配可用方法…" },
      { at: 72, label: "思考中 · 正在整理本次解法…" },
      { at: 88, label: "思考中 · 正在生成最终答案…" },
    ];
    setProgress(percent, stages[0].label);
    state.progressTimer = setInterval(() => {
      percent = Math.min(90, percent + (percent < 40 ? 4 : percent < 70 ? 3 : 1.5));
      const stage = [...stages].reverse().find((item) => percent >= item.at) || stages[0];
      setProgress(percent, stage.label);
    }, 500);
  }

  function renderHeroStatus(backend) {
    const chips = [
      renderHeroStatusChips(backend),
      state.launchConfig.demoMode && state.launchConfig.operatorMode ? chip("录屏模式：已关闭 live LLM", "warn") : "",
    ].filter(Boolean).join("");
    byId("heroChips").innerHTML = chips;
  }

  function renderScenarioOptions(items) {
    byId("scenarioSelect").innerHTML = renderScenarioOptionsHtml(items);
  }

  function renderFiles() {
    if (!isUploadMode() && state.selectedSample && !activeSolveInputs().length) {
      const expectedRoute = state.selectedSample.expected?.route_decision;
      byId("fileList").innerHTML = `
        <div class="sample-card">
          <h3>当前样本不依赖上传材料</h3>
          <div class="meta-strip">
            ${chip(expectedRoute ? `预期路径：${expectedRoute}` : "样本模式")}
            ${chip("不依赖上传材料", "warn")}
          </div>
          <div class="section-copy">该样本会直接根据当前问题触发规则匹配与后续流程，不需要额外上传文档。</div>
        </div>
      `;
      return;
    }
    byId("fileList").innerHTML = renderFileList(activeSolveInputs());
  }

  function updateSolveButtonState() {
    const button = byId("solveBtn");
    const ready = canRunCurrentSolve();
    button.disabled = !ready;
    if (!ready) {
      button.textContent = isUploadMode() ? "请先选择文件" : "请先载入样本";
      return;
    }
    if (isUploadMode()) {
      button.textContent = "运行我的文件";
      return;
    }
    button.textContent = state.selectedSample?.featured ? "运行重点样本" : "运行推荐样本";
  }

  function resetWorkspaceView(message = "选择推荐样本，或上传文件后点击“运行当前问题”。") {
    state.latestPayload = null;
    byId("decisionSummary").innerHTML = renderDefaultDecisionSummary();
    byId("answerStatus").innerHTML = `<span class="chip">等待运行</span>`;
    byId("answerView").classList.remove("compact");
    byId("answerView").dataset.rawAnswer = "";
    byId("answerView").innerHTML = `<p>${escapeHtml(message)}</p>`;
    byId("answerMeta").textContent = "当前页面将展示最终回答、结论状态和主要证据。";
    if (byId("copyAnswerStatus")) {
      byId("copyAnswerStatus").textContent = "";
    }
    byId("evidenceList").innerHTML = `<div class="empty-state">尚无证据。</div>`;
    byId("detailSurface").innerHTML = `<div class="empty-state">运行后展示详情。</div>`;
    setProgress(0, "等待运行");
    setProgressState("", "待机");
    syncQuestionFieldState();
  }

  async function loadSample(caseRef) {
    const data = await apiRequest("demo.workspace_case.get", { case_ref: caseRef });
    state.startIntent = "sample";
    state.selectedSample = data;
    byId("questionInput").value = data.question_text || "";
    syncQuestionFieldState();
    byId("scenarioSelect").value = data.scenario_id || "";
    renderSamples();
    renderRelatedQuestions();
    renderStartPathCards();
    renderStartModeStatus();
    renderFiles();
    updateSolveButtonState();
    resetWorkspaceView(
      data.expected?.route_decision === "exploration"
        ? "样本已载入。系统将根据当前问题继续判断是否进入多智能体探索。"
        : data.featured
          ? "重点样本已载入。当前问题会要求系统先提取规则字段，再进行代码核验。点击“运行重点样本”开始。"
          : "推荐样本已载入。你可以直接运行，也可以上传自己的文件替换。"
    );
    const questionInput = byId("questionInput");
    if (questionInput) {
      questionInput.classList.remove("result-fresh");
      void questionInput.offsetWidth;
      questionInput.classList.add("result-fresh");
      window.setTimeout(() => questionInput.classList.remove("result-fresh"), 1200);
    }
  }

  function renderSamples() {
    const target = byId("sampleList");
    target.innerHTML = renderSampleList(state.sampleCases, state.selectedSample?.case_ref || "");
  }

  function renderRelatedQuestions() {
    const target = byId("relatedQuestionList");
    const currentQuestion = String(state.selectedSample?.question_text || "").trim();
    const questions = [...new Set((state.selectedSample?.related_questions || [])
      .map((item) => String(item || "").trim())
      .filter((item) => item && item !== currentQuestion))];
    target.innerHTML = renderRelatedQuestionList(questions);
  }

  function closeExplorationOverlay() {
    state.explorationOverlayTaskId = "";
    stopExplorationPoll();
    const overlay = byId("explorationOverlay");
    const frame = byId("explorationWorkbenchFrame");
    const loading = byId("explorationOverlayLoading");
    if (overlay) overlay.hidden = true;
    if (frame) frame.src = "about:blank";
    if (loading) loading.hidden = true;
  }

  function maybeOpenExplorationOverlay(payload) {
    if (!payload || payload.route_decision !== "exploration") return;
    const taskId = payload.exploration_links?.task_id || payload.exploration_runtime?.external_task?.task_id;
    if (!taskId || state.explorationOverlayTaskId === taskId) return;
    state.explorationOverlayTaskId = taskId;
    const overlay = byId("explorationOverlay");
    const frame = byId("explorationWorkbenchFrame");
    const reportLink = byId("explorationOverlayReportLink");
    const loading = byId("explorationOverlayLoading");
    if (reportLink) reportLink.href = `/discovery/report/${taskId}`;
    // Show overlay FIRST so the iframe is visible to the browser.
    // Some browsers defer navigation on iframes inside display:none parents,
    // causing the iframe to appear blank/stuck.
    if (overlay) overlay.hidden = false;
    // Show loading indicator; hide it once the iframe content loads
    if (loading) loading.hidden = false;
    if (frame) {
      // Remove previous onload handler and set new one
      frame.onload = function () {
        if (loading) loading.hidden = true;
      };
      frame.src = `/discovery?taskId=${encodeURIComponent(taskId)}&embed=1`;
    }
  }

  function bindAnswerCopyActions() {
    const copyButton = byId("copyAnswerBtn");
    const copyStatus = byId("copyAnswerStatus");
    const answerView = byId("answerView");
    if (copyButton && answerView) {
      copyButton.onclick = async () => {
        const rawAnswer = answerView.dataset.rawAnswer || "";
        if (!rawAnswer.trim()) {
          if (copyStatus) copyStatus.textContent = "当前没有可复制内容";
          return;
        }
        try {
          await copyText(rawAnswer);
          if (copyStatus) copyStatus.textContent = "已复制";
          window.setTimeout(() => {
            if (copyStatus) copyStatus.textContent = "";
          }, 1400);
        } catch (_error) {
          if (copyStatus) copyStatus.textContent = "复制失败";
        }
      };
    }
    document.querySelectorAll("[data-copy-code]").forEach((button) => {
      button.onclick = async () => {
        const code = button.dataset.copyCode || "";
        try {
          await copyText(code);
          const original = button.dataset.originalLabel || button.textContent || "复制代码";
          button.dataset.originalLabel = original;
          button.textContent = "已复制";
          window.setTimeout(() => {
            button.textContent = original;
          }, 1200);
        } catch (_error) {
          button.textContent = "复制失败";
          window.setTimeout(() => {
            button.textContent = "复制代码";
          }, 1200);
        }
      };
    });
  }

  function renderAnswer(payload) {
    const finalAnswer = String(payload.final_answer || "").trim();
    const answerView = byId("answerView");
    byId("answerStatus").innerHTML = renderAnswerStatus(payload);
    answerView.classList.toggle("compact", finalAnswer.length > 220 || finalAnswer.includes("\n"));
    answerView.dataset.rawAnswer = finalAnswer;
    answerView.innerHTML = formatAnswerMarkup(finalAnswer);
    if (window.hljs) {
      answerView.querySelectorAll("pre code").forEach((block) => {
        window.hljs.highlightElement(block);
      });
    }
    byId("answerMeta").innerHTML = renderAnswerMeta(payload);
    bindAnswerCopyActions();
  }

  function buildExplorationLinksFromRuntime(explorationRuntime) {
    const externalTask = explorationRuntime?.external_task || {};
    const taskId = externalTask.task_id;
    if (!taskId) return null;
    const frontendBaseUrl = "";
    const backendBaseUrl = "";
    return {
      task_id: taskId,
      frontend_base_url: frontendBaseUrl,
      backend_base_url: backendBaseUrl,
      workbench_url: `${frontendBaseUrl}/discovery`,
      report_url: `${frontendBaseUrl}/discovery/report/${taskId}`,
      backend_task_url: `${backendBaseUrl}/api/discovery/tasks/${taskId}`,
      backend_result_url: `${backendBaseUrl}/api/discovery/tasks/${taskId}/result`,
    };
  }

  function buildExplorationLinksFromTask(task) {
    const taskId = task?.task_id;
    if (!taskId) return null;
    const frontendBaseUrl = "";
    const backendBaseUrl = "";
    return {
      task_id: taskId,
      frontend_base_url: frontendBaseUrl,
      backend_base_url: backendBaseUrl,
      workbench_url: `${frontendBaseUrl}/discovery`,
      report_url: `${frontendBaseUrl}/discovery/report/${taskId}`,
      backend_task_url: `${backendBaseUrl}/api/discovery/tasks/${taskId}`,
      backend_result_url: `${backendBaseUrl}/api/discovery/tasks/${taskId}/result`,
    };
  }

  async function hydrateExplorationLinks(payload) {
    if (!payload || payload.route_decision !== "exploration") {
      return;
    }
    if (payload.exploration_links?.report_url || payload._explorationLinkLookupPending) {
      return;
    }
    payload._explorationLinkLookupPending = true;
    renderWorkspace(payload);
    try {
      const response = await fetch("http://127.0.0.1:5001/api/discovery/tasks?limit=50");
      if (!response.ok) {
        return;
      }
      const json = await response.json();
      const items = json.data || [];
      const target = items.find((item) => item?.metadata?.phase1_trace_id === payload.trace_id)
        || items.find((item) =>
          item?.metadata?.source === "phase1_runtime"
          && item?.metadata?.scenario_id === payload.scenario_id
          && item?.query === payload.question_text
        );
      if (target?.task_id) {
        payload.exploration_links = buildExplorationLinksFromTask(target);
        payload.exploration_runtime = payload.exploration_runtime || {};
        payload.exploration_runtime.external_task = target;
      }
    } catch (_error) {
      // Keep the workbench link visible even if fallback report lookup fails.
    } finally {
      payload._explorationLinkLookupPending = false;
      if (state.latestPayload === payload) {
        renderWorkspace(payload);
      }
    }
  }

  async function ensureWorkspaceReview(payload) {
    const pipeline = payload.asset_pipeline || {};
    if (pipeline.review?.review_task_id) {
      return pipeline.review;
    }
    let draft = pipeline.promotion?.draft || null;
    if (!draft && pipeline.feedback?.feedback_id) {
      const promotion = await apiRequest("factory.feedback.promote_to_draft", {
        feedback_id: pipeline.feedback.feedback_id,
      });
      pipeline.promotion = promotion;
      draft = promotion.draft || null;
    }
    if (!draft?.draft_id) {
      throw new Error("当前探索结果还没有形成可审核的方法草稿。");
    }
    const review = await apiRequest("factory.review.create", {
      draft_id: draft.draft_id,
    });
    pipeline.review = review;
    payload.asset_pipeline = pipeline;
    return review;
  }

  function applyPreviewAnswer(payload, preview) {
    if (!preview) return;
    const agentPreview = preview.agent_preview || {};
    const runtimePreview = preview.runtime_preview || {};
    const finalText = String(agentPreview.final_text || runtimePreview.final_answer || "").trim();
    if (finalText) {
      payload.final_answer = finalText;
      payload.answer_engine = agentPreview.status === "completed" ? "super_agent" : "runtime";
      payload.display_decision_text = "已生成探索性答案";
    }
    if (runtimePreview.final_decision) {
      payload.final_decision = runtimePreview.final_decision;
    }
  }

  async function handleReviewAction(action) {
    const payload = state.latestPayload;
    if (!payload || state.reviewActionPending) {
      return;
    }
    state.reviewActionPending = true;
    payload._reviewActionPending = true;
    payload._reviewAction = action;
    byId("answerStatus").innerHTML = chip(action === "approve" ? "正在接入方法库…" : "正在重新探索…", "warn");
    byId("answerMeta").textContent = action === "approve"
      ? "系统正在把这次探索形成的方法接入方法库。"
      : "系统正在根据你的拒绝意见重新进入探索，并准备下一轮答案。";
    renderWorkspace(payload);
    try {
      const review = await ensureWorkspaceReview(payload);
      let result;
      if (action === "approve") {
        result = await apiRequest("factory.review.approve", {
          review_task_id: review.review_task_id,
          note: "approved from workspace",
        });
        payload.asset_pipeline.review = result.review;
        payload.asset_pipeline.rule_version = result.rule_version;
        payload.asset_pipeline.case_rule_link = result.case_rule_link;
        payload.display_decision_text = "方法已接入方法库";
        payload._reviewActionPending = false;
        payload._reviewAction = "";
      } else {
        result = await apiRequest("factory.review.reject", {
          review_task_id: review.review_task_id,
          note: "rejected from workspace; rerun exploration",
        });
        payload.asset_pipeline.review = result.review;
        payload.asset_pipeline.draft = result.draft;
        if (result.rerun) {
          payload.asset_pipeline.feedback = result.rerun.feedback;
          payload.asset_pipeline.promotion = result.rerun.promotion;
          payload.asset_pipeline.review = result.rerun.review;
          payload.exploration_runtime = result.rerun.exploration_runtime;
          payload.exploration_links = buildExplorationLinksFromRuntime(result.rerun.exploration_runtime);
          applyPreviewAnswer(payload, result.rerun.review?.payload?.test_execution_preview);
        }
        payload._reviewActionPending = false;
        payload._reviewAction = "";
      }
      renderWorkspace(payload);
    } catch (error) {
      payload._reviewActionPending = false;
      payload._reviewAction = "";
      renderWorkspace(payload);
      byId("answerStatus").innerHTML = chip("审核动作失败", "danger");
      byId("answerMeta").textContent = error.message || String(error);
    } finally {
      state.reviewActionPending = false;
    }
  }

  function bindReviewActions() {
    document.querySelectorAll("[data-review-action]").forEach((button) => {
      button.addEventListener("click", () => {
        handleReviewAction(button.dataset.reviewAction);
      });
    });
  }

  function renderDetailSurface(payload) {
    const target = byId("detailSurface");
    if (!payload) {
      target.innerHTML = `<div class="empty-state">运行后展示详情。</div>`;
      return;
    }
    const tab = state.activeDetailTab;
    if (tab === "evidence") {
      target.innerHTML = renderDecisionEvidence(payload);
      return;
    }
    if (tab === "status") {
      target.innerHTML = renderDecisionStatus(payload);
      return;
    }
    target.innerHTML = renderInternalPanel(payload);
  }

  function pulseResultFeedback() {
    const targets = [
      document.querySelector(".decision-main"),
      document.querySelector(".result-side-card"),
      byId("answerView"),
      byId("evidenceList"),
      byId("detailSurface"),
    ].filter(Boolean);
    targets.forEach((target) => {
      target.classList.remove("result-fresh");
      // Force reflow so repeated runs retrigger the animation.
      void target.offsetWidth;
      target.classList.add("result-fresh");
      window.setTimeout(() => {
        target.classList.remove("result-fresh");
      }, 1400);
    });
  }

  let _explorationPollHandle = null;

  function stopExplorationPoll() {
    if (_explorationPollHandle) {
      clearInterval(_explorationPollHandle);
      _explorationPollHandle = null;
    }
  }

  async function pollExplorationResult(taskId, backendTaskUrl, partialPayload) {
    stopExplorationPoll();
    // Poll every 2 seconds until the task completes or fails
    _explorationPollHandle = setInterval(async () => {
      try {
        const resp = await fetch(backendTaskUrl);
        if (!resp.ok) return;
        const body = await resp.json();
        if (!body.success) return;
        const task = body.data;
        const status = task.status || "";
        // Completed terminal states
        if (["completed", "need_human_review", "insufficient_evidence"].includes(status)) {
          stopExplorationPoll();
          setProgress(90, "探索完成，正在生成最终结果…");
          try {
            const resultPayload = await apiRequest("product.workspace.exploration_poll", {
              payload: { exploration_task_id: taskId },
            });
            // Merge exploration result into the existing payload
            Object.assign(partialPayload, resultPayload);
            setProgress(100, "执行完成");
            setProgressState("done", "已完成");
            renderWorkspace(partialPayload);
          } catch (mergeError) {
            setProgress(100, "探索执行完成");
            setProgressState("", "待机");
          }
          return;
        }
        // Failed terminal states
        if (["failed", "timed_out", "cancelled"].includes(status)) {
          stopExplorationPoll();
          setProgress(100, "探索未完成");
          setProgressState("", "待机");
          return;
        }
        // Update progress label with current stage
        const stage = task.current_stage || status;
        setProgress(80, `多智能体探索中：${stage}…`);
      } catch (_pollError) {
        // Silently retry on network errors
      }
    }, 2000);
  }

  function renderWorkspace(payload) {
    state.latestPayload = payload;
    saveWorkspaceSnapshot(payload);
    renderAnswer(payload);
    byId("decisionSummary").innerHTML = renderDecisionSummary(payload);
    byId("evidenceList").innerHTML = renderEvidence(payload);
    renderDetailSurface(payload);
    pulseResultFeedback();
    bindReviewActions();
    hydrateExplorationLinks(payload);
    maybeOpenExplorationOverlay(payload);
  }

  async function solveWorkspace() {
    if (!canRunCurrentSolve()) {
      byId("answerStatus").innerHTML = chip("等待输入", "warn");
      byId("answerView").classList.remove("compact");
      byId("answerView").innerHTML = "<p>请先选择推荐样本，或上传文件后再点击“运行当前问题”。</p>";
      byId("answerMeta").textContent = "当前页面不会在进入时自动执行。";
      return;
    }
    const button = byId("solveBtn");
    button.disabled = true;
    button.textContent = "正在运行…";
    startProgress();
    let completed = false;
    try {
      const materials = state.uploadedFiles.length
        ? await Promise.all(state.uploadedFiles.map(fileToMaterial))
        : selectedSampleMaterials().map((item) => ({ ...item }));
      const scenarioId = byId("scenarioSelect").value || undefined;
      const shouldUseLlmExploration = Boolean(
        state.selectedSample?.expected?.route_decision === "exploration"
      );
      const metadata = state.launchConfig.demoMode
        ? {
            use_live_kimi: false,
            run_live_super_agent: false,
            exploration_use_llm: shouldUseLlmExploration,
            exploration_mode: shouldUseLlmExploration ? "emergent" : "grounded",
          }
        : {
            use_live_kimi: true,
            run_live_super_agent: true,
            exploration_use_llm: true,
            exploration_mode: "emergent",
          };
      const payload = await apiRequest("product.workspace.solve", {
        question_text: byId("questionInput").value.trim(),
        scenario_id: scenarioId,
        materials,
        metadata,
      });

      // Detect pending exploration: show overlay immediately, poll for completion
      const explorationPending = (
        payload.exploration_runtime?.status === "exploration_pending"
        && payload.exploration_links?.task_id
      );
      if (explorationPending) {
        setProgress(60, "思考中 · 正在启动多智能体探索…");
        setProgressState("thinking", "探索中");
      } else {
        setProgress(76, "已找到合适方法，正在生成最终答案…");
      }

      if (payload.super_agent_handoff && payload.super_agent_result?.status === "not_run") {
        const agentResult = await apiRequest(payload.super_agent_handoff.action, {
          payload: payload.super_agent_handoff.payload,
        });
        payload.super_agent_result = agentResult;
        const finalText = String(agentResult.final_text || "").trim();
        if (finalText && !(finalText.startsWith("{") && finalText.endsWith("}"))) {
          payload.answer_engine = "super_agent";
          payload.final_answer = finalText;
        }
      }

      // First render — shows partial answer + opens exploration overlay if pending
      if (!explorationPending) {
        setProgress(100, "执行完成");
        setProgressState("done", "已完成");
      } else {
        setProgress(80, "多智能体探索已在后台启动，打开探索面板查看实时进度…");
      }
      renderWorkspace(payload);
      completed = true;

      // If exploration is pending, poll discovery backend and fetch result when done
      if (explorationPending) {
        const taskId = payload.exploration_links.task_id;
        const backendTaskUrl = payload.exploration_links.backend_task_url;
        pollExplorationResult(taskId, backendTaskUrl, payload);
      }
    } catch (error) {
      const message = error.message || String(error);
      setProgress(100, "执行失败");
      setProgressState("error", "处理失败");
      byId("answerStatus").innerHTML = chip("执行失败", "danger");
      byId("answerView").classList.add("compact");
      byId("answerView").innerHTML = `<p>${escapeHtml(message)}</p>`;
      byId("answerMeta").textContent = "请检查上传文件、问题内容或后端日志。";
    } finally {
      if (!completed && !document.querySelector(".progress-panel.error")) {
        setProgressState("", "待机");
      }
      stopProgress();
      updateSolveButtonState();
    }
  }

  async function init() {
    state.launchConfig = readLaunchConfig();
    try {
      const [scenarios, cases, backend] = await Promise.all([
        apiRequest("product.scenario.list"),
        apiRequest("demo.workspace_case.list"),
        apiRequest("retrieval.embedding_backend.status"),
      ]);
      state.scenarios = scenarios.scenarios || [];
      state.sampleCases = cases.cases || [];
      state.defaultSampleRef = cases.default_case_ref || null;
      renderScenarioOptions(state.scenarios);
      renderSamples();
      renderRelatedQuestions();
      renderHeroStatus(backend.active_backend);
      const requestedCaseRef = state.launchConfig.caseRef;
      const availableCaseRefs = new Set(state.sampleCases.map((item) => item.case_ref));
      const initialCaseRef = requestedCaseRef && availableCaseRefs.has(requestedCaseRef)
        ? requestedCaseRef
        : state.defaultSampleRef;
      if (initialCaseRef) {
        await loadSample(initialCaseRef);
      }
      if (state.launchConfig.autorun && initialCaseRef) {
        window.setTimeout(() => {
          solveWorkspace();
        }, 120);
      }
    } catch (error) {
      byId("heroChips").innerHTML = chip(error.message || String(error), "danger");
      setProgress(100, error.message || "初始化失败");
    }

    byId("sampleStartBtn").addEventListener("click", async () => {
      if (state.defaultSampleRef) {
        state.uploadedFiles = [];
        byId("fileInput").value = "";
        await loadSample(state.selectedSample?.case_ref || state.defaultSampleRef);
        return;
      }
      state.startIntent = "sample";
      renderStartPathCards();
      renderStartModeStatus();
      renderFiles();
      updateSolveButtonState();
    });
    byId("uploadStartBtn").addEventListener("click", () => {
      state.startIntent = "upload";
      renderStartPathCards();
      renderStartModeStatus();
      renderFiles();
      updateSolveButtonState();
      byId("fileInput").focus();
      resetWorkspaceView("已切换到上传模式。请选择本地文件后再运行。");
    });
    byId("fileInput").addEventListener("change", (event) => {
      state.startIntent = "upload";
      state.uploadedFiles = Array.from(event.target.files || []);
      syncQuestionFieldState();
      renderStartPathCards();
      renderStartModeStatus();
      renderFiles();
      updateSolveButtonState();
      resetWorkspaceView("已选择本地文件。点击“运行当前问题”后开始处理。");
    });
    byId("solveBtn").addEventListener("click", solveWorkspace);
    byId("sampleList").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-case-ref]");
      if (!button) return;
      state.uploadedFiles = [];
      byId("fileInput").value = "";
      await loadSample(button.dataset.caseRef);
    });
    byId("relatedQuestionList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-related-question]");
      if (!button) return;
      byId("questionInput").value = button.dataset.relatedQuestion || "";
      syncQuestionFieldState();
    });
    byId("clearBtn").addEventListener("click", () => {
      closeExplorationOverlay();
      state.selectedSample = null;
      state.startIntent = "sample";
      state.uploadedFiles = [];
      byId("fileInput").value = "";
      byId("questionInput").value = "";
      syncQuestionFieldState();
      byId("scenarioSelect").value = "";
      renderStartPathCards();
      renderStartModeStatus();
      renderFiles();
      renderSamples();
      renderRelatedQuestions();
      updateSolveButtonState();
      resetWorkspaceView();
    });
    document.querySelectorAll("[data-detail-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeDetailTab = button.dataset.detailTab;
        document.querySelectorAll("[data-detail-tab]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        renderDetailSurface(state.latestPayload);
      });
    });
    document.querySelectorAll("[data-exploration-close]").forEach((button) => {
      button.addEventListener("click", closeExplorationOverlay);
    });
    renderStartPathCards();
    renderStartModeStatus();
    renderFiles();
    updateSolveButtonState();
    resetWorkspaceView();
    byId("questionInput").addEventListener("input", syncQuestionFieldState);
  }

  init();
})();
