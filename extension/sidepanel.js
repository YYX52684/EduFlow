(function () {
  const STORAGE_EDUFLOW_API_URL = "eduflow_api_url";
  const STORAGE_CARD_CONFIG = "eduflow_card_config";
  const STORAGE_WORKSPACE_ID = "eduflow_workspace_id";
  const STORAGE_HISTORY = "eduflow_history";
  const DEFAULT_EDUFLOW_API_URL = "https://eduflows.cn";
  const MAX_HISTORY = 20;

  const DEFAULT_CARD_CONFIG = {
    modelId: "Doubao-Seed-1.6",
    historyRecordNum: -1,
    trainerName: "agent",
    interactiveRounds: 0,
  };

  const state = {
    file: null,
    fileName: null,
    stages: null,
    fullContent: null,
    trainsetPath: null,
    personas: [],
    personaDir: null,
    selectedFrameworkId: "dspy",
    selectedPersonaId: null,
    taskName: "",
    description: "",
    cardsMarkdown: null,
  };

  let lastInjectBodies = null;
  let historyEntries = [];

  const tabStatusEl = document.getElementById("tab-status");
  const eduflowApiUrlEl = document.getElementById("eduflow-api-url");
  const extensionWorkspaceIdEl = document.getElementById("extension-workspace-id");
  const extensionWorkspacePickEl = document.getElementById("extension-workspace-pick");
  const btnRefreshWorkspaces = document.getElementById("btn-refresh-workspaces");
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileStatusEl = document.getElementById("file-status");
  const step1ResultEl = document.getElementById("step1-result");
  const step2Block = document.getElementById("step2-block");
  const step3Block = document.getElementById("step3-block");
  const step4Block = document.getElementById("step4-block");
  const personaSelect = document.getElementById("persona-select");
  const personaContentWrap = document.getElementById("persona-content-wrap");
  const personaContent = document.getElementById("persona-content");
  const btnSavePersona = document.getElementById("btn-save-persona");
  const personaSaveStatus = document.getElementById("persona-save-status");
  const btnGenerate = document.getElementById("btn-generate");
  const generateStatus = document.getElementById("generate-status");
  const generateProgress = document.getElementById("generate-progress");
  const progressTextEl = document.getElementById("progress-text");
  const progressFill = document.getElementById("progress-fill");
  const cardsGeneratedHint = document.getElementById("cards-generated-hint");
  const cardsPreview = document.getElementById("cards-preview");
  const btnInject = document.getElementById("btn-inject");
  const injectStatus = document.getElementById("inject-status");
  const btnGenerateAiBg = document.getElementById("btn-generate-ai-bg");
  const aiBgStatus = document.getElementById("ai-bg-status");

  const cardSourceGenerated = document.getElementById("card-source-generated");
  const cardSourceFile = document.getElementById("card-source-file");
  const cardSourceHistory = document.getElementById("card-source-history");
  const injectMdInput = document.getElementById("inject-md-input");
  const btnPickInjectMd = document.getElementById("btn-pick-inject-md");
  const historyInjectSelect = document.getElementById("history-inject-select");

  const cardConfigHeader = document.getElementById("card-config-header");
  const cardConfigBody = document.getElementById("card-config-body");
  const cardConfigToggle = document.getElementById("card-config-toggle");
  const cardConfigModelId = document.getElementById("card-config-model-id");
  const cardConfigHistoryNum = document.getElementById("card-config-history-num");
  const cardConfigTrainer = document.getElementById("card-config-trainer");
  const cardConfigRounds = document.getElementById("card-config-rounds");

  const historyHeader = document.getElementById("history-header");
  const historyBody = document.getElementById("history-body");
  const historyToggle = document.getElementById("history-toggle");
  const historyListEl = document.getElementById("history-list");
  const historyEmptyEl = document.getElementById("history-empty");

  const platformConfigStatus = document.getElementById("platform-config-status");
  const platformConfigFields = document.getElementById("platform-config-fields");
  const btnGetPlatformConfig = document.getElementById("btn-get-platform-config");
  const btnSyncWebPlatform = document.getElementById("btn-sync-web-platform");

  function getApiBase() {
    return (eduflowApiUrlEl?.value || "").trim().replace(/\/$/, "") || DEFAULT_EDUFLOW_API_URL;
  }

  function setStatus(el, text, type) {
    if (!el) return;
    el.textContent = text || "";
    el.className = "status " + (type || "info");
    el.style.display = text ? "block" : "none";
  }

  function setProgress(pct, label) {
    if (generateProgress) generateProgress.style.display = "block";
    if (progressFill) progressFill.style.width = Math.min(100, pct) + "%";
    if (progressTextEl) progressTextEl.textContent = label || "加载中...";
  }

  function enableStepBlocks(stepIndex) {
    for (let i = 2; i <= stepIndex; i++) {
      const block = document.getElementById("step" + i + "-block");
      if (block) block.classList.remove("step-block-disabled");
    }
  }

  function newId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return "h_" + Date.now() + "_" + Math.random().toString(36).slice(2, 10);
  }

  function countACards(md) {
    return (md.match(/^#\s*卡片\d+A\s*$/gm) || []).length;
  }

  function taskNameFromMarkdown(md) {
    const m = (md || "").match(/^>\s*任务名称:\s*(.+)$/m);
    return m ? m[1].trim() : "";
  }

  function loadCardConfigFromStorage(cb) {
    chrome.storage.local.get([STORAGE_CARD_CONFIG], (r) => {
      const c = r[STORAGE_CARD_CONFIG] && typeof r[STORAGE_CARD_CONFIG] === "object" ? r[STORAGE_CARD_CONFIG] : {};
      if (cardConfigModelId) cardConfigModelId.value = c.modelId != null && String(c.modelId).trim() !== "" ? c.modelId : DEFAULT_CARD_CONFIG.modelId;
      if (cardConfigHistoryNum) {
        const h = c.historyRecordNum;
        cardConfigHistoryNum.value =
          h !== undefined && h !== null && String(h) !== "" ? String(h) : String(DEFAULT_CARD_CONFIG.historyRecordNum);
      }
      if (cardConfigTrainer) cardConfigTrainer.value = c.trainerName != null && String(c.trainerName).trim() !== "" ? c.trainerName : DEFAULT_CARD_CONFIG.trainerName;
      if (cardConfigRounds) {
        const ir = c.interactiveRounds;
        cardConfigRounds.value =
          ir !== undefined && ir !== null && String(ir) !== "" ? String(ir) : String(DEFAULT_CARD_CONFIG.interactiveRounds);
      }
      if (cb) cb();
    });
  }

  function saveCardConfigToStorage() {
    const cfg = {
      modelId: (cardConfigModelId?.value || "").trim() || DEFAULT_CARD_CONFIG.modelId,
      historyRecordNum: parseInt(cardConfigHistoryNum?.value, 10),
      trainerName: (cardConfigTrainer?.value || "").trim() || DEFAULT_CARD_CONFIG.trainerName,
      interactiveRounds: parseInt(cardConfigRounds?.value, 10),
    };
    if (!Number.isFinite(cfg.historyRecordNum)) cfg.historyRecordNum = DEFAULT_CARD_CONFIG.historyRecordNum;
    if (!Number.isFinite(cfg.interactiveRounds)) cfg.interactiveRounds = DEFAULT_CARD_CONFIG.interactiveRounds;
    chrome.storage.local.set({ [STORAGE_CARD_CONFIG]: cfg });
  }

  function getCardConfigForInject() {
    const cfg = {
      modelId: (cardConfigModelId?.value || "").trim() || DEFAULT_CARD_CONFIG.modelId,
      trainerName: (cardConfigTrainer?.value || "").trim() || DEFAULT_CARD_CONFIG.trainerName,
      historyRecordNum: parseInt(cardConfigHistoryNum?.value, 10),
      interactiveRounds: parseInt(cardConfigRounds?.value, 10),
    };
    if (!Number.isFinite(cfg.historyRecordNum)) cfg.historyRecordNum = DEFAULT_CARD_CONFIG.historyRecordNum;
    if (!Number.isFinite(cfg.interactiveRounds)) cfg.interactiveRounds = DEFAULT_CARD_CONFIG.interactiveRounds;
    return cfg;
  }

  function updateCardSourceUI() {
    const file = cardSourceFile?.checked;
    const hist = cardSourceHistory?.checked;
    if (btnPickInjectMd) btnPickInjectMd.style.display = file ? "inline-block" : "none";
    if (historyInjectSelect) historyInjectSelect.style.display = hist ? "block" : "none";
  }

  function setCardSource(mode) {
    if (mode === "generated" && cardSourceGenerated) cardSourceGenerated.checked = true;
    if (mode === "file" && cardSourceFile) cardSourceFile.checked = true;
    if (mode === "history" && cardSourceHistory) cardSourceHistory.checked = true;
    updateCardSourceUI();
  }

  function refreshHistoryInjectSelect() {
    if (!historyInjectSelect) return;
    const sel = historyInjectSelect.value;
    historyInjectSelect.innerHTML = '<option value="">— 选择一条历史记录 —</option>';
    historyEntries.forEach((e) => {
      const opt = document.createElement("option");
      opt.value = e.id;
      opt.textContent = e.timestamp + " · " + (e.taskName || e.sourceFile || "未命名");
      historyInjectSelect.appendChild(opt);
    });
    if (sel && historyEntries.some((x) => x.id === sel)) historyInjectSelect.value = sel;
  }

  function persistHistory() {
    chrome.storage.local.set({ [STORAGE_HISTORY]: historyEntries });
  }

  function renderHistoryList() {
    if (!historyListEl) return;
    historyListEl.innerHTML = "";
    if (historyEmptyEl) historyEmptyEl.style.display = historyEntries.length ? "none" : "block";
    historyEntries.forEach((e) => {
      const li = document.createElement("li");
      const meta = document.createElement("div");
      meta.className = "history-meta";
      meta.innerHTML =
        '<div class="history-title">' +
        escapeHtml(e.taskName || "未命名任务") +
        "</div>" +
        '<div class="history-sub">' +
        escapeHtml(e.timestamp) +
        " · 源文件 " +
        escapeHtml(e.sourceFile || "—") +
        " · A卡 " +
        (e.stageCount != null ? e.stageCount : "?") +
        "</div>";
      const actions = document.createElement("div");
      actions.className = "history-actions";
      const bFill = document.createElement("button");
      bFill.type = "button";
      bFill.textContent = "填入注入区";
      bFill.addEventListener("click", () => {
        setCardSource("history");
        if (cardsPreview) cardsPreview.value = e.cardsMarkdown || "";
        if (historyInjectSelect) historyInjectSelect.value = e.id;
        setStatus(injectStatus, "已从历史记录填入", "success");
      });
      const bDel = document.createElement("button");
      bDel.type = "button";
      bDel.className = "danger";
      bDel.textContent = "删除";
      bDel.addEventListener("click", () => {
        historyEntries = historyEntries.filter((x) => x.id !== e.id);
        persistHistory();
        renderHistoryList();
        refreshHistoryInjectSelect();
      });
      actions.appendChild(bFill);
      actions.appendChild(bDel);
      li.appendChild(meta);
      li.appendChild(actions);
      historyListEl.appendChild(li);
    });
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function pushHistory(entry) {
    if (!entry.cardsMarkdown || !entry.cardsMarkdown.trim()) return;
    historyEntries = historyEntries.filter((x) => x.id !== entry.id);
    historyEntries.unshift(entry);
    while (historyEntries.length > MAX_HISTORY) historyEntries.pop();
    persistHistory();
    renderHistoryList();
    refreshHistoryInjectSelect();
  }

  function buildHistoryEntry(cardsMarkdown, sourceFile) {
    return {
      id: newId(),
      timestamp: new Date().toISOString().replace("T", " ").slice(0, 19),
      sourceFile: sourceFile || state.fileName || "",
      taskName: state.taskName || taskNameFromMarkdown(cardsMarkdown) || "",
      cardsMarkdown,
      personaId: state.selectedPersonaId || "",
      stageCount: countACards(cardsMarkdown),
    };
  }

  async function refreshTabStatus() {
    const res = await chrome.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
    if (!res.success) {
      tabStatusEl.textContent = "无法获取当前页面";
      tabStatusEl.className = "tab-status warn";
      return;
    }
    const { isZhihuishu } = res.data;
    if (isZhihuishu) {
      tabStatusEl.textContent = "当前页面：智慧树能力训练配置页，可注入";
      tabStatusEl.className = "tab-status ok";
    } else {
      tabStatusEl.textContent = "当前页面不是智慧树配置页。请先打开能力训练配置页后再点击「注入平台」。";
      tabStatusEl.className = "tab-status warn";
    }
  }

  const llmEl = {
    header: document.getElementById("settings-header"),
    body: document.getElementById("settings-body"),
    toggle: document.getElementById("settings-toggle"),
    summary: document.getElementById("llm-status-summary"),
    apiKey: document.getElementById("extension-llm-api-key"),
    keyMask: document.getElementById("extension-llm-key-mask"),
    baseUrl: document.getElementById("extension-llm-base-url"),
    model: document.getElementById("extension-llm-model"),
    presetSelect: document.getElementById("extension-llm-preset"),
    btnSave: document.getElementById("btn-save-llm-config"),
    btnTest: document.getElementById("btn-test-llm"),
    saveStatus: document.getElementById("extension-llm-save-status"),
    testStatus: document.getElementById("extension-llm-test-status"),
  };
  const LLM_PRESETS = {
    deepseek: { base_url: "https://api.deepseek.com", model: "deepseek-chat" },
    doubao: { base_url: "https://llm-service.polymas.com/api/openai/v1", model: "Doubao-1.5-pro-32k" },
    openai: { base_url: "https://api.openai.com/v1", model: "gpt-4o" },
  };
  let llmCanGenerate = false;

  let storageReady = new Promise((resolve) => {
    chrome.storage.local.get([STORAGE_EDUFLOW_API_URL, STORAGE_WORKSPACE_ID, STORAGE_HISTORY], (r) => {
      eduflowApiUrlEl.value = r[STORAGE_EDUFLOW_API_URL] || DEFAULT_EDUFLOW_API_URL;
      if (extensionWorkspaceIdEl) extensionWorkspaceIdEl.value = r[STORAGE_WORKSPACE_ID] || "";
      historyEntries = Array.isArray(r[STORAGE_HISTORY]) ? r[STORAGE_HISTORY] : [];
      renderHistoryList();
      refreshHistoryInjectSelect();
      resolve();
    });
  });
  eduflowApiUrlEl.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_EDUFLOW_API_URL]: eduflowApiUrlEl.value }));
  if (extensionWorkspaceIdEl) {
    extensionWorkspaceIdEl.addEventListener("change", () =>
      chrome.storage.local.set({ [STORAGE_WORKSPACE_ID]: (extensionWorkspaceIdEl.value || "").trim() })
    );
  }

  if (llmEl.header) {
    llmEl.header.addEventListener("click", () => {
      const open = llmEl.body.style.display !== "none";
      llmEl.body.style.display = open ? "none" : "block";
      llmEl.toggle.textContent = open ? "展开" : "收起";
    });
  }

  if (cardConfigHeader) {
    cardConfigHeader.addEventListener("click", () => {
      const open = cardConfigBody.style.display !== "none";
      cardConfigBody.style.display = open ? "none" : "block";
      if (cardConfigToggle) cardConfigToggle.textContent = open ? "展开" : "收起";
    });
  }

  [cardConfigModelId, cardConfigHistoryNum, cardConfigTrainer, cardConfigRounds].forEach((el) => {
    if (el) {
      el.addEventListener("change", saveCardConfigToStorage);
      el.addEventListener("blur", saveCardConfigToStorage);
    }
  });

  if (historyHeader) {
    historyHeader.addEventListener("click", () => {
      const open = historyBody.style.display !== "none";
      historyBody.style.display = open ? "none" : "block";
      if (historyToggle) historyToggle.textContent = open ? "展开" : "收起";
    });
  }

  if (cardSourceGenerated)
    cardSourceGenerated.addEventListener("change", () => {
      updateCardSourceUI();
      if (cardSourceGenerated.checked && state.cardsMarkdown) {
        if (cardsPreview) cardsPreview.value = state.cardsMarkdown;
      }
    });
  if (cardSourceFile) cardSourceFile.addEventListener("change", updateCardSourceUI);
  if (cardSourceHistory) cardSourceHistory.addEventListener("change", updateCardSourceUI);

  if (btnPickInjectMd) btnPickInjectMd.addEventListener("click", () => injectMdInput && injectMdInput.click());
  if (injectMdInput) {
    injectMdInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = "";
      if (!file) return;
      setCardSource("file");
      const reader = new FileReader();
      reader.onload = () => {
        const text = typeof reader.result === "string" ? reader.result : "";
        if (cardsPreview) cardsPreview.value = text;
        pushHistory(buildHistoryEntry(text, file.name));
        setStatus(injectStatus, "已载入本地文件并写入历史", "success");
      };
      reader.readAsText(file, "UTF-8");
    });
  }

  if (historyInjectSelect) {
    historyInjectSelect.addEventListener("change", () => {
      const id = historyInjectSelect.value;
      if (!id) return;
      setCardSource("history");
      const ent = historyEntries.find((x) => x.id === id);
      if (ent && cardsPreview) cardsPreview.value = ent.cardsMarkdown || "";
    });
  }

  async function fetchWorkspacesList() {
    const base = getApiBase();
    const res = await fetch(base + "/api/extension/workspaces");
    const data = await res.json().catch(() => ({}));
    return Array.isArray(data.workspaces) ? data.workspaces : [];
  }

  if (btnRefreshWorkspaces) {
    btnRefreshWorkspaces.addEventListener("click", async () => {
      try {
        const list = await fetchWorkspacesList();
        if (!extensionWorkspacePickEl) return;
        extensionWorkspacePickEl.innerHTML = '<option value="">— 从列表选择填入 —</option>';
        list.forEach((w) => {
          const opt = document.createElement("option");
          opt.value = w;
          opt.textContent = w;
          extensionWorkspacePickEl.appendChild(opt);
        });
        setStatus(llmEl.testStatus, "工作区列表已刷新（" + list.length + " 个）", "success");
      } catch (err) {
        setStatus(llmEl.testStatus, "拉取工作区失败：" + (err.message || ""), "error");
      }
    });
  }

  if (extensionWorkspacePickEl) {
    extensionWorkspacePickEl.addEventListener("change", () => {
      const v = extensionWorkspacePickEl.value;
      if (v && extensionWorkspaceIdEl) {
        extensionWorkspaceIdEl.value = v;
        chrome.storage.local.set({ [STORAGE_WORKSPACE_ID]: v });
      }
      extensionWorkspacePickEl.value = "";
    });
  }

  function llmSetSummary(text, type) {
    if (!llmEl.summary) return;
    llmEl.summary.textContent = text;
    llmEl.summary.className = "settings-summary" + (type ? " " + type : "");
  }

  async function loadExtensionLlmConfig() {
    const base = getApiBase();
    try {
      const res = await fetch(base + "/api/extension/llm/config");
      const data = await res.json().catch(() => ({}));
      llmCanGenerate = !!data.can_generate;
      if (data.presets) Object.assign(LLM_PRESETS, data.presets);

      if (data.status_message) {
        const type = data.can_generate ? "ok" : data.config_source === "none" ? "warn" : "";
        llmSetSummary(data.status_message, type);
      }
      if (llmEl.keyMask) {
        llmEl.keyMask.textContent = data.has_api_key ? data.api_key_masked || "已设置" : "未设置";
      }
      if (llmEl.baseUrl && data.base_url) {
        llmEl.baseUrl.value = data.base_url;
      }
      if (llmEl.model && data.model) {
        llmEl.model.value = data.model;
      }
    } catch (_) {
      llmSetSummary("无法连接后端，请确认地址", "error");
    }
  }

  if (llmEl.presetSelect) {
    llmEl.presetSelect.addEventListener("change", () => {
      const key = llmEl.presetSelect.value;
      const preset = LLM_PRESETS[key];
      if (!preset) return;
      if (llmEl.baseUrl) llmEl.baseUrl.value = preset.base_url || "";
      if (llmEl.model) llmEl.model.value = preset.model || "";
      llmEl.presetSelect.value = "";
    });
  }

  if (llmEl.btnSave) {
    llmEl.btnSave.addEventListener("click", async () => {
      const base = getApiBase();
      const bUrl = (llmEl.baseUrl?.value || "").trim();
      const mName = (llmEl.model?.value || "").trim();
      if (!bUrl || !mName) {
        setStatus(llmEl.saveStatus, "Base URL 和 Model 不能为空", "error");
        return;
      }
      setStatus(llmEl.saveStatus, "保存中…", "info");
      try {
        const body = { base_url: bUrl, model: mName };
        if (llmEl.apiKey?.value?.trim()) body.api_key = llmEl.apiKey.value.trim();
        const res = await fetch(base + "/api/extension/llm/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setStatus(llmEl.saveStatus, data.message || "保存失败", "error");
          return;
        }
        setStatus(llmEl.saveStatus, data.message || "已保存", "success");
        if (llmEl.apiKey) llmEl.apiKey.value = "";
        await loadExtensionLlmConfig();
      } catch (e) {
        setStatus(llmEl.saveStatus, "保存失败：" + (e.message || ""), "error");
      }
    });
  }

  if (llmEl.btnTest) {
    llmEl.btnTest.addEventListener("click", async () => {
      const base = getApiBase();
      setStatus(llmEl.testStatus, "测试中…", "info");
      llmEl.btnTest.disabled = true;
      try {
        const body = {};
        if (llmEl.apiKey?.value?.trim()) body.api_key = llmEl.apiKey.value.trim();
        if (llmEl.baseUrl?.value?.trim()) body.base_url = llmEl.baseUrl.value.trim();
        if (llmEl.model?.value?.trim()) body.model = llmEl.model.value.trim();
        const res = await fetch(base + "/api/extension/llm/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (data.success) {
          const msg = "连接成功" + (data.latency_ms ? ` (${data.latency_ms}ms)` : "");
          setStatus(llmEl.testStatus, msg, "success");
        } else {
          setStatus(llmEl.testStatus, data.error_message || "测试失败", "error");
        }
      } catch (e) {
        setStatus(llmEl.testStatus, "请求失败：" + (e.message || ""), "error");
      } finally {
        llmEl.btnTest.disabled = false;
      }
    });
  }

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    const file = e.dataTransfer?.files?.[0];
    if (file && /\.(md|docx|pdf)$/i.test(file.name)) handleFile(file);
  });
  fileInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  });

  async function handleFile(file) {
    state.file = file;
    state.fileName = file.name;
    state.stages = null;
    state.fullContent = null;
    state.personas = [];
    state.taskName = "";
    state.description = "";
    state.cardsMarkdown = null;
    if (cardsGeneratedHint) cardsGeneratedHint.style.display = "none";
    step1ResultEl.style.display = "none";
    setStatus(generateStatus, "");
    setStatus(injectStatus, "");
    setStatus(personaSaveStatus, "");
    personaContentWrap.style.display = "none";
    personaSelect.innerHTML = '<option value="">加载中…</option>';

    if (!llmCanGenerate) {
      setStatus(fileStatusEl, "请先在「LLM 设置」中配置 API Key", "error");
      return;
    }

    setStatus(fileStatusEl, "解析中（上传并生成 trainset、人设）…", "info");
    setProgress(10, "上传解析中...");
    const formData = new FormData();
    formData.append("file", file);
    const base = getApiBase();
    try {
      setProgress(30, "调用后端 upload-parse...");
      const res = await fetch(base + "/api/extension/upload-parse", { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (data.error) throw new Error(data.error);
      if (!data.success) throw new Error(data.error || "解析失败");

      state.stages = data.stages || [];
      state.fullContent = data.full_content || "";
      state.trainsetPath = data.trainset_path || null;
      state.personas = data.personas || [];
      state.personaDir = data.persona_dir || null;
      state.taskName = data.task_name || "";
      state.description = data.description || "";

      setProgress(100, "完成");
      setStatus(fileStatusEl, "解析完成：" + (data.filename || file.name), "success");
      step1ResultEl.style.display = "block";
      step1ResultEl.innerHTML =
        "阶段数：<strong>" +
        state.stages.length +
        "</strong>；人设数：<strong>" +
        state.personas.length +
        "</strong>" +
        (state.taskName ? "；任务：" + escapeHtml(state.taskName) : "");
      step1ResultEl.className = "step-result success";

      enableStepBlocks(4);
      await fillPersonaSelect();
    } catch (err) {
      setStatus(fileStatusEl, "解析失败：" + (err.message || ""), "error");
      step1ResultEl.style.display = "block";
      step1ResultEl.textContent = err.message || "解析失败";
      step1ResultEl.className = "step-result error";
    } finally {
      setProgress(0, "");
      if (generateProgress) generateProgress.style.display = "none";
    }
  }

  async function fillPersonaSelect() {
    personaSelect.innerHTML = '<option value="">加载中…</option>';
    const base = getApiBase();
    try {
      const res = await fetch(base + "/api/extension/personas");
      const data = await res.json().catch(() => ({}));
      const presets = data.presets || [];
      const custom = data.custom || [];
      personaSelect.innerHTML = '<option value="">请选择人设</option>';
      presets.forEach((id) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        personaSelect.appendChild(opt);
      });
      custom.forEach((id) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id.replace(/^custom\//, "");
        personaSelect.appendChild(opt);
      });
    } catch (_) {
      personaSelect.innerHTML = '<option value="">请选择人设</option>';
      ["excellent", "average", "struggling"].forEach((id) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        personaSelect.appendChild(opt);
      });
      (state.personas || []).forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.name || p.id;
        personaSelect.appendChild(opt);
      });
    }
  }

  personaSelect.addEventListener("change", async () => {
    const id = personaSelect.value;
    state.selectedPersonaId = id || null;
    if (!id) {
      personaContentWrap.style.display = "none";
      return;
    }
    const base = getApiBase();
    setStatus(personaSaveStatus, "加载中…", "info");
    personaContentWrap.style.display = "block";
    try {
      const res = await fetch(base + "/api/extension/personas/content?persona_id=" + encodeURIComponent(id));
      const data = await res.json().catch(() => ({}));
      personaContent.value = data.content || "";
      personaContent.readOnly = !!data.read_only;
      btnSavePersona.style.display = data.read_only ? "none" : "block";
      setStatus(personaSaveStatus, "");
    } catch (_) {
      personaContent.value = "";
      setStatus(personaSaveStatus, "加载失败", "error");
    }
  });

  btnSavePersona.addEventListener("click", async () => {
    const id = state.selectedPersonaId;
    if (!id || !id.startsWith("custom/")) return;
    const base = getApiBase();
    setStatus(personaSaveStatus, "保存中…", "info");
    try {
      const res = await fetch(base + "/api/extension/personas/content", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona_id: id, content: personaContent.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data.error_detail?.message || data.message || data.error || "保存失败";
        throw new Error(msg);
      }
      setStatus(personaSaveStatus, "已保存", "success");
    } catch (e) {
      setStatus(personaSaveStatus, "保存失败：" + (e.message || ""), "error");
    }
  });

  async function generateCards() {
    if (!state.stages || !state.fullContent) {
      setStatus(generateStatus, "请先完成步骤 1 选择文件", "error");
      return;
    }
    if (!llmCanGenerate) {
      setStatus(generateStatus, "请先在「LLM 设置」中配置 API Key", "error");
      return;
    }
    const base = getApiBase();
    btnGenerate.disabled = true;
    setStatus(generateStatus, "生成中...", "info");
    setProgress(20, "调用生成接口...");
    try {
      const res = await fetch(base + "/api/extension/generate-cards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          framework_id: state.selectedFrameworkId || "dspy",
          stages: state.stages,
          full_content: state.fullContent,
          source_filename: state.fileName || null,
          task_name: state.taskName || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.error) throw new Error(data.error);
      if (!data.success || !data.cards_markdown) throw new Error(data.error || "生成失败");

      state.cardsMarkdown = data.cards_markdown;
      setProgress(100, "完成");
      setStatus(generateStatus, "已生成卡片", "success");
      if (cardsGeneratedHint) {
        cardsGeneratedHint.textContent =
          "已生成 " + state.stages.length + " 个阶段。请在步骤 4 编辑区确认或修改后注入。";
        cardsGeneratedHint.style.display = "block";
      }
      if (cardsPreview) cardsPreview.value = state.cardsMarkdown;
      setCardSource("generated");
      setStatus(injectStatus, "");
      enableStepBlocks(4);
      pushHistory(buildHistoryEntry(state.cardsMarkdown, state.fileName));
    } catch (err) {
      setStatus(generateStatus, "错误：" + (err.message || ""), "error");
      if (cardsGeneratedHint) cardsGeneratedHint.style.display = "none";
    } finally {
      setProgress(0, "");
      if (generateProgress) generateProgress.style.display = "none";
      btnGenerate.disabled = false;
    }
  }

  btnGenerate.addEventListener("click", generateCards);

  function resetInjectFollowUp() {
    lastInjectBodies = null;
    if (btnGenerateAiBg) btnGenerateAiBg.disabled = true;
    setStatus(aiBgStatus, "");
  }

  cardsPreview &&
    cardsPreview.addEventListener("input", () => {
      resetInjectFollowUp();
    });

  btnInject.addEventListener("click", async () => {
    saveCardConfigToStorage();
    const markdown = cardsPreview ? cardsPreview.value : "";
    if (!markdown || !markdown.trim()) {
      setStatus(injectStatus, "请填写步骤 4 中的卡片内容（生成、本地文件或历史记录）", "error");
      return;
    }
    const tabRes = await chrome.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
    if (!tabRes.success || !tabRes.data.isZhihuishu) {
      setStatus(injectStatus, "请先切换到智慧树能力训练配置页标签，再点击「注入平台」。", "error");
      return;
    }
    setStatus(injectStatus, "正在注入...", "info");
    resetInjectFollowUp();
    btnInject.disabled = true;
    try {
      const res = await chrome.tabs.sendMessage(tabRes.data.tabId, {
        type: "INJECT_CARDS",
        payload: {
          cards_markdown: markdown,
          task_name: state.taskName || "",
          description: state.description || "",
          evaluation_items: [],
          card_config: getCardConfigForInject(),
        },
      });
      if (res?.success) {
        const d = res.details || {};
        const parts = [];
        if (d.aCount != null) parts.push("节点 " + d.aCount);
        if (d.bCount != null) parts.push("连线 " + d.bCount);
        if (d.evalCount != null && d.evalCount > 0) parts.push("评价项 " + d.evalCount);
        const summary = parts.length ? parts.join("，") : res.message || "请刷新画布查看";
        setStatus(injectStatus, "注入完成：" + summary, "success");
        if (d.aStepBodies && d.aStepBodies.length && btnGenerateAiBg) {
          lastInjectBodies = d.aStepBodies;
          btnGenerateAiBg.disabled = false;
        }
      } else {
        setStatus(injectStatus, "注入失败：" + (res?.error || "未知错误"), "error");
      }
    } catch (e) {
      setStatus(injectStatus, "注入失败：请确认当前标签页为智慧树能力训练配置页并刷新后重试。" + (e.message || ""), "error");
    } finally {
      btnInject.disabled = false;
    }
  });

  if (btnGenerateAiBg) {
    btnGenerateAiBg.addEventListener("click", async () => {
      if (!lastInjectBodies || !lastInjectBodies.length) return;
      const tabRes = await chrome.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
      if (!tabRes.success || !tabRes.data.isZhihuishu) {
        setStatus(aiBgStatus, "请先打开智慧树能力训练配置页", "error");
        return;
      }
      setStatus(aiBgStatus, "生成中 0/" + lastInjectBodies.length + "…", "info");
      btnGenerateAiBg.disabled = true;
      try {
        const res = await chrome.tabs.sendMessage(tabRes.data.tabId, {
          type: "GENERATE_A_BACKGROUNDS",
          payload: {
            a_step_bodies: lastInjectBodies,
            train_name: state.taskName || taskNameFromMarkdown(cardsPreview?.value || "") || "训练任务",
            train_description: state.description || "",
          },
        });
        if (res?.success && res.details) {
          const { okCount, fail, total } = res.details;
          let msg = "完成：" + okCount + "/" + total + " 张成功";
          if (fail && fail.length) msg += "；" + fail.map((f) => "#" + f.index + " " + (f.error || "")).join("；");
          setStatus(aiBgStatus, msg, fail && fail.length ? "error" : "success");
        } else {
          setStatus(aiBgStatus, res?.error || "失败", "error");
        }
      } catch (e) {
        setStatus(aiBgStatus, "请求失败：" + (e.message || ""), "error");
      } finally {
        btnGenerateAiBg.disabled = false;
      }
    });
  }

  if (btnGetPlatformConfig) {
    btnGetPlatformConfig.addEventListener("click", async () => {
      setStatus(platformConfigStatus, "获取中…", "info");
      if (platformConfigFields) platformConfigFields.style.display = "none";
      try {
        const res = await chrome.runtime.sendMessage({ type: "GET_PLATFORM_CONFIG" });
        if (!res.success) {
          setStatus(platformConfigStatus, res.error || "获取失败", "error");
          return;
        }
        const d = res.data;
        const urlEl = document.getElementById("platform-config-url");
        const cookieEl = document.getElementById("platform-config-cookie");
        const jwtEl = document.getElementById("platform-config-jwt");
        const startEl = document.getElementById("platform-config-start");
        const endEl = document.getElementById("platform-config-end");
        if (urlEl) urlEl.value = d.url || "";
        if (cookieEl) cookieEl.value = d.cookie || "";
        if (jwtEl) jwtEl.value = d.jwt || "";
        if (startEl) startEl.value = d.startNodeId || "";
        if (endEl) endEl.value = d.endNodeId || "";
        setStatus(platformConfigStatus, "已获取，可逐项复制到 Web 端", "success");
        if (platformConfigFields) platformConfigFields.style.display = "block";
      } catch (e) {
        setStatus(platformConfigStatus, "获取失败：" + (e.message || ""), "error");
      }
    });
  }

  if (btnSyncWebPlatform) {
    btnSyncWebPlatform.addEventListener("click", async () => {
      const wid = (extensionWorkspaceIdEl?.value || "").trim();
      if (!wid) {
        setStatus(platformConfigStatus, "请先在 LLM 设置中填写 Web 工作区 ID", "error");
        return;
      }
      setStatus(platformConfigStatus, "同步中…", "info");
      try {
        const res = await chrome.runtime.sendMessage({ type: "GET_PLATFORM_CONFIG" });
        if (!res.success) {
          setStatus(platformConfigStatus, res.error || "请先在本页一键获取平台配置（需在智慧树配置页）", "error");
          return;
        }
        const d = res.data;
        const base = getApiBase();
        const syncRes = await fetch(base + "/api/extension/sync-platform-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workspace_id: wid,
            url: d.url || undefined,
            cookie: d.cookie || undefined,
            authorization: d.jwt || undefined,
            start_node_id: d.startNodeId || undefined,
            end_node_id: d.endNodeId || undefined,
            course_id: d.courseId || undefined,
            train_task_id: d.trainTaskId || undefined,
          }),
        });
        const data = await syncRes.json().catch(() => ({}));
        if (!syncRes.ok) {
          const msg = data.error_detail?.message || data.message || data.detail || "同步失败";
          setStatus(platformConfigStatus, msg, "error");
          return;
        }
        setStatus(platformConfigStatus, data.message || "已写入", "success");
        const webUrl = base.replace(/\/$/, "") + "/app/w/" + encodeURIComponent(wid);
        chrome.tabs.create({ url: webUrl });
      } catch (e) {
        setStatus(platformConfigStatus, "同步失败：" + (e.message || ""), "error");
      }
    });
  }

  document.querySelectorAll(".platform-config-fields .btn-copy").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-target");
      const el = id ? document.getElementById(id) : null;
      if (!el) return;
      const text = el.value || "";
      if (!text) return;
      navigator.clipboard.writeText(text).then(
        () => {
          btn.textContent = "已复制";
          setTimeout(() => {
            btn.textContent = "复制";
          }, 1500);
        },
        () => {
          btn.textContent = "复制失败";
          setTimeout(() => {
            btn.textContent = "复制";
          }, 1500);
        }
      );
    });
  });

  (async function init() {
    await storageReady;
    loadCardConfigFromStorage();
    await loadExtensionLlmConfig();
    setCardSource("generated");
    updateCardSourceUI();
  })();
  refreshTabStatus();
  setInterval(refreshTabStatus, 2000);
})();
