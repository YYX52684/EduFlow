(function () {
  const STORAGE_EDUFLOW_API_URL = "eduflow_api_url";
  const STORAGE_LLM_URL = "eduflow_llm_api_url";
  const STORAGE_LLM_KEY = "eduflow_llm_api_key";
  const STORAGE_LLM_MODEL = "eduflow_llm_model";
  const STORAGE_LLM_SERVICE_CODE = "eduflow_llm_service_code";
  const DEFAULT_EDUFLOW_API_URL = "https://eduflows.cn";
  const DEFAULT_LLM_API_URL = "http://llm-service.polymas.com/api/openai/v1";
  const DEFAULT_LLM_MODEL = "Doubao-1.5-pro-32k";
  const DEFAULT_LLM_SERVICE_CODE = "SI_Ability";

  const ANALYZE_PROMPT = `你是一个剧本分析专家，擅长为沉浸式角色扮演体验设计场景结构。
请分析以下剧本，将其划分为多个**场景/幕**。请严格按照以下JSON格式返回（不要添加任何其他说明，不要使用markdown代码块）：
{"stages":[{"id":1,"title":"场景标题","description":"场景描述","interaction_rounds":5,"role":"NPC角色","student_role":"学生角色","task":"场景目标","key_points":["要点1"],"content_excerpt":"原文摘要"}]}
划分原则：每个场景有完整剧情单元，场景间自然递进，体量适中。不要当成考试来划分。
剧本内容：
---
{content}
---
请直接返回JSON：`;

  const GENERATE_PROMPT_PREFIX = `你是一个教学卡片设计专家。根据以下「分幕结果」和「完整剧本」，生成沉浸式角色扮演的卡片 Markdown。
要求：1. 按阶段顺序输出「# 卡片NA」「# 卡片NB」，N 为阶段号。2. 卡片之间用 --- 分隔。3. 卡片NA 含 # Role、# Context、# Interaction Logic、# Judgment Logic、# Constraints、# Output Format；第一张加 # Prologue。4. 卡片NB 为简短过渡提示。5. 用「你」指代 NPC，「学生」指代对方。回复 50-100 字。
分幕结果（JSON）：{stagesJson}
完整剧本：{fullContent}
请直接输出完整 Markdown（从 # 卡片1A 开始）：`;

  let currentFile = null;
  let currentFileContent = null;
  let currentCardsMarkdown = null;

  const tabStatusEl = document.getElementById("tab-status");
  const eduflowDetails = document.getElementById("eduflow-details");
  const eduflowApiUrlEl = document.getElementById("eduflow-api-url");
  const llmDetails = document.getElementById("llm-details");
  const llmUrl = document.getElementById("llm-url");
  const llmKey = document.getElementById("llm-key");
  const llmModel = document.getElementById("llm-model");
  const llmServiceCode = document.getElementById("llm-service-code");
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileStatusEl = document.getElementById("file-status");
  const btnGenerate = document.getElementById("btn-generate");
  const generateStatus = document.getElementById("generate-status");
  const generateProgress = document.getElementById("generate-progress");
  const progressTextEl = document.getElementById("progress-text");
  const progressFill = document.getElementById("progress-fill");
  const cardsReady = document.getElementById("cards-ready");
  const cardsSummary = document.getElementById("cards-summary");
  const cardsPreview = document.getElementById("cards-preview");
  const btnInject = document.getElementById("btn-inject");
  const injectStatus = document.getElementById("inject-status");

  function setStatus(el, text, type) {
    if (!el) return;
    el.textContent = text || "";
    el.className = "status " + (type || "info");
    el.style.display = text ? "block" : "none";
  }

  function setProgress(pct, label) {
    generateProgress.style.display = "block";
    if (progressFill) progressFill.style.width = Math.min(100, pct) + "%";
    if (progressTextEl) progressTextEl.textContent = label || "加载中...";
  }

  async function refreshTabStatus() {
    const res = await chrome.runtime.sendMessage({ type: "GET_CURRENT_TAB_INFO" });
    if (!res.success) {
      tabStatusEl.textContent = "无法获取当前页面";
      tabStatusEl.className = "tab-status warn";
      return;
    }
    const { url, isZhihuishu } = res.data;
    if (isZhihuishu) {
      tabStatusEl.textContent = "当前页面：智慧树能力训练配置页，可注入";
      tabStatusEl.className = "tab-status ok";
    } else {
      tabStatusEl.textContent = "当前页面不是智慧树配置页。请先打开能力训练配置页后再点击「注入平台」。";
      tabStatusEl.className = "tab-status warn";
    }
  }

  chrome.storage.local.get([STORAGE_EDUFLOW_API_URL, STORAGE_LLM_URL, STORAGE_LLM_KEY, STORAGE_LLM_MODEL, STORAGE_LLM_SERVICE_CODE], (r) => {
    eduflowApiUrlEl.value = r[STORAGE_EDUFLOW_API_URL] || DEFAULT_EDUFLOW_API_URL;
    llmUrl.value = r[STORAGE_LLM_URL] || DEFAULT_LLM_API_URL;
    llmKey.value = r[STORAGE_LLM_KEY] || "";
    llmModel.value = r[STORAGE_LLM_MODEL] || DEFAULT_LLM_MODEL;
    llmServiceCode.value = r[STORAGE_LLM_SERVICE_CODE] || DEFAULT_LLM_SERVICE_CODE;
  });
  eduflowApiUrlEl.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_EDUFLOW_API_URL]: eduflowApiUrlEl.value }));
  llmUrl.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_LLM_URL]: llmUrl.value }));
  llmKey.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_LLM_KEY]: llmKey.value }));
  llmModel.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_LLM_MODEL]: llmModel.value }));
  llmServiceCode.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_LLM_SERVICE_CODE]: llmServiceCode.value }));

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

  function handleFile(file) {
    currentFile = file;
    currentCardsMarkdown = null;
    cardsReady.style.display = "none";
    setStatus(generateStatus, "");
    setStatus(injectStatus, "");
    btnGenerate.disabled = true;
    readFileAsText(file)
      .then((text) => {
        currentFileContent = text;
        btnGenerate.disabled = false;
      })
      .catch(() => {});
  }

  async function generateCards() {
    if (!currentFileContent || !currentFile) return;
    const eduflowApiUrl = (eduflowApiUrlEl?.value || "").trim().replace(/\/$/, "") || DEFAULT_EDUFLOW_API_URL;
    const apiKey = llmKey.value.trim();

    btnGenerate.disabled = true;
    setStatus(generateStatus, "生成中...", "info");
    setProgress(10, "上传并生成中...");
    try {
      let stages = [];
      let cardsMarkdown = null;

      if (eduflowApiUrl) {
        setProgress(20, "调用 EduFlow 后端...");
        try {
          const formData = new FormData();
          formData.append("file", currentFile);
          const res = await fetch(`${eduflowApiUrl}/api/extension/upload-and-generate`, {
            method: "POST",
            body: formData,
          });
          const data = await res.json().catch(() => ({}));
          if (data.error) throw new Error(data.error);
          if (data.success && data.cards_markdown) {
            cardsMarkdown = data.cards_markdown;
            stages = data.stages || [];
          }
        } catch (e) {
          setProgress(25, "后端不可用，改用 LLM 直连...");
        }
      }

      if (!cardsMarkdown) {
        if (!apiKey) {
          setStatus(generateStatus, "后端暂时不可用，请填写下方 LLM API Key 作为备用", "error");
          return;
        }
        setProgress(25, "分幕中...");
        const llmConfig = {
          apiUrl: llmUrl.value.trim() || DEFAULT_LLM_API_URL,
          apiKey,
          model: llmModel.value.trim() || DEFAULT_LLM_MODEL,
          serviceCode: llmServiceCode.value.trim() || DEFAULT_LLM_SERVICE_CODE || undefined,
        };
        const content = currentFileContent.length > 45000 ? currentFileContent.slice(0, 45000) + "\n\n[以下已省略]" : currentFileContent;
        const analyzeRes = await chrome.runtime.sendMessage({
          type: "LLM_CALL",
          payload: {
            apiUrl: llmConfig.apiUrl,
            apiKey: llmConfig.apiKey,
            model: llmConfig.model,
            serviceCode: llmConfig.serviceCode,
            messages: [{ role: "user", content: ANALYZE_PROMPT.replace("{content}", content) }],
            maxTokens: 8192,
          },
        });
        if (!analyzeRes.success) throw new Error(analyzeRes.error || "分幕失败");
        setProgress(40, "分幕完成，生成卡片中...");
        try {
          const raw = analyzeRes.data.replace(/```\w*\n?/g, "").trim();
          const m = raw.match(/\{[\s\S]*\}/);
          const obj = m ? JSON.parse(m[0]) : JSON.parse(raw);
          stages = obj.stages || obj;
        } catch (e) {
          throw new Error("分幕结果解析失败");
        }
        if (!stages.length) throw new Error("未分析出有效阶段");
        setProgress(55, "生成卡片中...");
        const genRes = await chrome.runtime.sendMessage({
          type: "LLM_CALL",
          payload: {
            apiUrl: llmConfig.apiUrl,
            apiKey: llmConfig.apiKey,
            model: llmConfig.model,
            serviceCode: llmConfig.serviceCode,
            messages: [{
              role: "user",
              content: GENERATE_PROMPT_PREFIX
                .replace("{stagesJson}", JSON.stringify(stages))
                .replace("{fullContent}", content.slice(0, 30000)),
            }],
            maxTokens: 16384,
          },
        });
        if (!genRes.success) throw new Error(genRes.error || "生成失败");
        let cards = genRes.data.trim();
        if (!cards.includes("# 卡片")) cards = "# 卡片1A\n\n" + cards;
        cardsMarkdown = `# 教学卡片\n\n> 生成时间: ${new Date().toLocaleString()}\n> 阶段数量: ${stages.length}\n\n---\n\n` + cards;
      }

      setProgress(100, "完成");
      currentCardsMarkdown = cardsMarkdown;
      setStatus(generateStatus, `已生成 ${stages.length * 2} 张卡片`, "success");
      cardsSummary.textContent = `已生成 ${stages.length} 个阶段、${stages.length * 2} 张卡片。请确保当前标签页为智慧树能力训练配置页，再点击「注入平台」。`;
      if (cardsPreview) cardsPreview.textContent = currentCardsMarkdown;
      cardsReady.style.display = "block";
      setStatus(injectStatus, "");
    } catch (err) {
      setStatus(generateStatus, "错误：" + err.message, "error");
      cardsReady.style.display = "none";
      setProgress(0, "");
      if (generateProgress) generateProgress.style.display = "none";
    } finally {
      btnGenerate.disabled = false;
    }
  }

  btnGenerate.addEventListener("click", generateCards);

  btnInject.addEventListener("click", async () => {
    if (!currentCardsMarkdown) {
      setStatus(injectStatus, "请先生成卡片", "error");
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
        payload: { cards_markdown: currentCardsMarkdown },
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

  refreshTabStatus();
  setInterval(refreshTabStatus, 2000);
})();
