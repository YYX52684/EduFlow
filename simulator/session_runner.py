"""
会话运行器
负责协调NPC和学生之间的对话流程

支持三种模式：
- auto: 全自动（LLM扮演学生）
- manual: 全手动（终端输入）
- hybrid: 混合模式（可随时切换）
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum

from .card_loader import LocalCardLoader, CardData
from .llm_npc import LLMNPC, NPCFactory
from .student_persona import StudentPersona, PersonaManager
from .llm_student import LLMStudent, StudentFactory, ManualStudent


class SessionMode(Enum):
    """会话模式"""
    AUTO = "auto"        # 全自动
    MANUAL = "manual"    # 手动输入
    HYBRID = "hybrid"    # 混合模式


@dataclass
class SessionConfig:
    """会话配置"""
    mode: SessionMode = SessionMode.AUTO
    persona_id: str = "excellent"           # 人设标识
    max_rounds_per_card: int = 10           # 每张卡片最大对话轮次
    total_max_rounds: int = 100             # 总最大对话轮次
    output_dir: str = "simulator_output"    # 输出目录
    verbose: bool = False                   # 详细输出
    save_logs: bool = True                  # 是否保存对话日志

    # 自定义人设根目录（如工作区 output/persona_lib）；为空则用默认 simulator_config/custom
    custom_persona_dir: Optional[str] = None
    # NPC配置（可选，None表示从环境变量读取）
    npc_config: Optional[dict] = None
    # 学生模拟器配置（可选）
    student_config: Optional[dict] = None
    # 进度回调（phase, message），仿真过程中切换卡片时调用
    progress_callback: Optional[Callable[[str, str], None]] = None


@dataclass
class DialogueTurn:
    """单轮对话"""
    turn_number: int
    card_id: str
    speaker: str           # "npc" 或 "student"
    content: str
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionLog:
    """会话日志"""
    session_id: str
    start_time: str
    end_time: str = ""
    config: dict = field(default_factory=dict)
    cards_used: List[str] = field(default_factory=list)
    dialogue: List[DialogueTurn] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "config": self.config,
            "cards_used": self.cards_used,
            "dialogue": [
                {
                    "turn": d.turn_number,
                    "card_id": d.card_id,
                    "speaker": d.speaker,
                    "content": d.content,
                    "timestamp": d.timestamp,
                }
                for d in self.dialogue
            ],
            "summary": self.summary,
        }
    
    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        lines = [
            f"# 对话日志",
            f"",
            f"**会话ID**: {self.session_id}",
            f"**开始时间**: {self.start_time}",
            f"**结束时间**: {self.end_time}",
            f"**使用卡片**: {', '.join(self.cards_used)}",
            f"**总轮次**: {len([d for d in self.dialogue if d.speaker == 'student'])}",
            f"",
            f"---",
            f"",
            f"## 对话记录",
            f"",
        ]
        
        current_card = ""
        for turn in self.dialogue:
            if turn.card_id != current_card:
                current_card = turn.card_id
                lines.append(f"\n### {current_card}\n")
            
            speaker_label = "NPC" if turn.speaker == "npc" else "学生"
            lines.append(f"**[{speaker_label}]**: {turn.content}\n")
        
        if self.summary:
            lines.extend([
                f"",
                f"---",
                f"",
                f"## 会话总结",
                f"",
                f"- 总轮次: {self.summary.get('total_turns', 0)}",
                f"- 使用卡片数: {self.summary.get('cards_count', 0)}",
                f"- 会话状态: {self.summary.get('status', 'unknown')}",
            ])
        
        return "\n".join(lines)


class SessionRunner:
    _ANCHOR_STOPWORDS = {
        "我们", "你们", "这个", "那个", "以及", "然后", "还有", "就是", "已经", "可以", "需要",
        "进行", "相关", "问题", "情况", "内容", "方面", "这些", "那些", "一下", "因为", "所以",
        "如果", "那么", "然后", "继续", "说明", "分析", "回答", "学生", "老师", "参数", "系统",
    }

    """会话运行器"""
    
    def __init__(self, config: SessionConfig = None):
        """
        初始化会话运行器
        
        Args:
            config: 会话配置
        """
        self.config = config or SessionConfig()
        
        # 组件
        self.card_loader = LocalCardLoader()
        self.persona_manager = PersonaManager(
            custom_dir=self.config.custom_persona_dir
        ) if self.config.custom_persona_dir else PersonaManager()
        
        self.npc: Optional[LLMNPC] = None
        self.student: Optional[Union[LLMStudent, ManualStudent]] = None
        
        # 状态
        self.cards: List[CardData] = []
        self.a_cards: List[CardData] = []
        self.b_cards: List[CardData] = []
        self.current_card_index: int = 0
        self.turn_count: int = 0
        self.card_turn_count: int = 0
        
        # 日志
        self.log: Optional[SessionLog] = None
        
        # 输出目录
        self.output_dir = Path(self.config.output_dir)
        self.logs_dir = self.output_dir / "logs"
    
    def load_cards(self, md_path: str):
        """
        加载卡片
        
        Args:
            md_path: Markdown文件路径
        """
        self.cards = self.card_loader.load_from_markdown(md_path)
        self.a_cards, self.b_cards = self.card_loader.separate_cards(self.cards)
        
        if not self.a_cards:
            raise ValueError(f"未能从文件中解析出A类卡片: {md_path}")
        
        print(f"[加载] 共加载 {len(self.a_cards)} 个对话卡, {len(self.b_cards)} 个过渡卡")
    
    def setup(self):
        """设置会话组件"""
        # 加载人设
        persona = self.persona_manager.get_persona(self.config.persona_id)
        print(f"[人设] 使用人设: {persona.name} ({persona.persona_type})")
        
        # 创建学生模拟器
        if self.config.mode == SessionMode.MANUAL:
            self.student = ManualStudent()
        else:
            if self.config.student_config:
                self.student = LLMStudent(persona, self.config.student_config)
            else:
                self.student = StudentFactory.create_from_env(persona)
        
        # 初始化NPC（稍后在run时根据当前卡片创建）
        self.npc = None
        
        # 重置状态
        self.current_card_index = 0
        self.turn_count = 0
        self.card_turn_count = 0
        
        # 初始化日志
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log = SessionLog(
            session_id=session_id,
            start_time=datetime.now().isoformat(),
            config={
                "mode": self.config.mode.value,
                "persona_id": self.config.persona_id,
                "max_rounds_per_card": self.config.max_rounds_per_card,
            },
            cards_used=[c.card_id for c in self.a_cards],
        )
        
        # 确保输出目录存在
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self) -> SessionLog:
        """
        运行会话
        
        Returns:
            会话日志
        """
        print("\n" + "=" * 60)
        print("开始模拟会话")
        print("=" * 60)
        
        try:
            total_cards = len(self.a_cards)
            while self.current_card_index < total_cards:
                current_card = self.a_cards[self.current_card_index]
                idx = self.current_card_index + 1
                if self.config.progress_callback:
                    self.config.progress_callback(
                        "simulate",
                        f"仿真中… 阶段 {idx}/{total_cards}",
                    )
                
                print(f"\n{'='*40}")
                print(f"[阶段 {current_card.stage_num}] {current_card.stage_name or current_card.title}")
                print(f"{'='*40}")
                
                # 创建/切换NPC
                self._switch_to_card(current_card)
                
                # 运行当前卡片的对话
                transition = self._run_card_dialogue(current_card)
                
                # 处理跳转
                if transition:
                    self._handle_transition(transition, current_card)
                else:
                    # 达到轮次上限，直接进入下一张卡片
                    self.current_card_index += 1
                
                # 检查是否超过总轮次上限
                if self.turn_count >= self.config.total_max_rounds:
                    print(f"\n[警告] 达到总轮次上限 ({self.config.total_max_rounds})，结束会话")
                    break
            
            # 完成
            self.log.end_time = datetime.now().isoformat()
            self.log.summary = {
                "total_turns": self.turn_count,
                "cards_count": self.current_card_index + 1,
                "status": "completed",
            }
            
            print("\n" + "=" * 60)
            print("[完成] 会话结束")
            print(f"  总轮次: {self.turn_count}")
            print(f"  使用卡片: {self.current_card_index + 1}/{len(self.a_cards)}")
            print("=" * 60)
            
            # 保存日志
            if self.config.save_logs:
                self._save_log()
            
            return self.log
            
        except KeyboardInterrupt:
            print("\n[中断] 用户中断会话")
            self.log.end_time = datetime.now().isoformat()
            self.log.summary = {
                "total_turns": self.turn_count,
                "cards_count": self.current_card_index + 1,
                "status": "interrupted",
            }
            if self.config.save_logs:
                self._save_log()
            return self.log
        
        except Exception as e:
            print(f"\n[错误] 会话异常: {e}")
            self.log.end_time = datetime.now().isoformat()
            self.log.summary = {
                "total_turns": self.turn_count,
                "cards_count": self.current_card_index + 1,
                "status": "error",
                "error": str(e),
            }
            if self.config.save_logs:
                self._save_log()
            raise
    
    def _switch_to_card(self, card: CardData):
        """切换到指定卡片"""
        prompt = card.get_system_prompt()
        
        if self.npc is None:
            # 首次创建NPC
            if self.config.npc_config:
                self.npc = LLMNPC(prompt, self.config.npc_config)
            else:
                self.npc = NPCFactory.create_with_card_config(prompt, card.model_id)
        else:
            # 切换卡片，保留历史
            self.npc.switch_to_card(prompt, preserve_history=True)
        
        # 更新学生的场景上下文
        if isinstance(self.student, LLMStudent):
            context = f"当前阶段: {card.stage_name or card.title}\n"
            if card.context:
                context += f"背景: {card.context}"
            self.student.set_scene_context(context)
        
        # 重置卡片轮次计数
        self.card_turn_count = 0
    
    def _run_card_dialogue(self, card: CardData) -> Optional[str]:
        """
        运行单张卡片的对话
        
        Returns:
            跳转目标（如果有）
        """
        # 发送开场白（如果是第一张卡片且有开场白）
        if self.current_card_index == 0 and card.prologue:
            prologue = self.npc.send_prologue(card.prologue)
            self._log_turn(card.card_id, "npc", prologue)
            print(f"\n[NPC开场白]: {prologue}")
            
            # 学生回应开场白
            student_response = self._get_student_response(prologue)
            self._log_turn(card.card_id, "student", student_response)
            self.turn_count += 1
            self.card_turn_count += 1
        
        # 对话循环
        while self.card_turn_count < self.config.max_rounds_per_card:
            # 获取学生消息（首轮可能是对开场白的回应，后续是对NPC回复的回应）
            if self.card_turn_count == 0:
                # 如果没有开场白，学生先发起对话
                student_message = self._get_student_first_message()
            else:
                # 继续对话（学生消息已在上一轮末尾获取）
                student_message = None
            
            # NPC回复
            if student_message or self.npc.history:
                last_student_msg = student_message or self.npc.history[-1].content if self.npc.history else ""
                
                if last_student_msg:
                    npc_prompt = (
                        "请基于学生这条最新回答继续推进。"
                        "避免围绕同一小知识点连续追问超过2轮；若已连续2轮没有新增信息，"
                        "请先做一句阶段性收束并切换到本幕下一个关键要点。\n\n"
                        f"学生最新回答：{last_student_msg}"
                    )
                    npc_response = self.npc.respond(npc_prompt)
                    
                    # 检查跳转指令
                    transition = self.npc.check_transition(npc_response)
                    clean_response = self.npc.get_clean_response(npc_response)
                    
                    self._log_turn(card.card_id, "npc", clean_response)
                    print(f"\n[NPC]: {clean_response}")
                    
                    if transition:
                        print(f"\n[跳转] 检测到跳转指令: {transition}")
                        return transition
                    
                    # 学生回应
                    student_response = self._get_student_response(clean_response)
                    self._log_turn(card.card_id, "student", student_response)
                    
                    self.turn_count += 1
                    self.card_turn_count += 1
            else:
                # 没有对话历史，学生先开始
                student_message = self._get_student_first_message()
                self._log_turn(card.card_id, "student", student_message)
                
                npc_prompt = (
                    "请基于学生这条最新回答继续推进。"
                    "避免围绕同一小知识点连续追问超过2轮；若已连续2轮没有新增信息，"
                    "请先做一句阶段性收束并切换到本幕下一个关键要点。\n\n"
                    f"学生最新回答：{student_message}"
                )
                npc_response = self.npc.respond(npc_prompt)
                transition = self.npc.check_transition(npc_response)
                clean_response = self.npc.get_clean_response(npc_response)
                
                self._log_turn(card.card_id, "npc", clean_response)
                print(f"\n[NPC]: {clean_response}")
                
                if transition:
                    return transition
                
                self.turn_count += 1
                self.card_turn_count += 1
        
        print(f"\n[提示] 达到单卡片轮次上限 ({self.config.max_rounds_per_card})")
        return None
    
    def _get_student_first_message(self) -> str:
        """获取学生的首条消息"""
        prompt = "老师好，我准备好了，请开始。"
        if isinstance(self.student, LLMStudent):
            return self.student.generate_response(prompt)
        else:
            print("\n[提示] 请输入学生的开场发言")
            return self.student.generate_response(prompt)
    
    def _get_student_response(self, npc_message: str) -> str:
        """获取学生对NPC消息的回复"""
        response = self.student.generate_response(npc_message)
        print(f"\n[学生]: {response}")
        return response
    
    def _handle_transition(self, transition: str, current_card: CardData):
        """
        处理跳转指令
        
        Args:
            transition: 跳转目标（如"卡片2A"、"卡片1B"）
            current_card: 当前卡片
        """
        # 查找对应的B类卡片
        b_card = next(
            (b for b in self.b_cards if b.stage_num == current_card.stage_num),
            None
        )
        
        if b_card:
            transition_text = self._run_transition_card(b_card, current_card)
            if transition_text:
                print(f"\n[过渡] {transition_text}")
                self._log_turn(b_card.card_id, "npc", transition_text)
        
        # 移动到下一张A类卡片
        self.current_card_index += 1

    def _run_transition_card(self, b_card: CardData, current_card: CardData) -> str:
        """执行 B 类卡片：基于上一张A卡最后一轮对话做回应，再过渡。"""
        dialogue_context = self._build_transition_dialogue_context(current_card)
        anchor_keywords = self._extract_recent_student_keywords(current_card)
        prompt = b_card.render_transition_prompt(dialogue_context)
        if not prompt:
            return b_card.get_transition_output()

        try:
            transition_npc = self._build_transition_npc(prompt, b_card)
            response = transition_npc.respond(
                "请根据系统提示，先回应上一张A卡最后一轮学生回答，再自然衔接下一环节。"
                "不要做泛泛的整体总结。输出建议50-120词，硬上限不超过150词。"
            )
            clean_response = transition_npc.get_clean_response(response)
            if anchor_keywords and not self._contains_anchor_keyword(clean_response, anchor_keywords):
                # 强历史锚定重试：要求命中至少一个最近学生关键词
                must_hit = "、".join(anchor_keywords[:3])
                retry_instruction = (
                    "请重写上一条过渡回复：必须先回应学生最后一轮的具体表达，"
                    f"并至少出现以下关键词之一：{must_hit}。"
                    "不要做静态总结，随后给出下一步具体任务。"
                    "输出建议50-120词，硬上限不超过150词。"
                )
                retry_response = transition_npc.respond(retry_instruction)
                retry_clean = transition_npc.get_clean_response(retry_response)
                if retry_clean:
                    clean_response = retry_clean

            if anchor_keywords and not self._contains_anchor_keyword(clean_response, anchor_keywords):
                clean_response = self._force_anchor_into_transition(clean_response, anchor_keywords)

            return clean_response or b_card.get_transition_output()
        except Exception as e:
            print(f"\n[警告] B类卡片执行失败，回退到静态输出: {e}")
            return b_card.get_transition_output()

    def _build_transition_npc(self, prompt: str, card: CardData) -> LLMNPC:
        """创建一个临时 NPC 来执行 B 类卡片。"""
        if self.npc is not None:
            return LLMNPC(
                prompt,
                {
                    "api_url": self.npc.api_url,
                    "api_key": self.npc.api_key,
                    "model": self.npc.model,
                    "service_code": self.npc.service_code,
                    "max_tokens": self.npc.max_tokens,
                    "temperature": self.npc.temperature,
                },
            )
        if self.config.npc_config:
            return LLMNPC(prompt, self.config.npc_config)
        return NPCFactory.create_with_card_config(prompt, card.model_id)

    def _build_transition_dialogue_context(self, current_card: CardData) -> str:
        """整理上一张A卡的对话记录，并突出最后一轮，供 B 类卡片回应。"""
        turns = [turn for turn in self.log.dialogue if turn.card_id == current_card.card_id]
        if not turns:
            return "上一张A卡暂无可用对话记录。若无法判断最后一轮细节，就先做一句自然承接，再进入下一环节。"

        lines = ["## 上一张A卡对话记录"]
        for turn in turns:
            speaker_label = "NPC" if turn.speaker == "npc" else "学生"
            lines.append(f"{speaker_label}: {turn.content}")

        last_student_idx = max(
            (idx for idx, turn in enumerate(turns) if turn.speaker == "student"),
            default=-1,
        )
        if last_student_idx >= 0:
            lines.extend(["", "## 最后一轮重点"])
            previous_npc = next(
                (
                    turns[idx].content
                    for idx in range(last_student_idx - 1, -1, -1)
                    if turns[idx].speaker == "npc"
                ),
                "",
            )
            if previous_npc:
                lines.append(f"上一问: {previous_npc}")
            lines.append(f"学生最后一轮回答: {turns[last_student_idx].content}")

        return "\n".join(lines)

    def _extract_recent_student_keywords(self, current_card: CardData, limit: int = 5) -> List[str]:
        """从上一张A卡最近学生回复中提取关键词（过滤停用词）。"""
        turns = [turn for turn in self.log.dialogue if turn.card_id == current_card.card_id and turn.speaker == "student"]
        if not turns:
            return []
        last_student = turns[-1].content or ""
        # 提取中文连续词片段与英文术语
        raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_\-]{2,}", last_student)
        keywords: List[str] = []
        for token in raw_tokens:
            t = token.strip()
            if not t or t in self._ANCHOR_STOPWORDS:
                continue
            if t not in keywords:
                keywords.append(t)
            if len(keywords) >= limit:
                break
        return keywords

    @staticmethod
    def _contains_anchor_keyword(text: Optional[str], keywords: List[str]) -> bool:
        if not text or not keywords:
            return False
        return any(k and k in text for k in keywords)

    @staticmethod
    def _force_anchor_into_transition(text: Optional[str], keywords: List[str]) -> str:
        """兜底：若模型未命中关键词，强制在开头注入一个锚点。"""
        base = (text or "").strip()
        kw = next((k for k in keywords if k), "")
        if not kw:
            return base
        prefix = f"你刚才提到“{kw}”，这个点先落实。"
        if not base:
            return prefix + "请继续说明下一步要怎么做。"
        if kw in base:
            return base
        return prefix + base
    
    def _log_turn(self, card_id: str, speaker: str, content: str):
        """记录对话轮次"""
        turn = DialogueTurn(
            turn_number=len(self.log.dialogue) + 1,
            card_id=card_id,
            speaker=speaker,
            content=content,
            timestamp=datetime.now().isoformat(),
        )
        self.log.dialogue.append(turn)
    
    def _save_log(self):
        """保存会话日志"""
        # 保存JSON格式
        json_path = self.logs_dir / f"session_{self.log.session_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.log.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 保存Markdown格式
        md_path = self.logs_dir / f"session_{self.log.session_id}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(self.log.to_markdown())
        
        print(f"\n[保存] 对话日志已保存:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {md_path}")
    
    def get_dialogue_for_evaluation(self) -> List[Dict[str, str]]:
        """
        获取用于评估的对话记录
        
        Returns:
            格式化的对话列表
        """
        return [
            {
                "turn": d.turn_number,
                "card_id": d.card_id,
                "speaker": d.speaker,
                "content": d.content,
            }
            for d in self.log.dialogue
        ]


def run_simulation(
    md_path: str,
    persona_id: str = "excellent",
    mode: str = "auto",
    output_dir: str = "simulator_output",
    verbose: bool = False,
) -> SessionLog:
    """
    便捷函数：运行模拟会话
    
    Args:
        md_path: 卡片Markdown文件路径
        persona_id: 人设标识符
        mode: 会话模式 (auto/manual/hybrid)
        output_dir: 输出目录
        verbose: 详细输出
        
    Returns:
        会话日志
    """
    config = SessionConfig(
        mode=SessionMode(mode),
        persona_id=persona_id,
        output_dir=output_dir,
        verbose=verbose,
    )
    
    runner = SessionRunner(config)
    runner.load_cards(md_path)
    runner.setup()
    
    return runner.run()
