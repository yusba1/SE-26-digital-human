# 数字人推理与渲染性能分析

用于排查「跑起来之后推理时快时慢、渲染帧率不足 20」的问题。

## 1. 后端推理性能测试（推荐先跑）

在 **backend** 目录下执行（需已安装依赖并具备 `stream_data` 与模型）。若使用虚拟环境请先激活：

```bash
cd backend
source venv/bin/activate   # Windows: venv\Scripts\activate
python scripts/performance_profile.py
```

可选参数：

- `--seconds 15`：正式计时时长（秒），默认 10
- `--warmup 2`：预热时长（秒），默认 2
- `--cpu`：强制 CPU，不则使用 `dihuman_core.USE_GPU`
- `--data-path /path/to/stream_data`：覆盖数据目录

脚本会输出：

- **输出帧数** 与 **实测输出帧率 (FPS)**：当前算法下后端能产生的帧率
- **process() 耗时**：单次 `process()` 的 mean / P50 / P95 / P99（毫秒）
- **仅「有输出帧」的 process() 耗时**：真正产图那几次的耗时
- **JPEG 编码耗时**：`cv2.imencode(.jpg, quality=95)` 的 mean / P95

### 如何解读

1. **实测 FPS 远低于 20**
   - 算法设计：`dihuman_core` 需攒够 **8 个音频特征** 才输出 1 帧，且每步只消耗 800 样本（50ms 音频），理论产出约 **2.5～5 FPS** 量级，无法达到 20 FPS。若要接近 20 FPS，需改模型/算法（如降低特征帧数、步长或换更轻量结构）。
   - 若 **单次 process() 平均/P95 很高**（例如 >80ms）：说明单帧推理或前处理过慢，可能原因包括：未用 GPU、ONNX 提供方或内核慢、图像过大、JPEG 编码在 CPU 上过重。

2. **process() 时快时慢（P99 远高于 P50）**
   - 只有部分调用会跑 Encoder+UNet（`using_feat.shape[0]>=8` 时），其它只做缓冲或轻量逻辑，因此会出现「有时很慢、有时很快」；看「仅「有输出帧」的 process() 耗时」更能反映真实推理开销。

3. **JPEG 编码耗时偏高**
   - 若 mean > 10～20ms，可尝试：降分辨率、降 quality（如 85）、或把编码挪到单独线程/进程，避免阻塞推理循环。

## 2. 运行期轻量计时（可选）

在 `backend/app/services/dihuman_core.py` 顶部将：

```python
PROFILE_EVERY_N_FRAMES = 0
```

改为例如：

```python
PROFILE_EVERY_N_FRAMES = 60
```

则服务运行时每隔 60 个输出帧会打一条日志：`[DiHuman] 推理耗时: 近 60 帧平均 XX ms/帧`，便于在真实请求下观察稳定性。排查完建议改回 `0` 关闭。

## 3. 可能瓶颈汇总

| 位置 | 现象 | 建议 |
|------|------|------|
| 算法设计 | 8 特征帧才出 1 图，理论 FPS 上限约 2.5～5 | 改模型/步长或接受当前上限 |
| ONNX 推理 | 单帧 UNet/Encoder 耗时长 | 确认 GPU 生效、提供方与内核版本 |
| JPEG 编码 | 单帧编码 >15ms | 降质量/分辨率或异步编码 |
| 前端 | 解码/绘制或 RAF 同步导致卡顿 | 用开发者工具 Performance 看帧时间与主线程 |
| 网络 | WebSocket 发送大图导致阻塞 | 降分辨率/码率或分片 |

## 4. 前端帧率

前端目标帧率为 `App.tsx` 中的 `TARGET_FPS = 20`，实际渲染帧率还受限于：

- 后端实际下发的帧率（若后端 <20 FPS，前端无法达到 20）
- 每帧 JPEG 解码 + Canvas 绘制时间
- 音视频同步逻辑（按音频时间戳丢弃或等待帧）

若后端 FPS 已达标而前端仍卡顿，可在浏览器 Performance 面板查看主线程与合成器，确认是否在解码或 Canvas 上耗时过长。
