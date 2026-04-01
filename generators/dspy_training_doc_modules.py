"""
能力训练文档：DSPy 模块。
"""

import dspy

from .dspy_training_doc_signatures import TrainingDocSignature


class TrainingDocGeneratorModule(dspy.Module):
    """单次调用生成完整 Markdown 能力训练文档。"""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(TrainingDocSignature)

    def forward(
        self,
        course_name: str,
        training_theme: str,
        source_material: str,
        image_context: str = "",
    ) -> dspy.Prediction:
        return self.generate(
            course_name=course_name,
            training_theme=training_theme,
            source_material=source_material,
            image_context=image_context or "（暂无）",
        )
