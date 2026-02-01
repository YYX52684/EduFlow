"""
卡片注入器
解析生成的Markdown文件，提取A类和B类卡片，注入到智慧树平台

重要说明：
- A类卡片 → 平台节点（ScriptStep）
- B类卡片 → 平台连线上的过渡提示词（transitionPrompt）
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from .api_client import PlatformAPIClient

# 导入卡片默认配置
try:
    from config import CARD_DEFAULTS
except ImportError:
    # 如果配置不存在，使用默认值（字段名已通过抓包确认）
    CARD_DEFAULTS = {
        "model_id": "",                    # modelId
        "history_num": 0,                  # historyRecordNum
        "trainer_name": "",                # trainerName
        "default_interaction_rounds": 5,   # interactiveRounds
    }


@dataclass
class ParsedCard:
    """解析后的卡片数据"""
    card_id: str  # 如 "1A", "1B", "2A" 等
    stage_num: int  # 阶段编号
    card_type: str  # "A" 或 "B"
    title: str  # 卡片标题
    full_content: str  # 完整的markdown内容
    
    # 解析出的各部分内容
    role: str = ""
    context: str = ""
    interaction_logic: str = ""
    judgment_logic: str = ""
    constraints: str = ""
    output_format: str = ""
    knowledge_points: List[str] = field(default_factory=list)
    
    # 新增：卡片节点配置字段
    stage_name: str = ""           # 阶段名称（简短，用于显示）
    stage_description: str = ""    # 阶段描述（详细说明）
    interaction_rounds: int = 0    # 交互轮次（0表示使用默认值）
    
    def to_a_card_format(self) -> dict:
        """
        A类卡片 → 平台节点格式
        合并LLM生成的字段和配置默认值
        """
        # 清理内容：移除markdown标题行和元数据注释
        content = self.full_content
        content = re.sub(r'^#\s*卡片\d+[AB]\s*\n', '', content.strip())
        content = re.sub(r'<!--\s*STAGE_META:\s*\{.*?\}\s*-->\s*\n?', '', content)
        
        # 使用阶段名称，如果没有则使用卡片标题
        step_name = self.stage_name if self.stage_name else self.title
        
        # 使用阶段描述，如果没有则生成默认描述
        description = self.stage_description if self.stage_description else f"阶段{self.stage_num} - 交互卡片"
        
        # 确定交互轮次：优先使用LLM建议，否则使用配置默认值
        interaction_rounds = self.interaction_rounds if self.interaction_rounds > 0 else CARD_DEFAULTS.get("default_interaction_rounds", 5)
        
        return {
            "step_name": step_name,
            "llm_prompt": content,
            "description": description,
            "prologue": "",
            # 配置字段（从CARD_DEFAULTS获取默认值，字段名已通过抓包确认）
            "interaction_rounds": interaction_rounds,           # -> interactiveRounds
            "model_id": CARD_DEFAULTS.get("model_id", ""),      # -> modelId
            "history_num": CARD_DEFAULTS.get("history_num", 0), # -> historyRecordNum
            "trainer_name": CARD_DEFAULTS.get("trainer_name", ""),  # -> trainerName
        }
    
    def to_b_card_format(self) -> dict:
        """
        B类卡片 → 连线过渡提示词格式
        包含跳转条件（默认使用"卡片XB"格式）
        """
        # 清理内容
        content = self.full_content
        content = re.sub(r'^#\s*卡片\d+[AB]\s*\n', '', content.strip())
        
        # 跳转条件：默认使用"卡片XB"格式，与A类卡片中的跳转指令对应
        flow_condition = f"卡片{self.stage_num}B"
        
        return {
            "transition_prompt": content,
            "flow_condition": flow_condition,
        }


class CardInjector:
    """卡片注入器"""
    
    def __init__(self, api_client: PlatformAPIClient):
        self.api = api_client
        self._card_pattern = re.compile(r'^#\s*卡片(\d+)([AB])\s*$', re.MULTILINE)
    
    def parse_markdown(self, md_path: str) -> List[ParsedCard]:
        """解析Markdown文件"""
        path = Path(md_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {md_path}")
        
        content = path.read_text(encoding='utf-8')
        return self.parse_markdown_content(content)
    
    def parse_markdown_content(self, content: str) -> List[ParsedCard]:
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
    
    def _parse_card_section(self, content: str, card_id: str, stage_num: int, card_type: str) -> ParsedCard:
        """解析单个卡片"""
        card = ParsedCard(
            card_id=card_id,
            stage_num=stage_num,
            card_type=card_type,
            title=f"卡片{card_id}",
            full_content=content
        )
        
        # 解析阶段元数据（如果存在）
        stage_meta = self._extract_stage_meta(content)
        if stage_meta:
            card.stage_name = stage_meta.get("stage_name", "")
            card.stage_description = stage_meta.get("description", "")
            card.interaction_rounds = stage_meta.get("interaction_rounds", 0)
        
        sections = self._extract_sections(content)
        
        if "Role" in sections:
            card.role = sections["Role"]
        if "Context" in sections:
            card.context = sections["Context"]
        if "Interaction Logic" in sections:
            card.interaction_logic = sections["Interaction Logic"]
        if "Judgment Logic" in sections:
            card.judgment_logic = sections["Judgment Logic"]
        if "Constraints" in sections:
            card.constraints = sections["Constraints"]
        if "Output Format" in sections:
            card.output_format = sections["Output Format"]
        
        return card
    
    def _extract_stage_meta(self, content: str) -> Optional[Dict[str, Any]]:
        """
        从卡片内容中提取阶段元数据
        
        元数据格式: <!-- STAGE_META: {"stage_name": "...", "description": "...", "interaction_rounds": 5} -->
        
        Args:
            content: 卡片内容
            
        Returns:
            解析后的元数据字典，如果不存在则返回None
        """
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
    
    def separate_cards(self, cards: List[ParsedCard]) -> tuple:
        """
        将卡片分离为A类和B类
        
        Returns:
            (a_cards, b_cards) - A类卡片列表和B类卡片列表
        """
        a_cards = [c for c in cards if c.card_type == "A"]
        b_cards = [c for c in cards if c.card_type == "B"]
        
        # 按阶段号排序
        a_cards.sort(key=lambda x: x.stage_num)
        b_cards.sort(key=lambda x: x.stage_num)
        
        return a_cards, b_cards
    
    def inject_from_file(
        self,
        md_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        从Markdown文件注入卡片到平台
        
        Args:
            md_path: Markdown文件路径
            progress_callback: 进度回调
            
        Returns:
            注入结果
        """
        if progress_callback:
            progress_callback(0, 100, "正在解析Markdown文件...")
        
        # 解析所有卡片
        all_cards = self.parse_markdown(md_path)
        
        if not all_cards:
            raise ValueError(f"未能从文件 {md_path} 中解析出任何卡片")
        
        # 分离A类和B类卡片
        a_cards, b_cards = self.separate_cards(all_cards)
        
        if progress_callback:
            progress_callback(10, 100, f"解析完成: {len(a_cards)} 个A类卡片, {len(b_cards)} 个B类卡片")
        
        print(f"\n解析结果:")
        print(f"  A类卡片（节点）: {len(a_cards)} 个")
        print(f"  B类卡片（连线提示词）: {len(b_cards)} 个")
        
        # 转换为平台格式
        a_card_data = [card.to_a_card_format() for card in a_cards]
        b_card_data = [card.to_b_card_format() for card in b_cards]
        
        # 创建进度包装器
        def wrapped_progress(current: int, total: int, message: str):
            if progress_callback:
                progress = 10 + int((current / max(total, 1)) * 90)
                progress_callback(progress, 100, message)
        
        # 调用API注入
        result = self.api.inject_cards(
            a_cards=a_card_data,
            b_cards=b_card_data,
            progress_callback=wrapped_progress
        )
        
        if progress_callback:
            progress_callback(100, 100, "完成")
        
        return {
            "total_a_cards": len(a_cards),
            "total_b_cards": len(b_cards),
            "successful_a_cards": result["stats"]["successful_a_cards"],
            "successful_b_cards": result["stats"]["successful_b_cards"],
            "step_ids": result["step_ids"],
            "flow_ids": result["flow_ids"],
            "a_cards": [{"card_id": c.card_id, "title": c.title} for c in a_cards],
            "b_cards": [{"card_id": c.card_id, "title": c.title} for c in b_cards],
        }
    
    def preview_cards(self, md_path: str) -> None:
        """预览解析结果"""
        all_cards = self.parse_markdown(md_path)
        a_cards, b_cards = self.separate_cards(all_cards)
        
        print(f"\n{'='*60}")
        print(f"解析结果预览")
        print(f"{'='*60}")
        print(f"文件: {md_path}")
        print(f"{'='*60}")
        
        print(f"\n【A类卡片】共 {len(a_cards)} 个 → 将创建为平台节点")
        print("-" * 40)
        for card in a_cards:
            # 获取格式化后的数据以显示配置
            card_data = card.to_a_card_format()
            print(f"  [{card.card_id}] {card_data['step_name']}")
            if card.stage_description:
                desc_preview = card.stage_description[:50].replace('\n', ' ')
                print(f"       描述: {desc_preview}...")
            print(f"       交互轮次: {card_data['interaction_rounds']}")
            if card.role:
                role_preview = card.role[:50].replace('\n', ' ') + "..." if len(card.role) > 50 else card.role.replace('\n', ' ')
                print(f"       角色: {role_preview}")
        
        print(f"\n【B类卡片】共 {len(b_cards)} 个 → 将设置为连线过渡提示词")
        print("-" * 40)
        for i, card in enumerate(b_cards):
            if i < len(a_cards) - 1:
                print(f"  [{card.card_id}] 连接 卡片{a_cards[i].card_id} → 卡片{a_cards[i+1].card_id}")
            else:
                print(f"  [{card.card_id}] {card.title}")
        
        print(f"\n【默认配置】（从 config.py / .env 读取）")
        print("-" * 40)
        print(f"  AI模型: {CARD_DEFAULTS.get('model_id', '(未设置)')}")
        print(f"  历史记录: {CARD_DEFAULTS.get('history_num', -1)} (-1表示全部)")
        print(f"  训练官名称: {CARD_DEFAULTS.get('trainer_name', 'ai')}")
        print(f"  声音ID: {CARD_DEFAULTS.get('voice_id', '(默认)')}")
        
        print(f"\n{'='*60}")
        print(f"注入流程:")
        print(f"  1. 创建 {len(a_cards)} 个节点（A类卡片）")
        print(f"  2. 创建 {len(a_cards)-1} 条连线")
        print(f"  3. 在连线上设置 {len(b_cards)} 个过渡提示词（B类卡片）")
        print(f"{'='*60}")
    
    def validate_cards(self, cards: List[ParsedCard]) -> List[Dict[str, Any]]:
        """验证卡片数据"""
        issues = []
        a_cards, b_cards = self.separate_cards(cards)
        
        # 检查A类和B类卡片数量匹配
        expected_b = len(a_cards) - 1
        if len(b_cards) != expected_b:
            issues.append({
                "type": "count_mismatch",
                "message": f"B类卡片数量({len(b_cards)})应该是A类卡片数量({len(a_cards)})-1={expected_b}"
            })
        
        # 检查各卡片内容
        for card in cards:
            card_issues = []
            
            if not card.full_content or len(card.full_content) < 50:
                card_issues.append("内容过短")
            
            if card.card_type == "A" and not card.role:
                card_issues.append("A类卡片缺少Role部分")
            
            if card_issues:
                issues.append({
                    "card_id": card.card_id,
                    "issues": card_issues
                })
        
        return issues
