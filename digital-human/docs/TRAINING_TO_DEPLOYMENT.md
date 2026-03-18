# 从训练到部署：完整流程指南

本文档说明如何从 `AI-Interviewer-THG` 训练项目生成模型文件，并部署到 `digital-human` 服务项目。

## 项目关系

```
AI-Interviewer-THG (训练项目)
    ↓ 生成模型文件
stream_data/ 目录
    ↓ 复制到部署项目
digital-human (服务项目)
    ↓ 配置和启动
运行中的数字人服务
```

## 快速部署流程

### 第一步：在训练项目中生成模型文件

```bash
# 进入训练项目目录
cd /Users/Parry/Desktop/GitHub/AI-Interviewer-THG

# 1. 运行 build_stream_data.py 生成模型文件
python build_stream_data.py \
  --weights checkpoint_wenet/45.pth \
  --data_dir ./data_dir \
  --mode "wenet" \
  --out_dir "stream_data"

# 2. 下载 encoder.onnx（如果还没有）
ENCODER_ID="1e4Z9zS053JEWl6Mj3W9Lbc9GDtzHIg6b"
gdown "https://drive.google.com/uc?id=${ENCODER_ID}" -O data_utils/encoder.onnx

# 3. 复制 encoder.onnx 到 stream_data
cp data_utils/encoder.onnx stream_data/

# 4. 验证生成的文件
ls -la stream_data/
# 应该看到：
# - unet.onnx
# - encoder.onnx
# - img_inference/ (目录)
# - lms_inference/ (目录)
```

### 第二步：部署到服务项目

```bash
# 进入部署项目后端目录
cd /Users/Parry/Desktop/youth/00-code/digital-human/backend

# 方式 1: 使用部署脚本（推荐）
./deploy_model.sh /Users/Parry/Desktop/GitHub/AI-Interviewer-THG/stream_data

# 方式 2: 手动部署
cp -r /Users/Parry/Desktop/GitHub/AI-Interviewer-THG/stream_data .

# 配置环境变量
echo "THG_DATA_PATH=./stream_data" >> .env
echo "THG_USE_GPU=true" >> .env

# 验证配置
python test_thg_config.py
```

### 第三步：启动服务

```bash
# 从项目根目录启动
cd /Users/Parry/Desktop/youth/00-code/digital-human
./start.sh
```

## 文件对应关系

### 训练项目生成的文件

```
AI-Interviewer-THG/
└── stream_data/              # 由 build_stream_data.py 生成
    ├── unet.onnx             # UNet 模型（自动生成）
    ├── encoder.onnx          # 音频编码器（需单独下载）
    ├── img_inference/        # 图片帧（自动复制）
    │   ├── 0.jpg
    │   ├── 1.jpg
    │   └── ...
    └── lms_inference/        # 关键点数据（自动复制）
        ├── 0.lms
        ├── 1.lms
        └── ...
```

### 部署项目需要的文件

```
digital-human/
└── backend/
    └── stream_data/          # 从训练项目复制过来
        ├── unet.onnx
        ├── encoder.onnx
        ├── img_inference/
        └── lms_inference/
```

## 关键文件说明

### 1. build_stream_data.py

**位置**: `AI-Interviewer-THG/build_stream_data.py`

**作用**:

- 将训练好的 PyTorch 模型（`.pth`）转换为 ONNX 格式（`unet.onnx`）
- 复制图片帧到 `img_inference/`
- 复制关键点数据到 `lms_inference/`

**用法**:

```bash
python build_stream_data.py \
  --weights <checkpoint_path> \
  --data_dir <dataset_path> \
  --mode "wenet" \
  --out_dir "stream_data"
```

### 2. encoder.onnx

**来源**: WeNet 音频编码器，需要从 Google Drive 下载

**下载命令**:

```bash
ENCODER_ID="1e4Z9zS053JEWl6Mj3W9Lbc9GDtzHIg6b"
gdown "https://drive.google.com/uc?id=${ENCODER_ID}" -O data_utils/encoder.onnx
```

**注意**: 这个文件是通用的，不需要重新训练，直接下载使用即可。

### 3. deploy_model.sh

**位置**: `digital-human/backend/deploy_model.sh`

**作用**: 自动化部署流程，包括：

- 检查必需文件
- 复制文件到正确位置
- 配置环境变量
- 运行测试验证

## 常见问题

### Q1: build_stream_data.py 在哪里？

**A**: 在 `AI-Interviewer-THG` 项目根目录下。如果找不到，检查是否在正确的项目目录。

### Q2: encoder.onnx 必须下载吗？

**A**: 是的，`encoder.onnx` 是 WeNet 音频编码器，是预训练模型，需要单独下载。它不会由 `build_stream_data.py` 生成。

### Q3: 可以只复制部分文件吗？

**A**: 不可以。所有文件都是必需的：

- `unet.onnx` - 必需
- `encoder.onnx` - 必需
- `img_inference/` - 必需
- `lms_inference/` - 必需

### Q4: 训练项目和服务项目的 dihuman_core.py 一样吗？

**A**: 基本相同，但服务项目的版本增加了 GPU 支持（CoreML/CUDA）和更好的错误处理。建议使用服务项目的版本。

### Q5: 如何更新模型？

**A**:

1. 在训练项目中重新训练并生成新的 `stream_data/`
2. 使用部署脚本重新部署
3. 重启服务

## 验证清单

部署前确认：

- [ ] 训练项目已生成 `stream_data/` 目录
- [ ] `stream_data/unet.onnx` 存在
- [ ] `stream_data/encoder.onnx` 存在
- [ ] `stream_data/img_inference/` 目录存在且包含图片
- [ ] `stream_data/lms_inference/` 目录存在且包含关键点文件
- [ ] 图片和关键点文件数量一致
- [ ] 文件已复制到 `digital-human/backend/stream_data/`
- [ ] `.env` 文件已配置 `THG_DATA_PATH`
- [ ] `test_thg_config.py` 测试通过

## 相关文档

- [详细部署指南](MODEL_DEPLOYMENT.md) - 完整的部署说明
- [训练项目 README](../AI-Interviewer-THG/README.md) - 训练项目说明
- [服务项目 README](../README.md) - 服务项目说明
