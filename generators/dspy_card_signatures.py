"""
DSPy 卡片生成签名定义。

设计目标：
1. InputField 尽量只承载阶段事实与上下文，不混入展示层拼接逻辑。
2. OutputField 与最终卡片 section 一一对应，便于单独调优。
3. 共用提示片段抽成常量，避免 A/B/结尾卡合同漂移。
"""

import dspy


def _join_desc(*parts: str) -> str:
    return "".join(part for part in parts if part)


def _section_desc(title: str, *parts: str) -> str:
    return _join_desc(f"# {title} 部分：", *parts)


_COMMON_FULL_SCRIPT_DESC = "完整的原始剧本内容，用于理解整体剧情与学习目标。"

_A_ROLE_REFERENCE = "用「你」指代 NPC，例如「你是张经理，食品厂设备采购经理……」。"
_A_DIALOGUE_REFERENCE = "用「你」指 NPC、「学生/对方」指学生。"
_A_NO_ACTION_RULE = "只写NPC要说的内容，不要写动作、神态描写或元叙述。"
_A_NO_MECHANICAL_RULE = "严禁机械连接词如「你提到」「第一...第二...」等。"
_A_TRANSITION_NO_CARD_ID_RULE = "不要直接输出卡片编号，卡片跳转由展示层处理。"
_A_INTERACTION_DENSITY_RULE = "内部生成时必须保持高信息密度：至少覆盖3个来自 `key_points` 或 `content_excerpt` 的具体锚点（术语、事实、细节、原话片段均可），避免泛泛鼓励。"
_A_STAGE_TITLE_DESC = "场景标题。"
_A_NPC_ROLE_DESC = "NPC角色描述。"
_A_SCENE_GOAL_DESC = "场景目标/任务。"
_A_KEY_POINTS_DESC = "关键剧情点，用逗号分隔。用于约束本幕必须覆盖的关键信息，不要只做笼统概括。"
_A_CONTENT_EXCERPT_DESC = "本幕对应的原文关键内容或对话摘要，是必须重点覆盖的参考段落。生成各部分时，应优先从此处提取具体事实、数据、术语和对话片段，而不是只做抽象总结。"
_A_ROLE_SECTION_DESC = _section_desc(
    "Role",
    "NPC是谁，背景、性格、说话方式。建议80-140字。",
    _A_ROLE_REFERENCE,
    "需要结合本幕 `content_excerpt` 与 `key_points` 中的关键信息，至少落地2个具体事实（人物经历/事件/术语/数据/关系），避免抽象空话。",
)
_A_CONTEXT_SECTION_DESC = _section_desc(
    "Context",
    "当前场景背景，对方（学生）扮演什么角色。建议90-160字。",
    _A_DIALOGUE_REFERENCE,
    "须嵌入本幕原文中的关键信息点（如角色关系、场景前提、重要道具/数据），至少覆盖2个原文锚点，而不是只写「你和学生正在交流」这类空泛语句。",
    "若本环节紧接在角色切换之后，开场第一句须含简短情境承接（如时间、场景或身份，例如「好的，我们到病房了」「术后第二天了」「护士，我们明天要出院了」），再进入本角色第一句台词，避免学生感到突兀。",
)
_A_OPTIONS_SECTION_DESC = _section_desc(
    "Options（可选）",
    "仅当涉及英文/代码/长串需语音输入时提供。",
    "列出 3-5 个编号选项，中文描述清晰，包含正确/常见误区/部分正确。",
    "若无需选项则返回空字符串。",
    "避免让学生朗读英文或代码，提示其说编号或简短中文。",
)
_A_QA_INTERACTION_PATTERN = "围绕当前任务先抛出1-2个关键问题，再根据学生回答点评、追问或纠偏。"
_A_QA_TRANSITION_RULE = "更看重学生是否完成回答、说清原因/依据/方案，而不是只给出含糊态度。"
_A_GUIDANCE_INTERACTION_PATTERN = "先讲清1-2个步骤、原理或风险点，再请学生用一句话复述、确认或补关键项。"
_A_GUIDANCE_NO_QUIZ_STYLE = "不要一上来连续发问，也不要把整段操作说明改写成考试式盘问。"
_A_GUIDANCE_TRANSITION_RULE = "更看重学生能否复述关键顺序、禁忌、依据或风险点；如果复述不全，可继续讲解补充或要求再确认。"
_A_MULTI_ROUND_BASE_RULE = "Interaction 必须是可执行的多轮博弈逻辑，不是单轮台词：至少给出阶段状态、触发条件、每轮动作与升级/降级规则。"
_A_PROGRESSIVE_DISCLOSURE_RULE = "采用递进披露（surface -> emotional/technical -> core）：用户未触发高质量行为前，严禁提前吐露核心诉求或完整答案。"
_A_HOOK_RULE = "每轮末尾都要留一个可被追问的钩子句，禁止使用空泛句式如「你还有什么想问的吗」。"
_A_STATE_MACHINE_OUTPUT_RULE = "输出格式建议使用短标题+要点（如状态定义、反馈矩阵、阶段推进、钩子策略），确保运行时可读可执行。"
_A_QA_STATE_RULE = "问答考核型状态机：审慎模式（初始）->追证模式->达标模式；依据学生回答质量在状态间切换。"
_A_QA_MATRIX_RULE = "反馈矩阵：封闭提问仅短答不扩展；口号式回答要求补依据；开放提问增量披露；澄清总结可升级信任并进入收敛。"
_A_QA_PHASE_RULE = "阶段推进：A试探/B深挖/C收敛；仅在C阶段且学生展示可执行方案与依据时，才允许触发转折。"
_A_GUIDANCE_STATE_RULE = "指导讲解型状态机：冷淡模式（防御）/观察模式（初始）/知音模式（信任）。"
_A_GUIDANCE_MATRIX_RULE = "反馈矩阵：说教与评判触发防御收敛；开放提问与同理回应触发增量披露；精准总结后才可进入核心议题。"
_A_GUIDANCE_PHASE_RULE = "阶段推进：试探期/磨合期/决策期；只有在决策期形成初步共识后，才允许触发转折。"
_A_NO_HINT_TONE_RULE = "禁止使用教学提示腔与引导词，如「提示：」「例如：」「你提到的…」。"
_A_NO_BRACKET_EXPLAIN_RULE = "禁止使用任何括号补充说明（含中文/英文括号）；解释信息必须改写为自然主句。"
_A_SHORT_FEEDBACK_RULE = "正向反馈必须短句化（不超过20字），且只允许一句，随后立即进入任务推进。"
_A_DIRECT_PUSH_RULE = "优先使用「结论+追问」句式，避免先长段复述学生回答再评价。"
_A_LENGTH_RULE = "运行时单次口播输出建议控制在150-200词，硬上限不超过250词；不足则简洁回答，禁止为凑字数重复同义句。"
_A_NO_MICRO_LOOP_RULE = "禁止围绕同一小知识点连续多轮打转：同一细节点最多追问2轮，仍未达标则先做阶段性收束并切换到本幕下一个关键要点。"
_A_TOPIC_BUDGET_RULE = "采用“要点预算”推进：每轮只处理一个要点，但连续两轮未产生新增信息时必须换点，避免局部循环僵局。"

_B_RESPONSE_FIRST_RULE = "B卡运行时会获得 `${previous_dialogue}`，其中包含上一张A卡的对话记录。你必须先把前文收束到当前情景中的一个具体落点（如关键术语、错误点、已完成动作或待补步骤），再自然带出下一话题。"
_B_ANCHOR_RULE = "回应时尽量引用 `current_stage_key_points` 或 `current_stage_excerpt` 中的具体术语、事实或错误点，避免泛泛评价。"
_B_NO_FLOW_TERMS_RULE = "严禁使用「本环节」「本阶段」「现在请进入下一阶段」等流程用语。"
_B_NO_THIRD_PERSON_RULE = "不要写长段第三人称场景描写。"
_B_NO_STATIC_EVAL_TEMPLATE_RULE = "禁止使用静态评语模板（如「你有一定阐述/还可以更深入/就像我们讨论的」）；回应必须贴合上一轮学生具体内容。"
_B_MUST_REFERENCE_LAST_TURN_RULE = "必须点名上一轮学生回答中的至少1个具体点（术语、参数、结论或错误），再给确认或纠偏。"
_B_DYNAMIC_ADVANCE_RULE = "确认/纠偏后立刻提出下一步具体任务，不要写空泛过渡句。"
_B_OUTPUT_SCHEMA_RULE = "Output 固定采用「锚定 -> 回应 -> 推进」骨架：先锚定上一轮具体信息，再一句确认/纠偏，最后给出可执行下一步任务。"
_B_HISTORY_PRIORITY_RULE = "信号优先级必须为：P0=`${previous_dialogue}` 最近1-2轮，P1=`current_stage_key_points/current_stage_excerpt` 仅补漏，P2=阶段标题与任务仅定方向。"
_B_NO_OMNISCIENT_RULE = "禁止上帝视角总结前一A卡设计目标；若未引用最近轮次真实表达则视为不合格。"
_B_DYNAMIC_BRANCH_RULE = "必须包含动态分支：学生答到关键点时短肯定并推进；学生答偏/泛化时先纠偏再推进。不得写成固定单一路径模板。"
_B_BRIDGE_QUESTION_RULE = "推进环节必须抛出具体落地问题，优先询问“改造后先变化的运行参数+对应监控指标”。"
_B_LENGTH_RULE = "运行时最终口播输出建议控制在50-120词，硬上限不超过150词；在信息不足时优先简洁，不要为凑字数而重复。"

_ENDING_NO_FLOW_TERMS_RULE = "不要使用「本环节」「本阶段」「现在结束训练」等流程化说法。"
_ENDING_NO_NEW_TASK_RULE = "不要再提出新问题或开启新的任务。"
_ENDING_NO_BRACKET_RULE = "不要使用括号，不要解释系统行为。"


class CardASignature(dspy.Signature):
    """生成A类卡片（问答/考核型 NPC 角色卡片）的签名

    A类卡片是沉浸式角色扮演的核心。
    当前签名更偏向提问、追问、诊断、考核、评价型阶段。
    """

    full_script: str = dspy.InputField(desc=_COMMON_FULL_SCRIPT_DESC)
    stage_title: str = dspy.InputField(desc=_A_STAGE_TITLE_DESC)
    npc_role: str = dspy.InputField(desc=_A_NPC_ROLE_DESC)
    scene_goal: str = dspy.InputField(desc=_A_SCENE_GOAL_DESC)
    key_points: str = dspy.InputField(desc=_A_KEY_POINTS_DESC)
    content_excerpt: str = dspy.InputField(desc=_A_CONTENT_EXCERPT_DESC)

    role_section: str = dspy.OutputField(desc=_A_ROLE_SECTION_DESC)
    context_section: str = dspy.OutputField(desc=_A_CONTEXT_SECTION_DESC)
    interaction_section: str = dspy.OutputField(
        desc=_section_desc(
            "Interaction",
            "写出 NPC 在本幕中的多轮互动逻辑。建议220-420字。",
            _A_DIALOGUE_REFERENCE,
            _A_QA_INTERACTION_PATTERN,
            _A_MULTI_ROUND_BASE_RULE,
            _A_PROGRESSIVE_DISCLOSURE_RULE,
            _A_QA_STATE_RULE,
            _A_QA_MATRIX_RULE,
            _A_QA_PHASE_RULE,
            _A_HOOK_RULE,
            _A_STATE_MACHINE_OUTPUT_RULE,
            _A_NO_HINT_TONE_RULE,
            _A_NO_BRACKET_EXPLAIN_RULE,
            _A_SHORT_FEEDBACK_RULE,
            _A_DIRECT_PUSH_RULE,
            _A_LENGTH_RULE,
            _A_NO_MICRO_LOOP_RULE,
            _A_TOPIC_BUDGET_RULE,
            _A_INTERACTION_DENSITY_RULE,
            _A_NO_ACTION_RULE,
            "每轮通常推进1-2个问题或推进点，不要连续追问。",
            _A_NO_MECHANICAL_RULE,
            "学生答对时可给予具体正向反馈。",
            "严禁括号内暴露思考、元叙述。禁止在未达标时提前给出转折标记。",
        )
    )
    transition_section: str = dspy.OutputField(
        desc=_section_desc(
            "Transition",
            "什么情况下视为情景进展到转折点。",
            _A_DIALOGUE_REFERENCE,
            "必须基于本幕关键知识点和任务目标来判断是否达标：明确写出学生需要展示哪些要点（可引用 `key_points` 或 `content_excerpt` 中的关键信息）才算完成本环节。",
            "请列出2-4个可观察的达标条件；达标时用「视为情景进展到转折点」表述；未达标时写明可继续追问/引导。",
            _A_QA_TRANSITION_RULE,
            "优先使用行为与任务语言（如“完成自我介绍”“准确复述风险点”“提出可执行方案”），尽量避免情绪化词汇或情绪转折句式。建议80-140字。",
            _A_TRANSITION_NO_CARD_ID_RULE,
        )
    )
    constraints_section: str = dspy.OutputField(
        desc=_section_desc(
            "Constraints",
            "只列出当前场景真正需要的2-4条运行时约束，使用短横线列表格式。",
            "只写 NPC 扮演时需要遵守的规则，不要重复生成方法，不要写“信息密度”“覆盖锚点”“key_points/content_excerpt”“编号选项”等提示词设计要求。",
            "优先保留问答/考核型约束，例如提问节奏、追问时机、答偏时只纠正关键点、是否需要学生说清依据。",
            "若本幕并不需要追问/追深，不要为了凑规则强行写“答对后继续追问”。",
            "涉及英文/代码/长串时，用 `Options` 处理，不要把“提供编号选项”写进 Constraints。",
        )
    )
    options_section: str = dspy.OutputField(desc=_A_OPTIONS_SECTION_DESC)


class CardAGuidanceSignature(dspy.Signature):
    """生成A类卡片（指导讲解型 NPC 角色卡片）的签名

    适用于讲解步骤、原理、风险、禁忌并要求学生简短复述或确认的阶段。
    """

    full_script: str = dspy.InputField(desc=_COMMON_FULL_SCRIPT_DESC)
    stage_title: str = dspy.InputField(desc=_A_STAGE_TITLE_DESC)
    npc_role: str = dspy.InputField(desc=_A_NPC_ROLE_DESC)
    scene_goal: str = dspy.InputField(desc=_A_SCENE_GOAL_DESC)
    key_points: str = dspy.InputField(desc=_A_KEY_POINTS_DESC)
    content_excerpt: str = dspy.InputField(desc=_A_CONTENT_EXCERPT_DESC)

    role_section: str = dspy.OutputField(desc=_A_ROLE_SECTION_DESC)
    context_section: str = dspy.OutputField(desc=_A_CONTEXT_SECTION_DESC)
    interaction_section: str = dspy.OutputField(
        desc=_section_desc(
            "Interaction",
            "写出 NPC 在本幕中的多轮指导互动逻辑。建议220-420字。",
            _A_DIALOGUE_REFERENCE,
            _A_GUIDANCE_INTERACTION_PATTERN,
            _A_MULTI_ROUND_BASE_RULE,
            _A_PROGRESSIVE_DISCLOSURE_RULE,
            _A_GUIDANCE_STATE_RULE,
            _A_GUIDANCE_MATRIX_RULE,
            _A_GUIDANCE_PHASE_RULE,
            _A_HOOK_RULE,
            _A_STATE_MACHINE_OUTPUT_RULE,
            _A_NO_HINT_TONE_RULE,
            _A_NO_BRACKET_EXPLAIN_RULE,
            _A_SHORT_FEEDBACK_RULE,
            _A_DIRECT_PUSH_RULE,
            _A_LENGTH_RULE,
            _A_NO_MICRO_LOOP_RULE,
            _A_TOPIC_BUDGET_RULE,
            _A_INTERACTION_DENSITY_RULE,
            _A_NO_ACTION_RULE,
            _A_GUIDANCE_NO_QUIZ_STYLE,
            "讲解与确认比例大约 7:3；学生复述基本正确时，可给一句简短确认或补关键提醒。",
            _A_NO_MECHANICAL_RULE,
            "严禁括号内暴露思考、元叙述。禁止在未达标时提前给出转折标记。",
        )
    )
    transition_section: str = dspy.OutputField(
        desc=_section_desc(
            "Transition",
            "什么情况下视为情景进展到转折点。",
            _A_DIALOGUE_REFERENCE,
            "必须基于本幕关键知识点和任务目标来判断是否达标：明确写出学生需要展示哪些要点（可引用 `key_points` 或 `content_excerpt` 中的关键信息）才算完成本环节。",
            "请列出2-4个可观察的达标条件；达标时用「视为情景进展到转折点」表述；未达标时写明可继续讲解、补充说明或要求学生再确认。",
            _A_GUIDANCE_TRANSITION_RULE,
            "优先使用行为与任务语言（如“按顺序复述步骤”“指出禁忌项”“说明风险点”），尽量避免情绪化词汇或情绪转折句式。建议80-140字。",
            _A_TRANSITION_NO_CARD_ID_RULE,
        )
    )
    constraints_section: str = dspy.OutputField(
        desc=_section_desc(
            "Constraints",
            "只列出当前场景真正需要的2-4条运行时约束，使用短横线列表格式。",
            "只写 NPC 扮演时需要遵守的规则，不要重复生成方法，不要写“信息密度”“覆盖锚点”“key_points/content_excerpt”“编号选项”等提示词设计要求。",
            "优先保留指导讲解型约束，例如先讲解再确认、一次只推进1-2个步骤/原理、学生复述偏差时只纠正关键点、保持自然口语。",
            "不要为了凑规则把整段讲解改写成考试式盘问。",
            "涉及英文/代码/长串时，用 `Options` 处理，不要把“提供编号选项”写进 Constraints。",
        )
    )
    options_section: str = dspy.OutputField(desc=_A_OPTIONS_SECTION_DESC)


class CardAPrologueSignature(dspy.Signature):
    """生成A类卡片开场白（仅用于第一张卡片）"""

    full_script: str = dspy.InputField(desc=_COMMON_FULL_SCRIPT_DESC)
    npc_role: str = dspy.InputField(desc="NPC角色描述。")
    scene_goal: str = dspy.InputField(desc="场景目标/任务。")

    prologue: str = dspy.OutputField(
        desc="开场白：NPC角色的自我介绍或场景引入，建议50-80字，用于在交互开始前展示给学生。围绕身份与当前任务自然起场，不使用任何括号。"
    )


class CardAEndingSignature(dspy.Signature):
    """生成结尾用A类卡片（轮次为0，仅收尾用）"""

    full_script: str = dspy.InputField(desc=_COMMON_FULL_SCRIPT_DESC)
    last_stage_title: str = dspy.InputField(desc="最后一幕的场景标题或小结标题。")
    last_stage_role: str = dspy.InputField(desc="最后一幕的NPC角色描述（例如：主治医师、患者、带教老师、学生等）。")
    last_stage_goal: str = dspy.InputField(desc="最后一幕的场景目标或任务描述。")
    last_stage_key_points: str = dspy.InputField(desc="最后一幕的关键剧情点或知识点摘要。")
    last_stage_excerpt: str = dspy.InputField(desc="最后一幕对应的原文关键内容或对话摘要。")

    role_section: str = dspy.OutputField(
        desc=_section_desc(
            "Role",
            "说明你要继续沉浸在最后一幕的NPC身份中，用与剧本一致的说话方式做本次对话的收尾。",
            "不要重新发明新身份，只需用一句话提醒自己「你是谁」。",
        )
    )
    context_section: str = dspy.OutputField(
        desc=_section_desc(
            "Context",
            "说明这是本次实训/剧情中的最后一轮交流。",
            "基于 `last_stage_title`、`last_stage_goal` 和 `last_stage_excerpt`，用自然语言概括现在所处的情境。",
            _ENDING_NO_FLOW_TERMS_RULE,
            "如果在剧本中你是医生/患者/老师/学生等，应根据剧本里的身份自然选择合适的收尾方向（如医生嘱托、患者致谢、老师鼓励、学生感谢），但不要生硬罗列这些身份。",
        )
    )
    interaction_section: str = dspy.OutputField(
        desc=_section_desc(
            "Interaction",
            "写出 NPC 在最后一轮中要说的一整段收尾台词。",
            "可以包含1-2句对刚才表现、病情或学习收获的简要评价或回应，再加1-2句感谢、嘱托或鼓励，最后用一句自然的告别语结束。",
            "整段发言控制在150字以内，语气真诚自然。",
            _ENDING_NO_NEW_TASK_RULE,
            _ENDING_NO_BRACKET_RULE,
        )
    )
    transition_section: str = dspy.OutputField(
        desc=_section_desc(
            "Transition",
            "用自然语言说明「说完这段话后，本次实训/剧情就此结束」。",
            "禁止写任何卡片编号或技术性跳转指令，只用角色视角表达结束。",
            _ENDING_NO_FLOW_TERMS_RULE,
        )
    )
    constraints_section: str = dspy.OutputField(
        desc=_section_desc(
            "Constraints",
            "列出这张结尾卡的运行限制。",
            "可包含：轮次为0，只说这一轮就结束；不再提出新问题或任务；避免流程化用语和卡片编号；严禁括号和元叙述；整体长度建议150字以内。",
        )
    )


class CardBSignature(dspy.Signature):
    """生成B类卡片（场景过渡卡片）的签名 - 用于同一角色的场景间过渡

    过渡语的核心任务是先接住上一张A卡最后一轮学生回答，再自然开启下一环节。
    卡片跳转由编排层决定，不在本 signature 中生成。
    """

    current_stage_title: str = dspy.InputField(desc="当前阶段标题，用于在过渡语中自然带出刚讨论完的内容（勿用「本环节」等流程词）。")
    current_stage_goal: str = dspy.InputField(desc="当前阶段目标，应与该阶段的 `key_points` 和任务描述对应，过渡语需要根据是否达成这些目标来选择不同表述。")
    current_stage_key_points: str = dspy.InputField(desc="当前阶段关键要点，用逗号分隔。B卡回应时应优先围绕这些要点判断学生最后一轮回答哪里答到了、哪里遗漏或答偏。")
    current_stage_excerpt: str = dspy.InputField(desc="当前阶段原文摘录或关键内容。用于在回应里引用更具体的术语、事实或错误点，避免泛泛而谈。")
    next_stage_title: str = dspy.InputField(desc="下一阶段标题（如果有），用于自然带出下一话题；不要机械复述标题。")

    context_section: str = dspy.OutputField(
        desc=_section_desc(
            "Context",
            "说明过渡语使用原则。",
            _B_RESPONSE_FIRST_RULE,
            "不要脱离最后一轮直接做整段总评。1-2句话。",
        )
    )
    output_section: str = dspy.OutputField(
        desc=_section_desc(
            "Response Logic",
            "给运行时 Agent 使用的响应逻辑，不是固定台词。必须基于 `${previous_dialogue}` 动态生成过渡话。",
            _B_OUTPUT_SCHEMA_RULE,
            _B_HISTORY_PRIORITY_RULE,
            _B_DYNAMIC_BRANCH_RULE,
            _B_ANCHOR_RULE,
            "至少包含1个具体锚点（例如关键术语、错误点、情境事实），避免空泛赞扬。",
            _B_MUST_REFERENCE_LAST_TURN_RULE,
            _B_NO_STATIC_EVAL_TEMPLATE_RULE,
            _B_NO_OMNISCIENT_RULE,
            _B_DYNAMIC_ADVANCE_RULE,
            _B_BRIDGE_QUESTION_RULE,
            _B_LENGTH_RULE,
            "优先使用行为达成/事实纠偏语言，尽量避免情绪化词汇和“情绪转折”表达。",
            _B_NO_FLOW_TERMS_RULE,
            _B_NO_THIRD_PERSON_RULE,
        )
    )


class CardBNarratorSignature(dspy.Signature):
    """生成B类卡片（旁白过渡卡片）的签名 - 用于不同角色之间的切换

    旁白版的核心任务仍然是先接住上一轮学生回答，再自然完成角色切换。
    卡片跳转由编排层决定，不在本 signature 中生成。
    """

    current_stage_title: str = dspy.InputField(desc="当前阶段标题。")
    current_stage_goal: str = dspy.InputField(desc="当前阶段目标。")
    current_stage_key_points: str = dspy.InputField(desc="当前阶段关键要点，用逗号分隔。B卡回应时应优先围绕这些要点判断学生最后一轮回答哪里答到了、哪里遗漏或答偏。")
    current_stage_excerpt: str = dspy.InputField(desc="当前阶段原文摘录或关键内容。用于在回应里引用更具体的术语、事实或错误点，避免泛泛而谈。")
    current_stage_role: str = dspy.InputField(desc="当前阶段NPC角色。")
    next_stage_title: str = dspy.InputField(desc="下一阶段标题（如果有）。")
    next_stage_role: str = dspy.InputField(desc="下一阶段NPC角色（如果有）。")

    role_section: str = dspy.OutputField(
        desc=_section_desc(
            "Role",
            "旁白/叙述者的定位，1句话。",
            "只说明旁白身份，不要展开成长段叙事。",
        )
    )
    context_section: str = dspy.OutputField(
        desc=_section_desc(
            "Context",
            "说明过渡语使用原则。",
            _B_RESPONSE_FIRST_RULE,
            "在回应后，再自然衔接角色切换或下一角色。不要「无论您是否……」类无条件推进，也不要脱离最后一轮直接做整段总评。1-2句话。",
        )
    )
    output_section: str = dspy.OutputField(
        desc=_section_desc(
            "Response Logic",
            "给运行时 Agent 使用的响应逻辑，不是固定台词。必须先回应上一张A卡最后一轮学生回答，再自然引出下一角色或下一阶段。",
            _B_OUTPUT_SCHEMA_RULE,
            _B_HISTORY_PRIORITY_RULE,
            _B_DYNAMIC_BRANCH_RULE,
            _B_ANCHOR_RULE,
            "至少包含1个具体锚点（关键术语、错误点、情境事实）。",
            _B_MUST_REFERENCE_LAST_TURN_RULE,
            _B_NO_STATIC_EVAL_TEMPLATE_RULE,
            _B_NO_OMNISCIENT_RULE,
            _B_DYNAMIC_ADVANCE_RULE,
            _B_BRIDGE_QUESTION_RULE,
            _B_LENGTH_RULE,
            "优先使用行为达成/事实纠偏语言，尽量避免情绪化词汇和“情绪转折”表达。",
            _B_NO_FLOW_TERMS_RULE,
            "少用长段第三人称旁白，不使用括号。",
        )
    )
