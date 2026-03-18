# THG 模型部署指南

本文档说明如何将训练好的 THG 数字人模型文件从训练项目部署到后端服务中。

## 一、模型训练和生成流程

### 1. 在训练项目中生成模型文件

在 `AI-Interviewer-THG` 项目中，训练完成后需要生成部署用的模型文件：

```bash
# 在 AI-Interviewer-THG 项目目录下
python build_stream_data.py \
  --weights checkpoint_wenet/45.pth \
  --data_dir ./data_dir \
  --mode "wenet" \
  --out_dir "stream_data"
```

这个脚本会：

- 复制图片帧到 `stream_data/img_inference/`
- 复制关键点数据到 `stream_data/lms_inference/`
- 导出 UNet 模型为 `stream_data/unet.onnx`

### 2. 准备 encoder.onnx

`encoder.onnx` 需要单独下载（WeNet 音频编码器）：

```bash
# 在 AI-Interviewer-THG 项目目录下
# 从 Google Drive 下载
ENCODER_ID="1e4Z9zS053JEWl6Mj3W9Lbc9GDtzHIg6b"
gdown "https://drive.google.com/uc?id=${ENCODER_ID}" -O data_utils/encoder.onnx

# 复制到 stream_data 目录
cp data_utils/encoder.onnx stream_data/
```

### 3. 生成的 stream_data 目录结构

训练项目生成的 `stream_data/` 目录应该包含：

```
stream_data/
├── unet.onnx              # UNet 模型（由 build_stream_data.py 生成）
├── encoder.onnx           # 音频编码器（需要单独下载）
├── img_inference/         # 图片帧目录
│   ├── 0.jpg
│   ├── 1.jpg
│   └── ...
└── lms_inference/         # 关键点数据目录
    ├── 0.lms
    ├── 1.lms
    └── ...
```

## 二、模型文件结构（部署要求）

训练完成后，需要准备以下文件结构：

```
stream_data/
├── unet.onnx              # UNet 模型文件（必需）
├── encoder.onnx           # 音频编码器模型文件（必需）
├── img_inference/         # 图片帧目录（必需）
│   ├── 0.jpg
│   ├── 1.jpg
│   ├── 2.jpg
│   └── ...                # 按编号顺序命名，最多 300 帧
└── lms_inference/         # 关键点数据目录（必需）
    ├── 0.lms
    ├── 1.lms
    ├── 2.lms
    └── ...                # 按编号顺序命名，与图片一一对应
```

### 文件说明

1. **unet.onnx**: UNet 模型文件，用于生成数字人面部图像
2. **encoder.onnx**: 音频编码器模型文件，用于提取音频特征
3. **img_inference/**: 包含数字人全身图片帧的目录
   - 文件命名：`0.jpg`, `1.jpg`, `2.jpg`, ...（从 0 开始编号）
   - 格式：JPEG 图片
   - 数量：建议至少 100 帧，最多支持 300 帧
4. **lms_inference/**: 包含关键点数据的目录
   - 文件命名：`0.lms`, `1.lms`, `2.lms`, ...（与图片编号对应）
   - 格式：文本文件，每行一个关键点坐标（x y）
   - 数量：必须与 `img_inference/` 中的图片数量一致

### .lms 文件格式

`.lms` 文件是文本格式，每行包含一个关键点的坐标：

```
x1 y1
x2 y2
x3 y3
...
```

示例（假设有 68 个关键点）：

```
123.5 456.7
124.2 457.1
...
```

## 三、部署步骤

### 步骤 1: 从训练项目复制模型文件

将训练项目中生成的 `stream_data/` 目录复制到部署项目：

```bash
# 方式 1: 直接复制整个目录
cp -r /path/to/AI-Interviewer-THG/stream_data /path/to/digital-human/backend/

# 方式 2: 使用部署脚本（推荐）
cd /path/to/digital-human/backend
./deploy_model.sh /path/to/AI-Interviewer-THG/stream_data
```

### 步骤 2: 验证文件完整性

确保以下文件都存在：

```bash
# 创建目录结构
mkdir -p stream_data/img_inference
mkdir -p stream_data/lms_inference

# 复制模型文件
cp path/to/unet.onnx stream_data/
cp path/to/encoder.onnx stream_data/

# 复制图片帧（确保按编号命名：0.jpg, 1.jpg, ...）
cp path/to/images/*.jpg stream_data/img_inference/

# 复制关键点文件（确保按编号命名：0.lms, 1.lms, ...）
cp path/to/landmarks/*.lms stream_data/lms_inference/
```

### 步骤 3: 配置环境变量

创建或编辑 `.env` 文件（在 `backend/` 目录下）：

```bash
# 方式 1: 使用相对路径（推荐，如果 stream_data 在 backend/ 目录下）
THG_DATA_PATH=./stream_data

# 方式 2: 使用绝对路径
THG_DATA_PATH=/absolute/path/to/stream_data

# GPU 配置（可选，默认 true）
THG_USE_GPU=true
```

### 步骤 4: 验证配置

运行测试脚本验证配置是否正确：

```bash
cd backend
python test_thg_config.py
```

如果看到以下输出，说明配置成功：

```
==================================================
THG 配置测试
==================================================

1. 配置检查:
   thg_data_path: ./stream_data
   thg_use_gpu: True

2. 路径检查:
   ./stream_data: ✅ 存在
   绝对路径: /path/to/backend/stream_data
   包含 4 个文件/目录
     - unet.onnx
     - encoder.onnx
     - img_inference
     - lms_inference

3. Orchestrator 初始化测试:
   使用的服务: RealTHGService
   ✅ 成功使用 RealTHGService
```

### 步骤 5: 启动服务

```bash
# 从项目根目录启动
./start.sh

# 或手动启动后端
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload
```

## 四、从训练到部署的完整流程

### 流程图

```
AI-Interviewer-THG (训练项目)
    ↓
1. 训练模型 → checkpoint_wenet/45.pth
    ↓
2. 运行 build_stream_data.py → 生成 stream_data/
    ├── unet.onnx (自动生成)
    ├── img_inference/ (自动复制)
    └── lms_inference/ (自动复制)
    ↓
3. 下载 encoder.onnx → 放入 stream_data/
    ↓
4. 复制 stream_data/ → digital-human/backend/
    ↓
5. 配置环境变量 → backend/.env
    ↓
6. 验证和启动 → 服务运行
```

### 详细步骤

#### 在训练项目中（AI-Interviewer-THG）

```bash
# 1. 进入训练项目目录
cd /path/to/AI-Interviewer-THG

# 2. 生成 stream_data（假设已经训练完成）
python build_stream_data.py \
  --weights checkpoint_wenet/45.pth \
  --data_dir ./data_dir \
  --mode "wenet" \
  --out_dir "stream_data"

# 3. 下载 encoder.onnx（如果还没有）
ENCODER_ID="1e4Z9zS053JEWl6Mj3W9Lbc9GDtzHIg6b"
gdown "https://drive.google.com/uc?id=${ENCODER_ID}" -O data_utils/encoder.onnx

# 4. 复制 encoder.onnx 到 stream_data
cp data_utils/encoder.onnx stream_data/

# 5. 验证生成的文件
ls -la stream_data/
ls stream_data/img_inference/ | head
ls stream_data/lms_inference/ | head
```

#### 在部署项目中（digital-human）

```bash
# 1. 进入部署项目后端目录
cd /path/to/digital-human/backend

# 2. 使用部署脚本（推荐）
./deploy_model.sh /path/to/AI-Interviewer-THG/stream_data

# 或手动复制
cp -r /path/to/AI-Interviewer-THG/stream_data .

# 3. 配置环境变量
echo "THG_DATA_PATH=./stream_data" >> .env
echo "THG_USE_GPU=true" >> .env

# 4. 验证配置
python test_thg_config.py

# 5. 启动服务
cd ..
./start.sh
```

## 五、常见问题

### 1. 找不到模型文件

**错误信息**：

```
[ERROR] Failed to create ONNX Runtime sessions: FileNotFoundError
```

**解决方法**：

- 检查 `THG_DATA_PATH` 环境变量是否正确
- 确认 `unet.onnx` 和 `encoder.onnx` 文件存在
- 检查文件路径是相对路径还是绝对路径

### 2. 找不到图片或关键点文件

**错误信息**：

```
[INFO] found 0 images, 0 lms, using 0 frames
```

**解决方法**：

- 确认 `img_inference/` 和 `lms_inference/` 目录存在
- 检查文件命名是否正确（必须是 `0.jpg`, `1.jpg`, ... 和 `0.lms`, `1.lms`, ...）
- 确认文件数量一致

### 3. GPU 不可用

**错误信息**：

```
[WARNING] No GPU execution provider available, falling back to CPU
```

**解决方法**：

- 如果使用 CPU，这是正常的，服务会自动回退到 CPU
- 如果想使用 GPU：
  - macOS: 确保安装了支持 CoreML 的 ONNX Runtime
  - Linux/Windows: 确保安装了 CUDA 和对应的 ONNX Runtime

### 4. 图片和关键点数量不匹配

**错误信息**：

```
[INFO] found 100 images, 50 lms, using 50 frames
```

**解决方法**：

- 确保 `img_inference/` 和 `lms_inference/` 中的文件数量一致
- 检查文件编号是否连续（0, 1, 2, ...）

## 六、文件命名规范

### 图片文件

- **格式**: JPEG (`.jpg`)
- **命名**: 从 `0.jpg` 开始，连续编号
- **示例**: `0.jpg`, `1.jpg`, `2.jpg`, ..., `299.jpg`

### 关键点文件

- **格式**: 文本文件 (`.lms`)
- **命名**: 从 `0.lms` 开始，与图片编号对应
- **示例**: `0.lms`, `1.lms`, `2.lms`, ..., `299.lms`
- **内容**: 每行一个关键点坐标，格式为 `x y`（空格分隔）

## 七、性能优化建议

1. **帧数限制**: 代码中限制最多加载 300 帧，如果文件过多，只会使用前 300 帧
2. **预加载**: 所有图片和关键点会在初始化时预加载到内存，确保有足够内存
3. **GPU 加速**: 如果硬件支持，建议启用 GPU 加速（`THG_USE_GPU=true`）

## 八、部署检查清单

部署前请确认：

- [ ] `unet.onnx` 文件存在且可读
- [ ] `encoder.onnx` 文件存在且可读
- [ ] `img_inference/` 目录存在且包含图片文件
- [ ] `lms_inference/` 目录存在且包含关键点文件
- [ ] 图片和关键点文件数量一致
- [ ] 文件命名符合规范（从 0 开始连续编号）
- [ ] `.env` 文件中配置了 `THG_DATA_PATH`
- [ ] 运行 `test_thg_config.py` 测试通过
- [ ] 服务启动后日志显示 `✅ RealTHGService initialized successfully`

## 九、示例配置

### 本地开发环境

```bash
# backend/.env
THG_DATA_PATH=./stream_data
THG_USE_GPU=true
```

### 生产环境（Docker）

```dockerfile
# Dockerfile
ENV THG_DATA_PATH=/app/stream_data
ENV THG_USE_GPU=true

COPY stream_data /app/stream_data
```

### 生产环境（环境变量）

```bash
export THG_DATA_PATH=/data/digital-human/stream_data
export THG_USE_GPU=true
```

## 十、相关文件

- `backend/app/services/dihuman_core.py`: 模型加载和推理核心代码
- `backend/app/services/thg_service.py`: THG 服务封装
- `backend/app/config.py`: 配置管理
- `backend/test_thg_config.py`: 配置测试脚本
