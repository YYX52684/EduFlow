"""
智慧树平台API客户端
封装与平台的所有API交互

重要说明：
- A类卡片 = 节点（ScriptStep），使用 createScriptStep
- B类卡片 = 连线上的过渡提示词（transitionPrompt），使用 createScriptStepFlow + editScriptStepFlow
"""

import requests
import json
import time
import random
import string
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


def generate_step_id() -> str:
    """生成唯一的步骤ID（节点ID）"""
    chars = string.ascii_letters + string.digits + "_-"
    return ''.join(random.choices(chars, k=21))


def generate_flow_id() -> str:
    """生成唯一的连线ID"""
    chars = string.ascii_letters + string.digits + "_-"
    return ''.join(random.choices(chars, k=21))


class PlatformAPIClient:
    """智慧树平台API客户端"""
    
    def __init__(self, config: dict):
        """
        初始化API客户端
        
        Args:
            config: 平台配置字典
        """
        self.base_url = config.get("base_url", "https://cloudapi.polymas.com").rstrip("/")
        self.course_id = config.get("course_id", "")
        self.train_task_id = config.get("train_task_id", "")
        self.start_node_id = config.get("start_node_id", "")  # 训练开始节点
        self.end_node_id = config.get("end_node_id", "")      # 训练结束节点
        
        # 初始化session
        self.session = requests.Session()
        
        # 设置默认headers
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh,en;q=0.9,en-US;q=0.8,zh-CN;q=0.7",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Origin": "https://hike-teaching-center.polymas.com",
            "Referer": "https://hike-teaching-center.polymas.com/",
        })
        
        # 设置Cookie和Authorization
        cookie = config.get("cookie", "")
        if cookie:
            self.session.headers["Cookie"] = cookie
        
        authorization = config.get("authorization", "")
        if authorization:
            self.session.headers["Authorization"] = authorization
        
        # API端点
        self.endpoints = {
            "create_step": "/teacher-course/abilityTrain/createScriptStep",
            "edit_step": "/teacher-course/abilityTrain/editScriptStep",
            "create_flow": "/teacher-course/abilityTrain/createScriptStepFlow",
            "edit_flow": "/teacher-course/abilityTrain/editScriptStepFlow",
            "edit_configuration": "/teacher-course/abilityTrain/editConfiguration",
            "create_score_item": "/teacher-course/abilityTrain/createScoreItem",
        }
    
    def set_endpoints(self, endpoints: dict):
        """设置API端点（可覆盖默认值）"""
        self.endpoints.update(endpoints)
        
        # 卡片位置跟踪
        self._next_position = {"x": 200, "y": 100}
        self._position_step = {"x": 0, "y": 200}  # 纵向排列
    
    def _get_next_position(self) -> dict:
        """获取下一个卡片的位置"""
        pos = self._next_position.copy()
        self._next_position["x"] += self._position_step["x"]
        self._next_position["y"] += self._position_step["y"]
        return pos
    
    def reset_position(self, start_x: int = 570, start_y: int = 100):
        """重置卡片位置"""
        self._next_position = {"x": start_x, "y": start_y}
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[dict] = None,
        retry_count: int = 3,
        retry_delay: float = 1.0
    ) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 401:
                    raise RuntimeError("认证失败，请检查Cookie和Authorization是否有效或已过期")
                elif response.status_code == 403:
                    raise RuntimeError("权限不足")
                elif response.status_code >= 500:
                    if attempt < retry_count - 1:
                        time.sleep(retry_delay)
                        continue
                    raise RuntimeError(f"服务器错误: {response.status_code}")
                
                response.raise_for_status()
                
                try:
                    result = response.json()
                    if isinstance(result, dict):
                        code = result.get("code") or result.get("status")
                        if code and code != 200 and code != 0:
                            msg = result.get("message") or result.get("msg") or "未知错误"
                            raise RuntimeError(f"API错误: {msg}")
                    return result
                except json.JSONDecodeError:
                    return {"raw_response": response.text}
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < retry_count - 1:
                    time.sleep(retry_delay)
                    continue
                raise RuntimeError(f"连接错误: {e}")
            except requests.exceptions.Timeout:
                if attempt < retry_count - 1:
                    time.sleep(retry_delay)
                    continue
                raise RuntimeError("请求超时")
        
        raise RuntimeError("请求失败，已达到最大重试次数")
    
    # ========== A类卡片（节点）操作 ==========
    
    def create_step(
        self, 
        step_name: str,
        llm_prompt: str,
        description: str = "",
        prologue: str = "",
        step_id: Optional[str] = None,
        position: Optional[dict] = None,
        # 卡片配置参数（字段名已通过抓包确认）
        interaction_rounds: int = 5,
        model_id: str = "",
        history_num: int = 0,
        trainer_name: str = ""
    ) -> dict:
        """
        创建A类卡片（节点）
        
        Args:
            step_name: 节点名称
            llm_prompt: LLM提示词（A类卡片内容）
            description: 描述
            prologue: 开场白
            step_id: 步骤ID（可选，自动生成）
            position: 位置（可选，自动计算）
            interaction_rounds: 交互轮次（interactiveRounds，默认5）
            model_id: AI模型ID（modelId，如 Doubao-Seed-1.6）
            history_num: 历史记录数量（historyRecordNum，0=不保留，-1=全部）
            trainer_name: 虚拟训练官名字（trainerName）
            
        Returns:
            包含step_id的结果
        """
        if not step_id:
            step_id = generate_step_id()
        
        if not position:
            position = self._get_next_position()
        
        request_body = {
            "trainTaskId": self.train_task_id,
            "stepId": step_id,
            "courseId": self.course_id,
            "libraryFolderId": "",
            "positionDTO": {
                "x": position.get("x", 570),
                "y": position.get("y", 100)
            },
            "stepDetailDTO": {
                "nodeType": "SCRIPT_NODE",
                "stepName": step_name,
                "description": description,
                "prologue": prologue,
                "modelId": model_id,
                "llmPrompt": llm_prompt,
                "knowledgeBaseSwitch": 0,
                "searchEngineSwitch": 0,
                "videoSwitch": 0,
                "whiteBoardSwitch": 0,
                "trainSubType": "ability",
                "trainerName": trainer_name,
                "scriptStepCover": {},
                "scriptStepResourceList": [],
                # 字段名已通过抓包确认
                "interactiveRounds": interaction_rounds,  # 交互轮次
                "historyRecordNum": history_num,          # 历史记录数量
            }
        }
        
        result = self._make_request("POST", self.endpoints["create_step"], data=request_body)
        result["_step_id"] = step_id
        return result
    
    def edit_step(self, step_id: str, llm_prompt: str, step_name: str = "", description: str = "") -> dict:
        """
        修改A类卡片（节点）
        """
        request_body = {
            "trainTaskId": self.train_task_id,
            "stepId": step_id,
            "courseId": self.course_id,
            "libraryFolderId": "",
            "positionDTO": {"x": 570, "y": 300},
            "stepDetailDTO": {
                "nodeType": "SCRIPT_NODE",
                "stepName": step_name,
                "description": description,
                "prologue": "",
                "modelId": "",
                "llmPrompt": llm_prompt,
                "knowledgeBaseSwitch": 0,
                "searchEngineSwitch": 0,
                "videoSwitch": 0,
                "whiteBoardSwitch": 0,
                "trainSubType": "ability",
                "trainerName": "",
                "scriptStepCover": {},
                "scriptStepResourceList": [],
                "useTransitionDescriptionAsAudio": False,
                "useVideoOriginalSoundAsAudio": False,
            }
        }
        
        return self._make_request("POST", self.endpoints["edit_step"], data=request_body)
    
    # ========== 连线操作（B类卡片在连线上） ==========
    
    def create_flow(
        self,
        start_step_id: str,
        end_step_id: str,
        flow_id: Optional[str] = None
    ) -> dict:
        """
        创建连线（连接两个A类卡片节点）
        
        Args:
            start_step_id: 起始节点ID
            end_step_id: 结束节点ID
            flow_id: 连线ID（可选，自动生成）
            
        Returns:
            包含flow_id的结果
        """
        if not flow_id:
            flow_id = generate_flow_id()
        
        request_body = {
            "trainTaskId": self.train_task_id,
            "flowId": flow_id,
            "scriptStepStartId": start_step_id,
            "scriptStepEndId": end_step_id,
            "scriptStepStartHandle": f"{start_step_id}-source-bottom",
            "scriptStepEndHandle": f"{end_step_id}-target-top",
            "transitionPrompt": "",  # 初始为空，后续通过edit_flow设置B类卡片内容
            "transitionHistoryNum": -1,  # -1 表示全部历史记录
            "flowSettingType": "quick",
            "isDefault": 1,  # 设置为默认跳转
            "isError": False,
            "flowCondition": "1",  # 默认条件
            "flowConfiguration": {
                "relation": "and",
                "conditions": [{"text": "条件组1", "relation": "and", "conditions": [{"text": ""}]}]
            }
        }
        
        result = self._make_request("POST", self.endpoints["create_flow"], data=request_body)
        result["_flow_id"] = flow_id
        return result
    
    def edit_flow(
        self,
        flow_id: str,
        start_step_id: str,
        end_step_id: str,
        transition_prompt: str,
        flow_condition: str = "",
        is_default: bool = True
    ) -> dict:
        """
        修改连线（设置B类卡片内容和跳转条件）
        
        Args:
            flow_id: 连线ID
            start_step_id: 起始节点ID
            end_step_id: 结束节点ID
            transition_prompt: 过渡提示词（B类卡片内容）
            flow_condition: 跳转条件（如"卡片1B"，与A类卡片的跳转指令对应）
            is_default: 是否为默认跳转（单线路情况下始终为True）
            
        Returns:
            修改结果
        """
        # 跳转条件：如果设置了条件则使用，否则留空
        # 注意：isDefault=1 表示默认跳转，在单线路情况下即使有条件也需要勾选
        condition = flow_condition if flow_condition else ""
        
        request_body = {
            "trainTaskId": self.train_task_id,
            "flowId": flow_id,
            "scriptStepStartId": start_step_id,
            "scriptStepEndId": end_step_id,
            "scriptStepStartHandle": f"{start_step_id}-source-bottom",
            "scriptStepEndHandle": f"{end_step_id}-target-top",
            "transitionPrompt": transition_prompt,  # B类卡片内容在这里！
            "transitionHistoryNum": -1,  # -1 表示全部历史记录
            "flowSettingType": "quick",
            "isDefault": 1 if is_default else 0,  # 单线路情况下始终为1（勾选默认跳转）
            "isError": False,
            "flowCondition": condition,  # 跳转条件（如"卡片1B"），可以为空
            "flowConfiguration": {
                "relation": "and",
                "conditions": [{"text": "条件组1", "relation": "and", "conditions": [{"text": condition}]}]
            } if condition else {}
        }
        
        return self._make_request("POST", self.endpoints["edit_flow"], data=request_body)
    
    # ========== 任务配置与评价项 ==========
    
    def edit_configuration(
        self,
        task_name: str,
        description: str = "",
        train_time: int = -1
    ) -> dict:
        """
        更新训练任务配置
        
        Args:
            task_name: 任务名称
            description: 任务描述
            train_time: 训练时长（分钟），-1 表示不限时
            
        Returns:
            API 响应
        """
        request_body = {
            "trainTaskId": self.train_task_id,
            "trainTaskName": task_name,
            "description": description,
            "trainTime": train_time,
        }
        return self._make_request("POST", self.endpoints["edit_configuration"], data=request_body)
    
    def create_score_item(
        self,
        item_name: str,
        score: int,
        description: str = "",
        require_detail: str = ""
    ) -> dict:
        """
        创建评价项
        
        Args:
            item_name: 评价项名称
            score: 分值
            description: 评价描述
            require_detail: 详细要求
            
        Returns:
            API 响应
        """
        request_body = {
            "trainTaskId": self.train_task_id,
            "itemName": item_name,
            "score": score,
            "description": description,
            "requireDetail": require_detail,
        }
        return self._make_request("POST", self.endpoints["create_score_item"], data=request_body)
    
    # ========== 批量操作 ==========
    
    def inject_cards(
        self,
        a_cards: List[dict],
        b_cards: List[dict],
        progress_callback: Optional[callable] = None
    ) -> dict:
        """
        批量注入卡片
        
        连接结构：
        训练开始 ──(无B卡)──→ 卡片1A ──(卡片1B)──→ 卡片2A ──(卡片2B)──→ ... ──(无B卡)──→ 训练结束
        
        Args:
            a_cards: A类卡片列表
            b_cards: B类卡片列表，数量应为 len(a_cards) - 1
            progress_callback: 进度回调
            
        Returns:
            注入结果
        """
        expected_b_count = len(a_cards) - 1
        if len(b_cards) > expected_b_count:
            print(f"[提示] B类卡片数量({len(b_cards)})多于所需({expected_b_count})，多余的将被忽略")
        
        self.reset_position()
        
        step_ids = []
        flow_ids = []
        
        # 计算总步骤数：创建A卡 + 连接起始节点 + 创建连线 + 连接结束节点
        num_flows_between_cards = len(a_cards) - 1 if len(a_cards) > 1 else 0
        total_steps = len(a_cards) + 1 + num_flows_between_cards + 1  # +1起始连线 +1结束连线
        current_step = 0
        
        # ========== 阶段1: 创建所有A类卡片（节点）==========
        print("\n[阶段1] 创建A类卡片（节点）...")
        for i, card in enumerate(a_cards):
            if progress_callback:
                progress_callback(current_step, total_steps, f"创建A类卡片 {i+1}/{len(a_cards)}")
            
            try:
                result = self.create_step(
                    step_name=card.get("step_name", f"卡片{i+1}A"),
                    llm_prompt=card.get("llm_prompt", ""),
                    description=card.get("description", ""),
                    prologue=card.get("prologue", ""),
                    # 卡片配置参数（字段名已通过抓包确认）
                    interaction_rounds=card.get("interaction_rounds", 5),
                    model_id=card.get("model_id", ""),
                    history_num=card.get("history_num", 0),
                    trainer_name=card.get("trainer_name", ""),
                )
                step_id = result.get("_step_id")
                step_ids.append(step_id)
                print(f"  [OK] 创建节点 {i+1}: {step_id[:15]}... - {card.get('step_name', '')[:20]}")
            except Exception as e:
                print(f"  [失败] 创建节点 {i+1} 失败: {e}")
                step_ids.append(None)
            
            current_step += 1
            time.sleep(0.8)
        
        # ========== 阶段2: 从"训练开始"连接到第一个A类卡片 ==========
        print("\n[阶段2] 连接训练开始节点...")
        if self.start_node_id and step_ids and step_ids[0]:
            if progress_callback:
                progress_callback(current_step, total_steps, "连接训练开始节点")
            try:
                flow_result = self.create_flow(self.start_node_id, step_ids[0])
                print(f"  [OK] 训练开始 → 卡片1A")
            except Exception as e:
                print(f"  [失败] 连接训练开始节点失败: {e}")
        else:
            print(f"  [跳过] 未配置起始节点ID或第一个卡片创建失败")
        current_step += 1
        time.sleep(0.5)
        
        # ========== 阶段3: 创建A类卡片之间的连线，并设置B类卡片内容 ==========
        print("\n[阶段3] 创建卡片间连线并设置B类卡片...")
        for i in range(len(step_ids) - 1):
            start_id = step_ids[i]
            end_id = step_ids[i + 1]
            
            if not start_id or not end_id:
                print(f"  [跳过] 连线 {i+1}: 节点缺失")
                flow_ids.append(None)
                current_step += 1
                continue
            
            if progress_callback:
                progress_callback(current_step, total_steps, f"创建连线 {i+1}/{len(step_ids)-1}")
            
            try:
                # 创建连线
                flow_result = self.create_flow(start_id, end_id)
                flow_id = flow_result.get("_flow_id")
                
                # 设置B类卡片内容和跳转条件（如果有）
                if i < len(b_cards) and b_cards[i].get("transition_prompt"):
                    # 跳转条件：默认使用"卡片XB"格式，与A类卡片中的跳转指令对应
                    flow_condition = b_cards[i].get("flow_condition", f"卡片{i+1}B")
                    self.edit_flow(
                        flow_id=flow_id,
                        start_step_id=start_id,
                        end_step_id=end_id,
                        transition_prompt=b_cards[i]["transition_prompt"],
                        flow_condition=flow_condition,
                        is_default=True  # 单线路情况下始终勾选默认跳转
                    )
                    print(f"  [OK] 卡片{i+1}A → 卡片{i+2}A (含B类卡片{i+1}B, 跳转条件: {flow_condition}, 默认跳转: 是)")
                else:
                    print(f"  [OK] 卡片{i+1}A → 卡片{i+2}A (无B类卡片，默认跳转)")
                
                flow_ids.append(flow_id)
                
            except Exception as e:
                print(f"  [失败] 连线 {i+1} 失败: {e}")
                flow_ids.append(None)
            
            current_step += 1
            time.sleep(0.8)
        
        # ========== 阶段4: 从最后一个A类卡片连接到"训练结束" ==========
        print("\n[阶段4] 连接训练结束节点...")
        if self.end_node_id and step_ids and step_ids[-1]:
            if progress_callback:
                progress_callback(current_step, total_steps, "连接训练结束节点")
            try:
                flow_result = self.create_flow(step_ids[-1], self.end_node_id)
                flow_id = flow_result.get("_flow_id")
                
                # 检查是否有最后一张B类卡片需要设置
                # 最后一张B类卡片的索引 = len(a_cards) - 1
                last_b_index = len(a_cards) - 1
                if last_b_index < len(b_cards) and b_cards[last_b_index].get("transition_prompt"):
                    flow_condition = b_cards[last_b_index].get("flow_condition", f"卡片{len(a_cards)}B")
                    self.edit_flow(
                        flow_id=flow_id,
                        start_step_id=step_ids[-1],
                        end_step_id=self.end_node_id,
                        transition_prompt=b_cards[last_b_index]["transition_prompt"],
                        flow_condition=flow_condition,
                        is_default=True  # 单线路情况下始终勾选默认跳转
                    )
                    print(f"  [OK] 卡片{len(step_ids)}A → 训练结束 (含B类卡片{len(a_cards)}B, 跳转条件: {flow_condition}, 默认跳转: 是)")
                else:
                    print(f"  [OK] 卡片{len(step_ids)}A → 训练结束 (无B类卡片)")
            except Exception as e:
                print(f"  [失败] 连接训练结束节点失败: {e}")
        else:
            print(f"  [跳过] 未配置结束节点ID或最后一个卡片创建失败")
        current_step += 1
        
        if progress_callback:
            progress_callback(total_steps, total_steps, "完成")
        
        # 统计结果
        successful_steps = sum(1 for s in step_ids if s)
        successful_flows = sum(1 for f in flow_ids if f)
        
        return {
            "step_ids": step_ids,
            "flow_ids": flow_ids,
            "stats": {
                "total_a_cards": len(a_cards),
                "successful_a_cards": successful_steps,
                "total_b_cards": min(len(b_cards), expected_b_count),  # 实际使用的B卡数量
                "successful_b_cards": successful_flows,
            }
        }
