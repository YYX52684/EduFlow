"""智慧树平台训练任务对话客户端（简化版）

用于本地学生 LLM 与平台侧 LLM 进行对话：
- /ai-tools/trainRun/runCard：相当于在平台界面点击某个节点的「测试」
- /ai-tools/trainRun/chat：在已有 sessionId 下继续对话（学生发言）

注意：
- 不在代码里硬编码 authorization / cookie，全部从 config.PLATFORM_CONFIG 或 workspace 平台配置中读取。
- 这里只提供最小封装；具体如何将其接入 SessionRunner，需要根据实际项目演进。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests

from config import PLATFORM_CONFIG


@dataclass
class PlatformTrainConfig:
    """平台训练任务配置（从 .env / platform_config.json 读取）"""

    base_url: str
    cookie: str
    authorization: str
    train_task_id: str

    @classmethod
    def from_env(cls) -> "PlatformTrainConfig":
        """从全局 PLATFORM_CONFIG 创建配置实例。"""
        base_url = PLATFORM_CONFIG.get("base_url") or "https://cloudapi.polymas.com"
        cookie = PLATFORM_CONFIG.get("cookie", "") or ""
        authorization = PLATFORM_CONFIG.get("authorization", "") or ""
        train_task_id = PLATFORM_CONFIG.get("train_task_id", "") or ""

        missing = []
        if not cookie:
            missing.append("PLATFORM_COOKIE")
        if not authorization:
            missing.append("PLATFORM_AUTHORIZATION")
        if not train_task_id:
            missing.append("PLATFORM_TRAIN_TASK_ID")

        if missing:
            raise ValueError(
                "平台配置不完整，缺少: " + ", ".join(missing)
                + "。请在平台配置页面或 .env 中填写。"
            )

        return cls(
            base_url=base_url.rstrip("/"),
            cookie=cookie,
            authorization=authorization,
            train_task_id=train_task_id,
        )


class PlatformTrainClient:
    """智慧树平台训练任务对话客户端（封装 runCard / chat 接口）"""

    def __init__(self, cfg: PlatformTrainConfig):
        self.cfg = cfg
        # 平台返回的会话 ID（第一次 runCard 后通常会返回）
        self.session_id: str = ""

    # ---------- 内部工具 ----------

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": self.cfg.authorization,
            "Cookie": self.cfg.cookie,
        }

    def _full_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.cfg.base_url + path

    def _update_session_id_from_resp(self, data: Dict[str, Any]) -> None:
        """从响应中更新 sessionId（兼容 code/msg/data 这一层结构）。"""
        # 顶层直接带 sessionId 的情况
        sid = data.get("sessionId")
        if isinstance(sid, str) and sid.strip():
            self.session_id = sid.strip()
            return

        # 更常见：{"code":200,"data":{"sessionId": "..."}}
        inner = data.get("data")
        if isinstance(inner, dict):
            sid2 = inner.get("sessionId")
            if isinstance(sid2, str) and sid2.strip():
                self.session_id = sid2.strip()

    # ---------- 对外方法 ----------

    def run_card(self, step_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """调用 /ai-tools/trainRun/runCard，模拟平台的「测试」按钮。

        Args:
            step_id: 平台节点 ID（Step ID）
            session_id: 现有会话 ID；为空字符串或 None 时相当于新建会话
        """
        url = self._full_url("/ai-tools/trainRun/runCard")
        payload = {
            "taskId": self.cfg.train_task_id,
            "stepId": step_id,
            "sessionId": session_id or self.session_id or "",
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            self._update_session_id_from_resp(data)
        return data

    def chat(self, step_id: str, text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """调用 /ai-tools/trainRun/chat，在已有 session 下以学生身份继续对话。

        Args:
            step_id: 当前节点 ID（与界面选中节点一致）
            text: 学生输入文本
            session_id: 可选 sessionId；默认使用上一次调用中记录的 session_id
        """
        url = self._full_url("/ai-tools/trainRun/chat")
        payload = {
            "taskId": self.cfg.train_task_id,
            "stepId": step_id,
            "text": text,
            "sessionId": session_id or self.session_id or "",
        }
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            self._update_session_id_from_resp(data)
        return data

    @staticmethod
    def extract_npc_reply(data: Dict[str, Any]) -> str:
        """从平台 chat/runCard 返回的 JSON 里提取 NPC 回复文本。

        由于不同环境返回结构可能略有差异，这里只做安全的几种常见尝试：
        - data['content'] / data['text']
        - data['data']['content'] / data['data']['text']

        若无法解析，则返回整个 JSON 的字符串表示，方便调试。
        """
        if not isinstance(data, dict):
            return str(data)

        for key in ("content", "text"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()

        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("content", "text"):
                v = inner.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        # 兜底：直接返回 JSON 字符串，方便你后续根据真实结构调整解析逻辑
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return str(data)

