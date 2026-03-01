(function () {
  const STORAGE_EDUFLOW_API_URL = "eduflow_api_url";
  const DEFAULT_EDUFLOW_API_URL = "https://eduflows.cn";

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
    scoringSystemId: "default",
    cardsMarkdown: null,
  };

  const tabStatusEl = document.getElementById("tab-status");
  const eduflowApiUrlEl = document.getElementById("eduflow-api-url");
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileStatusEl = document.getElementById("file-status");
  const step1ResultEl = document.getElementById("step1-result");
  const step2Block = document.getElementById("step2-block");
  const frameworkSelect = document.getElementById("framework-select");
  const step3Block = document.getElementById("step3-block");
  const personaSelect = document.getElementById("persona-select");
  const personaContentWrap = document.getElementById("persona-content-wrap");
  const personaContent = document.getElementById("persona-content");
  const btnSavePersona = document.getElementById("btn-save-persona");
  const personaSaveStatus = document.getElementById("persona-save-status");
  const step4Block = document.getElementById("step4-block");
  const scoringSelect = document.getElementById("scoring-select");
  const step5Block = document.getElementById("step5-block");
  const btnGenerate = document.getElementById("btn-generate");
  const generateStatus = document.getElementById("generate-status");
  const generateProgress = document.getElementById("generate-progress");
  const progressTextEl = document.getElementById("progress-text");
  const progressFill = document.getElementById("progress-fill");
  const cardsReady = document.getElementById("cards-ready");
  const cardsSummary = document.getElementById("cards-summary");
  const cardsPreview = document.getElementById("cards-preview");
  const step6Block = document.getElementById("step6-block");
  const btnInject = document.getElementById("btn-inject");
  const injectStatus = document.getElementById("inject-status");

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

  chrome.storage.local.get([STORAGE_EDUFLOW_API_URL], (r) => {
    eduflowApiUrlEl.value = r[STORAGE_EDUFLOW_API_URL] || DEFAULT_EDUFLOW_API_URL;
  });
  eduflowApiUrlEl.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_EDUFLOW_API_URL]: eduflowApiUrlEl.value }));

  const extensionLlmApiKeyEl = document.getElementById("extension-llm-api-key");
  const extensionLlmKeyMaskEl = document.getElementById("extension-llm-key-mask");
  const extensionLlmModelTypeEl = document.getElementById("extension-llm-model-type");
  const btnSaveLlmConfig = document.getElementById("btn-save-llm-config");
  const extensionLlmSaveStatusEl = document.getElementById("extension-llm-save-status");

  async function loadExtensionLlmConfig() {
    const base = getApiBase();
    try {
      const res = await fetch(base + "/api/extension/llm/config");
      const data = await res.json().catch(() => ({}));
      if (extensionLlmKeyMaskEl) {
        extensionLlmKeyMaskEl.textContent = data.has_api_key ? data.api_key_masked || "已设置" : "未设置，请填写并保存";
      }
      if (extensionLlmModelTypeEl && data.model_type) {
        extensionLlmModelTypeEl.value = data.model_type;
      }
    } catch (_) {
      if (extensionLlmKeyMaskEl) extensionLlmKeyMaskEl.textContent = "无法加载，请确认后端地址正确";
    }
  }

  if (btnSaveLlmConfig) {
    btnSaveLlmConfig.addEventListener("click", async () => {
      const base = getApiBase();
      setStatus(extensionLlmSaveStatusEl, "保存中…", "info");
      try {
        const body = { model_type: extensionLlmModelTypeEl?.value || "doubao" };
        if (extensionLlmApiKeyEl?.value?.trim()) body.api_key = extensionLlmApiKeyEl.value.trim();
        const res = await fetch(base + "/api/extension/llm/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg = data.error_detail?.message || data.message || data.error || "保存失败";
          setStatus(extensionLlmSaveStatusEl, msg, "error");
          return;
        }
        setStatus(extensionLlmSaveStatusEl, data.message || "已保存", "success");
        if (extensionLlmApiKeyEl) extensionLlmApiKeyEl.value = "";
        await loadExtensionLlmConfig();
      } catch (e) {
        setStatus(extensionLlmSaveStatusEl, "保存失败：" + (e.message || ""), "error");
      }
    });
  }

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
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

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector('script[src="' + src + '"]')) {
        resolve();
        return;
      }
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("加载脚本失败: " + src));
      document.head.appendChild(s);
    });
  }

  function readFileAsText(file) {
    const ext = (file.name.match(/\.(\w+)$/i) || [])[1] || "";
    setStatus(fileStatusEl, "加载中...", "info");
    setProgress(5, "加载文件中...");
    if (ext.toLowerCase() === "md") {
      return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => {
          setStatus(fileStatusEl, "加载完成：" + file.name, "success");
          setProgress(0, "");
          if (generateProgress) generateProgress.style.display = "none";
          resolve(r.result);
        };
        r.onerror = () => reject(new Error("读取文件失败"));
        r.readAsText(file, "UTF-8");
      });
    }
    if (ext.toLowerCase() === "docx") {
      return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = async () => {
          try {
            const scriptUrl = chrome.runtime.getURL("lib/mammoth.min.js");
            await loadScript(scriptUrl);
          } catch (e) {
            setStatus(fileStatusEl, "不支持 .docx：请将 mammoth.min.js 放入 extension/lib/ 并重新加载扩展。", "error");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            reject(new Error("未找到 mammoth 库"));
            return;
          }
          if (typeof mammoth === "undefined") {
            setStatus(fileStatusEl, "mammoth 库加载异常", "error");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            reject(new Error("mammoth 未定义"));
            return;
          }
          try {
            const result = await mammoth.extractRawText({ arrayBuffer: r.result });
            setStatus(fileStatusEl, "加载完成：" + file.name, "success");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            resolve(result.value || "");
          } catch (err) {
            setStatus(fileStatusEl, "解析 .docx 失败：" + (err.message || ""), "error");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            reject(err);
          }
        };
        r.onerror = () => reject(new Error("读取文件失败"));
        r.readAsArrayBuffer(file);
      });
    }
    if (ext.toLowerCase() === "pdf") {
      return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = async () => {
          try {
            const scriptUrl = chrome.runtime.getURL("lib/pdf.min.js");
            await loadScript(scriptUrl);
          } catch (e) {
            setStatus(fileStatusEl, "不支持 .pdf：请将 pdf.min.js 放入 extension/lib/ 并重新加载扩展。", "error");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            reject(new Error("未找到 pdf.js 库"));
            return;
          }
          try {
            const pdfjsLib = window.pdfjsLib || window.pdfJsLib;
            if (!pdfjsLib || !pdfjsLib.getDocument) {
              setStatus(fileStatusEl, "pdf 库未正确加载", "error");
              setProgress(0, "");
              if (generateProgress) generateProgress.style.display = "none";
              reject(new Error("pdfjsLib 未定义"));
              return;
            }
            const doc = await pdfjsLib.getDocument({ data: r.result }).promise;
            const numPages = doc.numPages;
            let text = "";
            for (let i = 1; i <= numPages; i++) {
              const page = await doc.getPage(i);
              const content = await page.getTextContent();
              text += content.items.map((it) => (it.str || "")).join(" ") + "\n";
            }
            setStatus(fileStatusEl, "加载完成：" + file.name, "success");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            resolve(text);
          } catch (err) {
            setStatus(fileStatusEl, "解析 .pdf 失败：" + (err.message || ""), "error");
            setProgress(0, "");
            if (generateProgress) generateProgress.style.display = "none";
            reject(err);
          }
        };
        r.onerror = () => reject(new Error("读取文件失败"));
        r.readAsArrayBuffer(file);
      });
    }
    setStatus(fileStatusEl, "仅支持 .md / .docx / .pdf", "error");
    setProgress(0, "");
    if (generateProgress) generateProgress.style.display = "none";
    return Promise.reject(new Error("不支持的文件格式"));
  }

  async function handleFile(file) {
    state.file = file;
    state.fileName = file.name;
    state.stages = null;
    state.fullContent = null;
    state.personas = [];
    state.cardsMarkdown = null;
    cardsReady.style.display = "none";
    step1ResultEl.style.display = "none";
    setStatus(generateStatus, "");
    setStatus(injectStatus, "");
    setStatus(personaSaveStatus, "");
    personaContentWrap.style.display = "none";
    personaSelect.innerHTML = '<option value="">加载中…</option>';

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

      setProgress(100, "完成");
      setStatus(fileStatusEl, "解析完成：" + (data.filename || file.name), "success");
      step1ResultEl.style.display = "block";
      step1ResultEl.innerHTML = "阶段数：<strong>" + state.stages.length + "</strong>；trainset："
        + (state.trainsetPath || "—") + "；人设数：<strong>" + state.personas.length + "</strong>。";
      step1ResultEl.className = "step-result success";

      enableStepBlocks(6);
      await loadFrameworks();
      await fillPersonaSelect();
      if (scoringSelect) scoringSelect.value = state.scoringSystemId || "default";
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

  async function loadFrameworks() {
    const base = getApiBase();
    try {
      const res = await fetch(base + "/api/extension/frameworks");
      const data = await res.json().catch(() => ({}));
      const list = data.frameworks || [];
      frameworkSelect.innerHTML = "";
      list.forEach((f) => {
        const opt = document.createElement("option");
        opt.value = f.id;
        opt.textContent = f.name || f.id;
        frameworkSelect.appendChild(opt);
      });
      if (list.length && !list.find((f) => f.id === state.selectedFrameworkId)) {
        state.selectedFrameworkId = list[0].id;
      }
      if (state.selectedFrameworkId) frameworkSelect.value = state.selectedFrameworkId;
    } catch (_) {
      frameworkSelect.innerHTML = '<option value="dspy">dspy</option>';
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

  frameworkSelect.addEventListener("change", () => {
    state.selectedFrameworkId = frameworkSelect.value || "dspy";
  });

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

  scoringSelect.addEventListener("change", () => {
    state.scoringSystemId = scoringSelect.value || "default";
  });

  async function generateCards() {
    if (!state.stages || !state.fullContent) {
      setStatus(generateStatus, "请先完成步骤 1 选择文件", "error");
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
          scoring_system_id: state.scoringSystemId || "default",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.error) throw new Error(data.error);
      if (!data.success || !data.cards_markdown) throw new Error(data.error || "生成失败");

      state.cardsMarkdown = data.cards_markdown;
      setProgress(100, "完成");
      setStatus(generateStatus, "已生成卡片", "success");
      cardsSummary.textContent = "已生成 " + state.stages.length + " 个阶段。可编辑下方内容后再点击「注入平台」。";
      cardsPreview.value = state.cardsMarkdown;
      cardsReady.style.display = "block";
      setStatus(injectStatus, "");
      enableStepBlocks(6);
    } catch (err) {
      setStatus(generateStatus, "错误：" + (err.message || ""), "error");
      cardsReady.style.display = "none";
    } finally {
      setProgress(0, "");
      if (generateProgress) generateProgress.style.display = "none";
      btnGenerate.disabled = false;
    }
  }

  btnGenerate.addEventListener("click", generateCards);

  btnInject.addEventListener("click", async () => {
    const markdown = cardsPreview ? cardsPreview.value : state.cardsMarkdown;
    if (!markdown || !markdown.trim()) {
      setStatus(injectStatus, "请先完成步骤 5 生成卡片", "error");
      return;
    }
    const tabRes = await chrome.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
    if (!tabRes.success || !tabRes.data.isZhihuishu) {
      setStatus(injectStatus, "请先切换到智慧树能力训练配置页标签，再点击「注入平台」。", "error");
      return;
    }
    setStatus(injectStatus, "正在注入...", "info");
    try {
      const res = await chrome.tabs.sendMessage(tabRes.data.tabId, {
        type: "INJECT_CARDS",
        payload: { cards_markdown: markdown },
      });
      if (res?.success) {
        setStatus(injectStatus, "注入完成：" + (res.message || "请刷新画布查看"), "success");
      } else {
        setStatus(injectStatus, "注入失败：" + (res?.error || "未知错误"), "error");
      }
    } catch (e) {
      setStatus(injectStatus, "注入失败：请确认当前标签页为智慧树能力训练配置页并刷新后重试。" + (e.message || ""), "error");
    }
  });

  (async function init() {
    await loadFrameworks();
    await loadExtensionLlmConfig();
  })();
  refreshTabStatus();
  setInterval(refreshTabStatus, 2000);
})();
