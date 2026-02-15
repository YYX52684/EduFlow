"""
卡片加载器
支持从本地Markdown文件或平台API加载卡片数据。
卡片类型可扩展：通过 config.CARD_TYPES / CARD_TYPE_ROLE / CARD_SEQUENCE_ORDER 支持更多类型（如 C、D）。
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CardData:
    """卡片数据结构"""
    card_id: str              # 如 "1A", "1B", "2A" 等
    stage_num: int            # 阶段编号
    card_type: str            # "A"、"B" 或扩展类型（如 "C"）
    title: str                # 卡片标题
    
    # 核心内容
    full_content: str = ""    # 完整的markdown内容
    llm_prompt: str = ""      # A类卡片的LLM提示词
    transition_prompt: str = ""  # B类卡片的过渡提示词
    
    # 解析出的各部分
    role: str = ""            # 角色描述
    context: str = ""         # 上下文背景
    interaction: str = ""     # 交互逻辑
    transition: str = ""      # 跳转条件
    constraints: str = ""     # 约束条件
    prologue: str = ""        # 开场白（仅1A有）
    output: str = ""          # B类卡片的输出内容
    
    # 元数据
    stage_name: str = ""           # 阶段名称
    stage_description: str = ""    # 阶段描述
    interaction_rounds: int = 5    # 交互轮次
    model_id: str = ""             # 使用的模型
    
    def get_system_prompt(self) -> str:
        """获取用于NPC的系统提示词（对话类卡片）"""
        from config import CARD_TYPE_ROLE
        if CARD_TYPE_ROLE.get(self.card_type) == "dialogue":
            return self.llm_prompt or self.full_content
        return ""

    def get_transition_output(self) -> str:
        """获取过渡类卡片的输出"""
        from config import CARD_TYPE_ROLE
        if CARD_TYPE_ROLE.get(self.card_type) == "transition":
            return self.output or self.transition_prompt
        return ""


def _card_type_regex():
    """从 config.CARD_TYPES 生成卡片类型正则（如 AB -> [AB]，ABC -> [ABC]），向后兼容默认 AB。"""
    try:
        from config import CARD_TYPES
        types = (CARD_TYPES or "AB").strip() or "AB"
    except Exception:
        types = "AB"
    # 字符集，支持多字母类型
    return re.compile(r'^#\s*卡片(\d+)([' + re.escape(types) + r']+)\s*$', re.MULTILINE)


class LocalCardLoader:
    """从本地Markdown文件加载卡片"""

    def __init__(self):
        self._card_pattern = _card_type_regex()
    
    def load_from_markdown(self, md_path: str) -> List[CardData]:
        """
        从本地Markdown文件加载卡片
        
        Args:
            md_path: Markdown文件路径
            
        Returns:
            解析后的卡片列表
        """
        path = Path(md_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {md_path}")

        # 使用更宽容的读取方式：主要是我们自己生成的 cards_output_*.md 都是 UTF-8，
        # 但若用户用其他工具以非 UTF-8 保存，避免因单个非法字节导致整个模拟崩溃。
        with path.open("r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self.parse_markdown_content(content)
    
    def parse_markdown_content(self, content: str) -> List[CardData]:
        """解析Markdown内容"""
        cards = []
        sections = re.split(r'\n---\n', content)
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            match = self._card_pattern.search(section)
            if match:
                stage_num = int(match.group(1))
                card_type = match.group(2)
                card_id = f"{stage_num}{card_type}"
                
                card = self._parse_card_section(section, card_id, stage_num, card_type)
                cards.append(card)
        
        return cards
    
    def _parse_card_section(self, content: str, card_id: str, stage_num: int, card_type: str) -> CardData:
        """解析单个卡片内容"""
        card = CardData(
            card_id=card_id,
            stage_num=stage_num,
            card_type=card_type,
            title=f"卡片{card_id}",
            full_content=content
        )
        
        # 解析阶段元数据
        stage_meta = self._extract_stage_meta(content)
        if stage_meta:
            card.stage_name = stage_meta.get("stage_name", "")
            card.stage_description = stage_meta.get("description", "")
            card.interaction_rounds = stage_meta.get("interaction_rounds", 5)
        
        # 解析各章节
        sections = self._extract_sections(content)
        
        card.role = sections.get("Role", "")
        card.context = sections.get("Context", "")
        card.interaction = sections.get("Interaction", "")
        card.transition = sections.get("Transition", "")
        card.constraints = sections.get("Constraints", "")
        card.prologue = sections.get("Prologue", "")
        card.output = sections.get("Output", "")
        
        # 构建LLM提示词（对话类）或过渡提示（过渡类）
        try:
            from config import CARD_TYPE_ROLE
            role = CARD_TYPE_ROLE.get(card_type, "dialogue")
        except Exception:
            role = "dialogue" if card_type == "A" else "transition"
        if role == "dialogue":
            card.llm_prompt = self._build_a_card_prompt(content, card)
        else:
            card.transition_prompt = card.output

        return card
    
    def _build_a_card_prompt(self, content: str, card: CardData) -> str:
        """构建对话类卡片的LLM提示词"""
        prompt = content
        prompt = re.sub(r'^#\s*卡片\d+[A-Z]+\s*\n', '', prompt.strip())
        prompt = re.sub(r'<!--\s*STAGE_META:\s*\{.*?\}\s*-->\s*\n?', '', prompt)
        # 移除开场白部分（开场白单独使用，不加入系统提示）
        prompt = re.sub(r'#\s*Prologue\s*\n.*?(?=\n#\s|\Z)', '', prompt, flags=re.DOTALL)
        return prompt.strip()
    
    def _extract_stage_meta(self, content: str) -> Optional[Dict[str, Any]]:
        """提取阶段元数据"""
        meta_pattern = r'<!--\s*STAGE_META:\s*(\{.*?\})\s*-->'
        match = re.search(meta_pattern, content)
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None
    
    def _extract_sections(self, content: str) -> Dict[str, str]:
        """从卡片内容中提取各个章节"""
        sections = {}
        lines = content.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            # 检查是否是章节标题（# xxx，但不是 # 卡片xxx）
            if line.startswith('# ') and not line.startswith('# 卡片'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line[2:].strip()
                current_content = []
            elif current_section:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    
    def separate_cards(self, cards: List[CardData]) -> Tuple[List[CardData], List[CardData]]:
        """
        按 CARD_TYPE_ROLE 将卡片分为「对话类」与「过渡类」，兼容现有 a_cards / b_cards 语义。
        
        Returns:
            (a_cards, b_cards) - 对话类列表、过渡类列表（按 stage_num 排序）
        """
        try:
            from config import CARD_TYPE_ROLE
        except Exception:
            CARD_TYPE_ROLE = {"A": "dialogue", "B": "transition"}
        by_role = defaultdict(list)
        for c in cards:
            role = CARD_TYPE_ROLE.get(c.card_type, "dialogue")
            by_role[role].append(c)
        a_cards = by_role.get("dialogue", [])
        b_cards = by_role.get("transition", [])
        a_cards.sort(key=lambda x: (x.stage_num, x.card_type))
        b_cards.sort(key=lambda x: (x.stage_num, x.card_type))
        return a_cards, b_cards

    def get_card_sequence(self, cards: List[CardData], type_order: Optional[str] = None) -> List[CardData]:
        """
        获取按执行顺序排列的卡片序列。
        默认顺序由 CARD_SEQUENCE_ORDER 控制（如 "AB" 表示 1A->1B->2A->2B->...），可为更多类型扩展。
        """
        try:
            from config import CARD_SEQUENCE_ORDER
            order = (type_order or CARD_SEQUENCE_ORDER or "AB").strip() or "AB"
        except Exception:
            order = "AB"
        by_key = {}
        for c in cards:
            by_key[(c.stage_num, c.card_type)] = c
        stage_nums = sorted({c.stage_num for c in cards})
        sequence = []
        for sn in stage_nums:
            for t in order:
                if (sn, t) in by_key:
                    sequence.append(by_key[(sn, t)])
        return sequence


class PlatformCardLoader:
    """从智慧树平台API加载卡片（待实现）"""
    
    def __init__(self, api_config: dict):
        """
        初始化平台加载器
        
        Args:
            api_config: 平台API配置
        """
        self.base_url = api_config.get("base_url", "https://cloudapi.polymas.com")
        self.cookie = api_config.get("cookie", "")
        self.authorization = api_config.get("authorization", "")
    
    def load_from_platform(self, train_task_id: str) -> List[CardData]:
        """
        从智慧树平台拉取已配置项目的卡片数据
        
        注意：此功能需要教师端API支持，目前为待实现状态
        
        Args:
            train_task_id: 训练任务ID
            
        Returns:
            解析后的卡片列表
        """
        # TODO: 需要抓取教师端API来实现
        # 需要的API：
        # 1. 获取训练任务详情（节点列表、连线关系）
        # 2. 获取单个节点的详细配置（包括llmPrompt）
        raise NotImplementedError(
            "平台拉取功能待实现。\n"
            "需要先通过F12抓包获取以下API：\n"
            "1. 获取训练任务详情\n"
            "2. 获取节点prompt内容\n"
            "请使用本地文件模式：--simulate 'output/cards_output_xxx.md'"
        )
    
    def _fetch_task_details(self, train_task_id: str) -> dict:
        """获取训练任务详情（待实现）"""
        raise NotImplementedError()
    
    def _fetch_node_prompt(self, step_id: str) -> str:
        """获取节点的prompt内容（待实现）"""
        raise NotImplementedError()
