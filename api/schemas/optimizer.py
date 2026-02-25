from typing import Optional

from pydantic import BaseModel


class OptimizeRequest(BaseModel):
    """DSPy 优化请求体 schema。

    注意：字段名与现有前端/CLI 约定保持一致，避免破坏兼容性。
    """

    trainset_path: str = "output/optimizer/trainset.json"
    devset_path: Optional[str] = None
    cards_output_path: Optional[str] = None  # 默认 output/optimizer/cards_for_eval.md
    export_path: Optional[str] = None  # 默认 output/optimizer/export_score.json
    optimizer_type: str = "bootstrap"  # bootstrap | mipro
    model_type: Optional[str] = None  # doubao | deepseek，默认与 DEFAULT_MODEL_TYPE 一致
    max_rounds: Optional[int] = None
    use_auto_eval: bool = True  # 闭环模式（默认）：仿真+评估替代外部评估
    persona_id: str = "excellent"  # 闭环模式下的学生人设

