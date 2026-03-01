/**
 * EduFlow 智慧树卡片注入 - Background Service Worker
 * 参考实现：chrome.cookies.get(ai-poly) + API_REQUEST
 */

const HIKETC_URL = "https://hike-teaching-center.polymas.com/";
const AI_POLY_COOKIE = "ai-poly";
const CLOUDAPI_BASE = "https://cloudapi.polymas.com";

// 默认 LLM 配置（与 .env 一致，API Key 需在插件内填写）
const DEFAULT_LLM_API_URL = "http://llm-service.polymas.com/api/openai/v1";
const DEFAULT_LLM_MODEL = "Doubao-1.5-pro-32k";
const DEFAULT_LLM_SERVICE_CODE = "SI_Ability";

chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleMessage(msg, sender).then(sendResponse).catch((err) => {
    console.error("Background message handler error:", err);
    sendResponse({ success: false, error: err.message });
  });
  return true; // 保持消息通道开放以支持 async sendResponse
});

const ZHIHUISHU_MATCH = /hike-teaching-center\.polymas\.com.*ability/i;

async function handleMessage(msg, sender) {
  switch (msg.type) {
    case "GET_CURRENT_TAB_URL":
      return getCurrentTabUrl();
    case "GET_CURRENT_TAB_INFO":
      return getCurrentTabInfo();
    case "GET_AUTH":
      return getAuth();
    case "EXTRACT_PAGE_IDS":
      return extractPageIds(msg.payload);
    case "API_REQUEST":
      return apiRequest(msg.payload);
    case "LLM_CALL":
      return llmCall(msg.payload);
    case "EXTRACT_NODES_FROM_PAGE":
      return extractNodesFromPage(sender);
    case "GET_PLATFORM_CONFIG":
      return getPlatformConfig();
    case "LLM_CALL":
      return { success: false, error: "插件已移除 LLM 直连，请使用 EduFlow 后端（DSPy）" };
    default:
      return { success: false, error: `Unknown message type: ${msg.type}` };
  }
}

async function getCurrentTabInfo() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url) return { success: true, data: { url: "", tabId: null, isZhihuishu: false } };
    const isZhihuishu = ZHIHUISHU_MATCH.test(tab.url);
    return { success: true, data: { url: tab.url, tabId: tab.id, isZhihuishu } };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * 调用 LLM（OpenAI 兼容 chat/completions）
 * payload: { apiUrl, apiKey, model, serviceCode?, messages, maxTokens? }
 */
async function llmCall(payload) {
  try {
    const { apiUrl, apiKey, model, serviceCode, messages, maxTokens = 8192 } = payload || {};
    if (!apiUrl || !apiKey || !model || !Array.isArray(messages) || messages.length === 0) {
      return { success: false, error: "LLM 配置不完整：需要 apiUrl、apiKey、model、messages" };
    }
    const url = apiUrl.replace(/\/$/, "") + "/chat/completions";
    const headers = {
      "Content-Type": "application/json",
      Authorization: "Bearer " + apiKey,
    };
    if (serviceCode) headers["X-Service-Code"] = serviceCode;
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        model,
        messages,
        max_tokens: maxTokens,
        temperature: 0.7,
      }),
    });
    if (!res.ok) {
      const text = await res.text();
      return { success: false, error: `LLM HTTP ${res.status}: ${text.slice(0, 200)}` };
    }
    const data = await res.json();
    const content = data.choices?.[0]?.message?.content?.trim() ?? "";
    return { success: true, data: content };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function getCurrentTabUrl() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab?.url
      ? { success: true, data: tab.url }
      : { success: false, error: "No active tab found" };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function getAuth() {
  try {
    const cookie = await chrome.cookies.get({
      url: HIKETC_URL,
      name: AI_POLY_COOKIE,
    });
    const authorization = cookie?.value || null;
    return { success: true, data: { authorization } };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * 从 URL 解析 trainTaskId、courseId
 * courseId 可能在 query 或 path 中，如 /course/123/ 或 ?courseId=123
 */
async function extractPageIds(payload) {
  try {
    let url = payload?.url;
    if (!url) {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      url = tab?.url;
    }
    if (!url) return { success: false, error: "No URL available" };

    const u = new URL(url);
    let trainTaskId = u.searchParams.get("trainTaskId") || u.searchParams.get("train_task_id");
    let courseId = u.searchParams.get("courseId") || u.searchParams.get("course_id");

    if (!courseId && u.pathname) {
      const m = u.pathname.match(/\/course\/([^/]+)/i) || u.pathname.match(/\/courseId[=\/]([^/&]+)/i);
      if (m) courseId = m[1];
    }

    return {
      success: true,
      data: { trainTaskId: trainTaskId || null, courseId: courseId || null },
    };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * 从页面提取 SCRIPT_START / SCRIPT_END 节点 ID（通过 chrome.scripting.executeScript 避免 CSP 阻止内联脚本）
 */
async function extractNodesFromPage(sender) {
  const tabId = sender?.tab?.id;
  if (!tabId) return { success: false, error: "无法获取当前标签页" };
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: () => {
        const nodes = [];
        const walk = (obj, depth) => {
          if (depth > 10) return;
          if (!obj || typeof obj !== "object") return;
          if (obj.id && (obj.type === "SCRIPT_START" || obj.type === "SCRIPT_END")) {
            nodes.push({ id: obj.id, type: obj.type });
            return;
          }
          for (const k of Object.keys(obj)) {
            if (obj[k] && typeof obj[k] === "object" && !Array.isArray(obj[k])) walk(obj[k], depth + 1);
            if (Array.isArray(obj[k])) obj[k].forEach((x) => walk(x, depth + 1));
          }
        };
        if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__?.renderers) {
          for (const r of Object.values(window.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers || {})) {
            if (r?.getCurrentFiber) try { walk(r.getCurrentFiber(), 0); } catch (e) {}
          }
        }
        const start = nodes.find((n) => n.type === "SCRIPT_START");
        const end = nodes.find((n) => n.type === "SCRIPT_END");
        return { start_node_id: start?.id, end_node_id: end?.id };
      },
    });
    const result = results?.[0]?.result;
    if (result && (result.start_node_id || result.end_node_id)) {
      return { success: true, data: result };
    }
    return { success: false, error: "页面中未找到开始/结束节点，请确保已打开能力训练配置页并刷新" };
  } catch (e) {
    return { success: false, error: e.message || "提取节点失败" };
  }
}

/** 解析 queryScriptStepList 响应，提取 SCRIPT_START / SCRIPT_END 的 stepId，与 content.js 逻辑一致 */
function parseStepListForStartEnd(data) {
  let list = [];
  if (Array.isArray(data)) list = data;
  else if (data?.data && Array.isArray(data.data)) list = data.data;
  else if (data?.data?.steps) list = data.data.steps;
  else if (data?.data?.list) list = data.data.list;
  else if (data?.data?.scriptStepList) list = data.data.scriptStepList;
  else if (data?.data?.scriptSteps) list = data.data.scriptSteps;
  else if (data?.steps) list = data.steps;
  else if (data?.list && Array.isArray(data.list)) list = data.list;
  else if (data?.scriptStepList && Array.isArray(data.scriptStepList)) list = data.scriptStepList;
  else if (data?.result?.list) list = data.result.list;
  else if (data?.result?.scriptStepList) list = data.result.scriptStepList;
  const getType = (s) =>
    s?.type || s?.nodeType || s?.stepType || s?.stepDetailDTO?.nodeType || s?.stepDetailDTO?.stepType || "";
  const getId = (s) =>
    s?.id || s?.stepId || s?.scriptStepId || s?.stepDetailDTO?.stepId || "";
  const start = list.find((s) => getType(s) === "SCRIPT_START");
  const end = list.find((s) => getType(s) === "SCRIPT_END");
  return { startNodeId: start ? getId(start) : "", endNodeId: end ? getId(end) : "" };
}

/**
 * 一键获取平台配置：当前页 URL、Cookie、JWT、开始/结束节点 ID，供粘贴到 Web 端使用。
 */
async function getPlatformConfig() {
  try {
    const tabInfo = await getCurrentTabInfo();
    if (!tabInfo.success || !tabInfo.data?.url) {
      return { success: false, error: "无法获取当前标签页，请先打开智慧树能力训练配置页" };
    }
    const pageUrl = tabInfo.data.url;
    const idsRes = await extractPageIds({ url: pageUrl });
    if (!idsRes.success) {
      return { success: false, error: idsRes.error || "无法从 URL 解析 trainTaskId" };
    }
    const { trainTaskId, courseId } = idsRes.data;

    const auth = await getAuth();
    const jwt = auth.success && auth.data?.authorization ? auth.data.authorization : "";

    const cookies = await chrome.cookies.getAll({ url: HIKETC_URL });
    const cookieStr = cookies.map((c) => `${c.name}=${c.value}`).join("; ");

    let startNodeId = "";
    let endNodeId = "";
    if (trainTaskId) {
      const listRes = await apiRequest({
        endpoint: "/teacher-course/abilityTrain/queryScriptStepList",
        method: "POST",
        body: { trainTaskId, courseId: courseId || "" },
      });
      if (listRes.success && listRes.data) {
        const parsed = parseStepListForStartEnd(listRes.data);
        startNodeId = parsed.startNodeId || "";
        endNodeId = parsed.endNodeId || "";
      }
    }

    return {
      success: true,
      data: {
        url: pageUrl,
        cookie: cookieStr,
        jwt,
        startNodeId,
        endNodeId,
        trainTaskId: trainTaskId || "",
        courseId: courseId || "",
      },
    };
  } catch (e) {
    return { success: false, error: e.message || "获取配置失败" };
  }
}

async function apiRequest(payload) {
  try {
    const { endpoint, method = "GET", body, headers: extraHeaders = {} } = payload;
    const auth = await getAuth();
    if (!auth.success || !auth.data?.authorization) {
      return { success: false, error: "Failed to get auth (ai-poly cookie)" };
    }

    const url = endpoint.startsWith("http") ? endpoint : `${CLOUDAPI_BASE}${endpoint}`;
    const headers = {
      "Content-Type": "application/json",
      ...extraHeaders,
    };
    if (auth.data.authorization) {
      headers.Authorization = auth.data.authorization;
    }

    const res = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      credentials: "include",
    });

    if (!res.ok) {
      const text = await res.text();
      return { success: false, error: `HTTP ${res.status}: ${text.slice(0, 200)}` };
    }

    const data = await res.json();
    return { success: true, data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}
