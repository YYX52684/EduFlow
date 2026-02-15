from simulator.platform_client import PlatformTrainConfig, PlatformTrainClient

cfg = PlatformTrainConfig.from_env()
client = PlatformTrainClient(cfg)

# 1. 先模拟点一次「测试」
resp1 = client.run_card(step_id="EnqlsF3jGrax0g8Za4Vsf")
print("runCard resp:", resp1)
print("sessionId:", client.session_id)

# 2. 再发一条学生消息
resp2 = client.chat(
    step_id="EnqlsF3jGrax0g8Za4Vsf",
    text="你好，我想了解一下本次训练的要求。"
)
print("chat resp raw:", resp2)
print("NPC reply:", PlatformTrainClient.extract_npc_reply(resp2))
print("sessionId now:", client.session_id)