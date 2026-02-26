(function () {
  const STORAGE_EDUFLOW_API_URL = "eduflow_api_url";
  const DEFAULT_EDUFLOW_API_URL = "https://eduflows.cn";

  let currentFile = null;
  let currentFileContent = null;
  let currentCardsMarkdown = null;

  const tabStatusEl = document.getElementById("tab-status");
  const eduflowApiUrlEl = document.getElementById("eduflow-api-url");
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

  chrome.storage.local.get([STORAGE_EDUFLOW_API_URL], (r) => {
    eduflowApiUrlEl.value = r[STORAGE_EDUFLOW_API_URL] || DEFAULT_EDUFLOW_API_URL;
  });
  eduflowApiUrlEl.addEventListener("change", () => chrome.storage.local.set({ [STORAGE_EDUFLOW_API_URL]: eduflowApiUrlEl.value }));

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

    btnGenerate.disabled = true;
    setStatus(generateStatus, "生成中...", "info");
    setProgress(10, "上传并生成中...");
    try {
      setProgress(20, "调用 EduFlow 后端（DSPy）...");
      const formData = new FormData();
      formData.append("file", currentFile);
      const res = await fetch(`${eduflowApiUrl}/api/extension/upload-and-generate`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (data.error) throw new Error(data.error);
      if (!data.success || !data.cards_markdown) {
        throw new Error(data.error || "生成失败");
      }

      const stages = data.stages || [];
      const cardsMarkdown = data.cards_markdown;

      setProgress(100, "完成");
      currentCardsMarkdown = cardsMarkdown;
      setStatus(generateStatus, `已生成 ${stages.length * 2} 张卡片`, "success");
      cardsSummary.textContent = `已生成 ${stages.length} 个阶段、${stages.length * 2} 张卡片。请确保当前标签页为智慧树能力训练配置页，再点击「注入平台」。`;
      if (cardsPreview) cardsPreview.textContent = currentCardsMarkdown;
      cardsReady.style.display = "block";
      setStatus(injectStatus, "");
    } catch (err) {
      setStatus(generateStatus, "错误：" + err.message + "。请确认 EduFlow 后端地址正确（本地部署可填 http://localhost:端口）", "error");
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
