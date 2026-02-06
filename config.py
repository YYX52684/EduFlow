"""
配置文件 - 管理API密钥和全局设置
"""
import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# DeepSeek API配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 模拟器/评估器默认使用 DeepSeek（与卡片生成一致）；可通过 SIMULATOR_* / EVALUATOR_* / NPC_* 覆盖
def _deepseek_chat_url():
    base = DEEPSEEK_BASE_URL.rstrip("/")
    return f"{base}/v1/chat/completions"
DEEPSEEK_CHAT_URL = os.getenv("DEEPSEEK_CHAT_URL", _deepseek_chat_url())

# 文件路径配置
INPUT_DIR = os.path.join(os.path.dirname(__file__), "input")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# 确保目录存在
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# API调用参数
MAX_TOKENS = 4096
TEMPERATURE = 0.7

# 智慧树平台配置
PLATFORM_CONFIG = {
    # API基础URL（注意：实际API在cloudapi子域名）
    "base_url": os.getenv("PLATFORM_BASE_URL", "https://cloudapi.polymas.com"),
    # 认证Cookie
    "cookie": os.getenv("PLATFORM_COOKIE", ""),
    # Authorization JWT Token
    "authorization": os.getenv("PLATFORM_AUTHORIZATION", ""),
    # 课程ID
    "course_id": os.getenv("PLATFORM_COURSE_ID", ""),
    # 训练任务ID
    "train_task_id": os.getenv("PLATFORM_TRAIN_TASK_ID", ""),
    # 起始节点ID（训练开始）
    "start_node_id": os.getenv("PLATFORM_START_NODE_ID", ""),
    # 结束节点ID（训练结束）
    "end_node_id": os.getenv("PLATFORM_END_NODE_ID", ""),
}

# 平台API端点配置
PLATFORM_ENDPOINTS = {
    "create_step": "/teacher-course/abilityTrain/createScriptStep",
    "edit_step": "/teacher-course/abilityTrain/editScriptStep",
    "create_flow": "/teacher-course/abilityTrain/createScriptStepFlow",
    "edit_flow": "/teacher-course/abilityTrain/editScriptStepFlow",
    "edit_configuration": "/teacher-course/abilityTrain/editConfiguration",
    "create_score_item": "/teacher-course/abilityTrain/createScoreItem",
    # 查询现有脚本节点/连线，用于注入前检测。若平台接口不同，可在 .env / 工作区配置中覆盖。
    "list_steps": "/teacher-course/abilityTrain/getScriptStepList",
}

# 卡片默认配置（字段名已通过抓包确认）
# 这些配置项用于创建卡片节点时的默认值
CARD_DEFAULTS = {
    # AI模型ID (modelId)
    "model_id": os.getenv("CARD_MODEL_ID", ""),
    # 历史记录数量 (historyRecordNum)：0=不保留，-1=全部
    "history_num": int(os.getenv("CARD_HISTORY_NUM", "0")),
    # 虚拟训练官名字 (trainerName)
    "trainer_name": os.getenv("CARD_TRAINER_NAME", ""),
    # 默认交互轮次 (interactiveRounds)，如果LLM未指定
    "default_interaction_rounds": int(os.getenv("CARD_DEFAULT_INTERACTION_ROUNDS", "5")),
}

# 卡片生成器配置
# 可选值: "default" (传统方式), "dspy" (DSPy结构化生成)
CARD_GENERATOR_TYPE = os.getenv("CARD_GENERATOR_TYPE", "default")

# 评价项配置（注入时使用）
EVALUATION_CONFIG = {
    "enabled": os.getenv("ENABLE_EVALUATION", "true").lower() in ("true", "1", "yes"),
    "auto_generate": os.getenv("AUTO_GENERATE_EVALUATION", "true").lower() in ("true", "1", "yes"),
    "target_total_score": int(os.getenv("EVALUATION_TARGET_SCORE", "100")),
}

# 豆包API配置（公司内网）
DOUBAO_API_KEY = os.getenv("LLM_API_KEY")
DOUBAO_BASE_URL = "http://llm-service.polymas.com/api/openai/v1"
DOUBAO_MODEL = os.getenv("LLM_MODEL", "Doubao-1.5-pro-32k")
DOUBAO_SERVICE_CODE = os.getenv("LLM_SERVICE_CODE", "SI_Ability")

# 模型选择配置
# 可选值: "deepseek" (DeepSeek API), "doubao" (豆包API)
DEFAULT_MODEL_TYPE = os.getenv("MODEL_TYPE", "deepseek")

# DSPy 优化 + 外部评估指标配置
OPTIMIZER_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "optimizer")
os.makedirs(OPTIMIZER_OUTPUT_DIR, exist_ok=True)

DSPY_OPTIMIZER_CONFIG = {
    # 导出文件路径（外部平台评估结果）
    "export_file_path": os.getenv("DSPY_EXPORT_FILE", os.path.join(OPTIMIZER_OUTPUT_DIR, "export_score.json")),
    # 解析器: json | csv | custom
    "parser": os.getenv("DSPY_EXPORT_PARSER", "json"),
    # JSON 分数字段名
    "json_score_key": os.getenv("DSPY_JSON_SCORE_KEY", "total_score"),
    # CSV 分数列名（可选）
    "csv_score_column": os.getenv("DSPY_CSV_SCORE_COLUMN") or None,
    # 生成卡片输出路径（每轮优化写入）
    "cards_output_path": os.getenv("DSPY_CARDS_OUTPUT", os.path.join(OPTIMIZER_OUTPUT_DIR, "cards_for_eval.md")),
    # 优化器类型: bootstrap | mipro
    "optimizer_type": os.getenv("DSPY_OPTIMIZER", "bootstrap"),
    "max_rounds": int(os.getenv("DSPY_MAX_ROUNDS", "1")),
    "max_bootstrapped_demos": int(os.getenv("DSPY_MAX_BOOTSTRAPPED_DEMOS", "4")),
}
