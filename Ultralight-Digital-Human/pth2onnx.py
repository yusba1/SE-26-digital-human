from unet import Model
import onnx
import torch
import onnxruntime
import numpy as np
import time

# ============================================================
# 可调整参数配置
# ============================================================

# PyTorch 模型路径
PTH_PATH = "./checkpoints/Veo2/final.pth"

# 输出 ONNX 模型路径
ONNX_PATH = "./checkpoints/Veo2/Veo2_wenet.onnx"

# ASR 模式: "wenet" 或 "hubert"
ASR_MODE = "wenet"

# ============================================================

def check_onnx(torch_out, torch_in, audio, onnx_path):
    onnx_model = onnx.load(onnx_path)
    onnx.checker.check_model(onnx_model)
    providers = ["CUDAExecutionProvider"]
    ort_session = onnxruntime.InferenceSession(onnx_path, providers=providers)
    print(f"ONNX Providers: {ort_session.get_providers()}")
    ort_inputs = {
        ort_session.get_inputs()[0].name: torch_in.cpu().numpy(), 
        ort_session.get_inputs()[1].name: audio.cpu().numpy()
    }
    for i in range(1):
        t1 = time.time()
        ort_outs = ort_session.run(None, ort_inputs)
        t2 = time.time()
        print(f"ONNX 推理耗时: {t2 - t1:.4f}s")

    np.testing.assert_allclose(torch_out[0].cpu().numpy(), ort_outs[0][0], rtol=1e-03, atol=1e-05)
    print("模型已通过 ONNXRuntime 验证，转换成功！")

# 根据 ASR 模式设置音频特征维度
# wenet: [128, 16, 32], hubert: [16, 32, 32]
if ASR_MODE == "wenet":
    audio_dim = 128  # wenet 特征维度
else:
    audio_dim = 16   # hubert 特征维度

print(f"加载模型: {PTH_PATH}")
print(f"ASR 模式: {ASR_MODE}")

net = Model(6, ASR_MODE).eval()
net.load_state_dict(torch.load(PTH_PATH, map_location='cpu'))
img = torch.zeros([1, 6, 160, 160])
audio = torch.zeros([1, audio_dim, 16, 32])

input_dict = {"input": img, "audio": audio}

with torch.no_grad():
    torch_out = net(img, audio)
    print(f"输出形状: {torch_out.shape}")
    print(f"正在导出 ONNX 模型到: {ONNX_PATH}")
    torch.onnx.export(
        net, 
        (img, audio), 
        ONNX_PATH, 
        input_names=['input', "audio"],
        output_names=['output'], 
        opset_version=11,
        export_params=True
    )
    print("ONNX 导出完成！")

check_onnx(torch_out, img, audio, ONNX_PATH)
