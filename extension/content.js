/**
 * EduFlow 智慧树卡片注入 - Content Script（仅注入）
 * 仅在智慧树能力训练配置页运行，响应 INJECT_CARDS 消息并执行注入。
 */

(function () {
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type !== "INJECT_CARDS") return;
    const cards_markdown = msg.payload?.cards_markdown;
    if (!cards_markdown) {
      sendResponse({ success: false, error: "缺少 cards_markdown" });
      return true;
    }
    runInject(cards_markdown)
      .then((result) => sendResponse({ success: true, message: `已注入 ${result.aCount} 个节点，${result.bCount} 条连线` }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  });

  async function runInject(cardsMarkdown) {
    const idsRes = await chrome.runtime.sendMessage({ type: "EXTRACT_PAGE_IDS", payload: { url: location.href } });
    if (!idsRes.success) throw new Error(idsRes.error || "获取页面 ID 失败");
    const { trainTaskId, courseId } = idsRes.data;
    if (!trainTaskId) throw new Error("当前页面 URL 中未找到 trainTaskId");

    const { start_node_id, end_node_id } = await getStartEndNodes(trainTaskId, courseId || "");
    if (!start_node_id || !end_node_id) throw new Error("无法获取开始/结束节点 ID，请刷新页面后重试");

    return await injectCards({
      cardsMarkdown: cardsMarkdown,
      trainTaskId,
      courseId: courseId || "",
      startNodeId: start_node_id,
      endNodeId: end_node_id,
    });
  }

  async function getStartEndNodes(trainTaskId, courseId) {
    const listRes = await chrome.runtime.sendMessage({
      type: "API_REQUEST",
      payload: {
        endpoint: "/teacher-course/abilityTrain/getScriptStepList",
        method: "POST",
        body: { trainTaskId, courseId: courseId || "" },
      },
    });
    if (listRes.success && listRes.data) {
      const steps = extractStepsFromResponse(listRes.data);
      const startNode = steps.find((s) => getStepType(s) === "SCRIPT_START");
      const endNode = steps.find((s) => getStepType(s) === "SCRIPT_END");
      if (startNode && endNode) {
        return {
          start_node_id: getStepId(startNode),
          end_node_id: getStepId(endNode),
        };
      }
    }
    return await getStartEndFromPage();
  }

  function extractStepsFromResponse(data) {
    let list = [];
    if (Array.isArray(data)) list = data;
    else if (data?.data && Array.isArray(data.data)) list = data.data;
    else if (data?.data?.steps) list = data.data.steps;
    else if (data?.data?.list) list = data.data.list;
    else if (data?.data?.scriptStepList) list = data.data.scriptStepList;
    else if (data?.steps) list = data.steps;
    else if (data?.result && Array.isArray(data.result)) list = data.result;
    else if (data?.result?.list) list = data.result.list;
    return list;
  }

  function getStepType(step) {
    return step?.type || step?.nodeType || step?.stepType || "";
  }

  function getStepId(step) {
    return step?.id || step?.stepId || step?.scriptStepId || "";
  }

  async function getStartEndFromPage() {
    const res = await chrome.runtime.sendMessage({ type: "EXTRACT_NODES_FROM_PAGE" });
    if (res.success && res.data) {
      return res.data;
    }
    return {};
  }

  async function injectCards({ cardsMarkdown, trainTaskId, courseId, startNodeId, endNodeId }) {
    const cards = parseCardsMarkdown(cardsMarkdown);
    const aCards = cards.filter((c) => c.card_type === "A");
    const bCards = cards.filter((c) => c.card_type === "B");
    const stepIds = [];
    const basePos = { x: 570, y: 100 };
    const step = { x: 0, y: 200 };

    for (let i = 0; i < aCards.length; i++) {
      const a = aCards[i];
      const pos = { x: basePos.x + step.x * i, y: basePos.y + step.y * i };
      const stepId = generateId(21);
      const createRes = await chrome.runtime.sendMessage({
        type: "API_REQUEST",
        payload: {
          endpoint: "/teacher-course/abilityTrain/createScriptStep",
          method: "POST",
          body: buildCreateStepBody(a, trainTaskId, courseId, stepId, pos),
        },
      });
      if (!createRes.success) throw new Error(`创建节点 ${i + 1} 失败: ${createRes.error}`);
      stepIds.push(stepId);
      await sleep(500);
    }

    if (startNodeId && stepIds[0]) {
      await createFlow(startNodeId, stepIds[0], trainTaskId);
      await sleep(300);
    }

    for (let i = 0; i < stepIds.length - 1; i++) {
      const flowRes = await createFlow(stepIds[i], stepIds[i + 1], trainTaskId);
      const flowId = flowRes?._flow_id;
      const b = bCards.find((c) => c.stage_num === i + 1);
      if (flowId && b) {
        const prompt = cleanCardContent(b.full_content);
        await chrome.runtime.sendMessage({
          type: "API_REQUEST",
          payload: {
            endpoint: "/teacher-course/abilityTrain/editScriptStepFlow",
            method: "POST",
            body: {
              trainTaskId,
              flowId,
              scriptStepStartId: stepIds[i],
              scriptStepEndId: stepIds[i + 1],
              scriptStepStartHandle: `${stepIds[i]}-source-bottom`,
              scriptStepEndHandle: `${stepIds[i + 1]}-target-top`,
              transitionPrompt: prompt,
              transitionHistoryNum: -1,
              flowSettingType: "quick",
              isDefault: 1,
              isError: false,
              flowCondition: `卡片${i + 1}B`,
              flowConfiguration: { relation: "and", conditions: [{ text: "条件组1", relation: "and", conditions: [{ text: `卡片${i + 1}B` }] }] },
            },
          },
        });
      }
      await sleep(500);
    }

    if (endNodeId && stepIds.length) {
      await createFlow(stepIds[stepIds.length - 1], endNodeId, trainTaskId);
    }

    return { aCount: aCards.length, bCount: aCards.length - 1 };
  }

  async function createFlow(startId, endId, trainTaskId) {
    const flowId = generateId(21);
    const res = await chrome.runtime.sendMessage({
      type: "API_REQUEST",
      payload: {
        endpoint: "/teacher-course/abilityTrain/createScriptStepFlow",
        method: "POST",
        body: {
          trainTaskId,
          flowId,
          scriptStepStartId: startId,
          scriptStepEndId: endId,
          scriptStepStartHandle: `${startId}-source-bottom`,
          scriptStepEndHandle: `${endId}-target-top`,
          transitionPrompt: "",
          transitionHistoryNum: -1,
          flowSettingType: "quick",
          isDefault: 1,
          isError: false,
          flowCondition: "1",
          flowConfiguration: { relation: "and", conditions: [{ text: "条件组1", relation: "and", conditions: [{ text: "" }] }] },
        },
      },
    });
    const id = res?.success ? (res.data?.data?.flowId ?? res.data?.flowId ?? res.data?.id ?? flowId) : null;
    return res?.success ? { _flow_id: id } : null;
  }

  function buildCreateStepBody(card, trainTaskId, courseId, stepId, position) {
    const content = cleanCardContent(card.full_content);
    const stepName = card.stage_name || card.title || `阶段${card.stage_num}`;
    const description = card.stage_description || `阶段${card.stage_num}`;
    const prologue = card.prologue || "";
    const rounds = card.interaction_rounds > 0 ? card.interaction_rounds : 5;
    return {
      trainTaskId,
      stepId,
      courseId: courseId || "",
      libraryFolderId: "",
      positionDTO: { x: position.x, y: position.y },
      stepDetailDTO: {
        nodeType: "SCRIPT_NODE",
        stepName,
        description,
        prologue,
        modelId: "",
        llmPrompt: content,
        knowledgeBaseSwitch: 0,
        searchEngineSwitch: 0,
        videoSwitch: 0,
        whiteBoardSwitch: 0,
        trainSubType: "ability",
        trainerName: "",
        scriptStepCover: {},
        scriptStepResourceList: [],
        interactiveRounds: rounds,
        historyRecordNum: 0,
      },
    };
  }

  function cleanCardContent(content) {
    return content
      .replace(/^#\s*卡片\d+[AB]\s*\n/, "")
      .replace(/<!--\s*STAGE_META:\s*\{.*?\}\s*-->\s*\n?/g, "")
      .replace(/#\s*Prologue\s*\n[\s\S]*?(?=\n#\s|\Z)/, "")
      .trim();
  }

  function parseCardsMarkdown(content) {
    const CARD_PATTERN = /^#\s*卡片(\d+)([AB])\s*$/m;
    const sections = content.split(/\n---\n/);
    const cards = [];
    for (const section of sections) {
      const s = section.trim();
      if (!s) continue;
      const m = CARD_PATTERN.exec(s);
      if (m) {
        const stage_num = parseInt(m[1], 10);
        const card_type = m[2];
        cards.push({
          card_id: `${stage_num}${card_type}`,
          stage_num,
          card_type,
          title: `卡片${stage_num}${card_type}`,
          full_content: s,
          stage_name: "",
          stage_description: "",
          interaction_rounds: 0,
          prologue: "",
        });
      }
    }
    const metaPattern = /<!--\s*STAGE_META:\s*(\{.*?\})\s*-->/;
    const sectionPattern = /#\s+([^\n]+)\n([\s\S]*?)(?=\n#\s|$)/g;
    for (const card of cards) {
      const metaM = metaPattern.exec(card.full_content);
      if (metaM) {
        try {
          const meta = JSON.parse(metaM[1]);
          card.stage_name = meta.stage_name || "";
          card.stage_description = meta.description || "";
          card.interaction_rounds = meta.interaction_rounds || 0;
        } catch (_) {}
      }
      let match;
      while ((match = sectionPattern.exec(card.full_content)) !== null) {
        const [, title, body] = match;
        if (title.trim() === "Prologue") card.prologue = body.trim();
      }
    }
    return cards;
  }

  function generateId(len) {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    let s = "";
    for (let i = 0; i < len; i++) s += chars[Math.floor(Math.random() * chars.length)];
    return s;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
})();
