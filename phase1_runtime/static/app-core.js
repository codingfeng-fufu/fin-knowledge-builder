(function () {
  const API_PATH = "/api/phase1";
  const STORAGE_KEY = "phase1_workspace_latest";

  async function apiRequest(action, payload = {}) {
    const response = await fetch(API_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...payload }),
    });
    const data = await response.json();
    if (!data.ok) {
      const message = (data.error && data.error.message) || "请求失败";
      throw new Error(message);
    }
    return data.data;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function chip(label, tone = "") {
    return `<span class="chip ${tone}">${escapeHtml(label)}</span>`;
  }

  function kv(label, value) {
    return `<div class="detail-card"><h3>${escapeHtml(label)}</h3><div class="section-copy">${escapeHtml(value)}</div></div>`;
  }

  function code(value) {
    return `<pre class="code-block">${escapeHtml(typeof value === "string" ? value : JSON.stringify(value, null, 2))}</pre>`;
  }

  function displayRouteLabel(routeDecision, routeTitle) {
    if (routeTitle) {
      return String(routeTitle);
    }
    return {
      direct_match: "规则直接复用",
      rule_composable: "规则复用与组合",
      needs_more_context: "等待补充材料",
      exploration: "多智能体探索",
    }[String(routeDecision || "")] || String(routeDecision || "-");
  }

  function displayAnswerSource(answerEngine) {
    return {
      super_agent: "增强求解",
      runtime: "系统求解",
    }[String(answerEngine || "")] || String(answerEngine || "-");
  }

  function displayStatusLabel(status) {
    return {
      open: "待审核",
      published: "已发布",
      completed: "已完成",
      draft: "草稿",
      pending: "待处理",
      rejected: "已驳回",
      approved: "已通过审核",
      unreviewed: "待审核",
      candidate: "候选中",
      deprecated: "已下线",
      rolled_back: "已回滚",
    }[String(status || "")] || String(status || "-");
  }

  function saveWorkspaceSnapshot(payload) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
      console.warn("save workspace snapshot failed", error);
    }
  }

  function loadWorkspaceSnapshot() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.warn("load workspace snapshot failed", error);
      return null;
    }
  }

  async function fileToMaterial(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const textExts = new Set(["txt", "md", "json", "csv", "log", "html", "htm"]);
    if (textExts.has(ext)) {
      const content = await file.text();
      return {
        name: file.name,
        content,
        size: file.size,
      };
    }
    const base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.split(",").pop() || "");
      };
      reader.onerror = () => reject(reader.error || new Error("file read failed"));
      reader.readAsDataURL(file);
    });
    return {
      name: file.name,
      content_base64: base64,
      size: file.size,
    };
  }

  function renderJsonBlock(target, value) {
    target.innerHTML = code(value);
  }

  function byId(id) {
    return document.getElementById(id);
  }

  async function copyText(value) {
    const text = String(value ?? "");
    if (!text) return false;
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    textarea.style.pointerEvents = "none";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  }

  window.Phase1UI = {
    apiRequest,
    byId,
    chip,
    code,
    escapeHtml,
    fileToMaterial,
    kv,
    displayAnswerSource,
    displayRouteLabel,
    displayStatusLabel,
    loadWorkspaceSnapshot,
    copyText,
    renderJsonBlock,
    saveWorkspaceSnapshot,
  };
})();
