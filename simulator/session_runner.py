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
                    npc_response = self.npc.respond(last_student_msg)
                    
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
                
                npc_response = self.npc.respond(student_message)
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
        
        if b_card and b_card.output:
            # 输出B类卡片的过渡内容
            print(f"\n[过渡] {b_card.get_transition_output()}")
            self._log_turn(b_card.card_id, "npc", b_card.get_transition_output())
        
        # 移动到下一张A类卡片
        self.current_card_index += 1
    
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
