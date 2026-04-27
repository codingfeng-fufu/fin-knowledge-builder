(function () {
  const { apiRequest, byId, escapeHtml } = window.Phase1UI;
  const {
    renderOpsCards,
    renderOpsDetail,
    renderOpsSummary,
    renderRuleGraphSummary,
    renderRuleGraphTree,
    renderReviewActionResult,
  } = window.Phase1OpsRenderers;

  const state = { selectedReviewId: null, ruleGraph: null };

  function dbPath() { return byId("opsDbPath").value.trim(); }

  function bindCardEvents() {
    document.querySelectorAll("[data-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.id;
        const kind = button.dataset.kind;
        state.selectedReviewId = kind === "review" ? id : state.selectedReviewId;
        let detail;
        if (kind === "run") detail = await apiRequest("factory.workspace_run.get", { db_path: dbPath(), workspace_run_id: id });
        if (kind === "feedback") detail = await apiRequest("feedback.get", { db_path: dbPath(), feedback_id: id });
        if (kind === "draft") detail = await apiRequest("factory.draft.get", { db_path: dbPath(), draft_id: id });
        if (kind === "review") detail = await apiRequest("factory.review.get", { db_path: dbPath(), review_task_id: id });
        if (kind === "version") detail = await apiRequest("factory.rule_version.get", { db_path: dbPath(), rule_version_id: id });
        byId("opsDetail").innerHTML = renderOpsDetail(kind, detail);
      });
    });
    document.querySelectorAll("[data-community-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const communityId = button.dataset.communityId;
        const roots = (state.ruleGraph || {}).roots || [];
        const stack = [...roots];
        let selected = null;
        while (stack.length) {
          const current = stack.pop();
          if ((current.community_id || "") === communityId) {
            selected = current;
            break;
          }
          stack.push(...(current.children || []));
        }
        if (selected) {
          byId("opsDetail").innerHTML = renderOpsDetail("community", selected);
        }
      });
    });
  }

  async function refreshOps() {
    const [runs, feedback, drafts, reviews, versions, assetView, ruleGraph] = await Promise.all([
      apiRequest("factory.workspace_run.list", { db_path: dbPath() }),
      apiRequest("feedback.list", { db_path: dbPath() }),
      apiRequest("factory.draft.list", { db_path: dbPath() }),
      apiRequest("factory.review.list", { db_path: dbPath() }),
      apiRequest("factory.rule_version.list", { db_path: dbPath() }),
      apiRequest("factory.retrieval_asset_view", { db_path: dbPath() }),
      apiRequest("factory.rule_graph.view", { db_path: dbPath() }),
    ]);
    state.ruleGraph = ruleGraph;
    byId("opsKpis").innerHTML = renderOpsSummary([
      { label: "求解记录", value: runs.workspace_run_count || 0 },
      { label: "反馈", value: feedback.feedback_count || 0 },
      { label: "方法草稿", value: drafts.draft_count || 0 },
      { label: "已发布方法", value: assetView.asset_count || 0 },
    ]);
    byId("ruleGraphSummary").innerHTML = renderRuleGraphSummary(ruleGraph);
    byId("ruleGraphTree").innerHTML = renderRuleGraphTree(ruleGraph);
    byId("workspaceRunCards").innerHTML = renderOpsCards(runs.workspace_runs || [], "run");
    byId("feedbackCards").innerHTML = renderOpsCards(feedback.feedback || [], "feedback");
    byId("draftCards").innerHTML = renderOpsCards(drafts.drafts || [], "draft");
    byId("reviewCards").innerHTML = renderOpsCards(reviews.reviews || [], "review");
    byId("versionCards").innerHTML = renderOpsCards(versions.versions || [], "version");
    bindCardEvents();
  }

  async function actOnReview(action) {
    if (!state.selectedReviewId) {
      byId("opsDetail").innerHTML = `<div class="empty-state">请先选择一条审核任务。</div>`;
      return;
    }
    const assignee = byId("opsAssignee").value.trim();
    const payload = action === "approve"
      ? await apiRequest("factory.review.approve", { db_path: dbPath(), review_task_id: state.selectedReviewId, note: assignee || undefined })
      : await apiRequest("factory.review.reject", { db_path: dbPath(), review_task_id: state.selectedReviewId, note: assignee || undefined });
    byId("opsDetail").innerHTML = renderReviewActionResult(action, payload, state.selectedReviewId);
    refreshOps();
  }

  byId("opsRefreshBtn").addEventListener("click", refreshOps);
  byId("opsApproveBtn").addEventListener("click", () => actOnReview("approve"));
  byId("opsRejectBtn").addEventListener("click", () => actOnReview("reject"));

  refreshOps().catch((error) => {
    byId("opsDetail").innerHTML = `<div class="empty-state">${escapeHtml(error.message || String(error))}</div>`;
  });
})();
