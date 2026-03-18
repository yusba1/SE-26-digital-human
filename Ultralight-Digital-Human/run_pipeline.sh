#!/bin/bash
set -e

# ================================================================
#  数字人一键训练推理脚本
# ================================================================
#  使用方法:
#    1. 将训练视频放到 data_utils/<PROJECT_NAME>/ 目录下
#    2. 将推理测试音频放到同一目录下
#    3. 修改下方「项目配置」和「训练超参数」
#    4. 运行: bash run_pipeline.sh
# ================================================================

# ================== 项目配置（必填） ==================
PROJECT_NAME="Veo1"              # 项目名称，用作文件夹名
VIDEO_FILE="veo1_20fps.mp4"                # 训练视频文件名（放在 data_utils/<PROJECT_NAME>/ 下）
TEST_AUDIO_FILE="veo1_test.wav"      # 推理音频文件名（同目录，支持 mp3/wav/m4a 等）

# ================== 训练超参数 ==================
ASR_MODE="wenet"                      # 音频特征类型: "wenet"(视频需20fps) 或 "hubert"(视频需25fps)
EPOCHS=80                            # 训练轮次
BATCH_SIZE=32                         # 批次大小
LEARNING_RATE=0.001                   # 初始学习率
LR_DECAY_STEP=20                      # 学习率衰减间隔（每 N 轮衰减一次）
LR_DECAY_FACTOR=0.5                   # 学习率衰减因子
SAVE_INTERVAL=30                      # 模型保存间隔（每 N 轮保存一次）
NUM_WORKERS=4                         # DataLoader 工作进程数
USE_SYNCNET=True                     # 是否使用 SyncNet（True/False）
PERCEPTUAL_LOSS_WEIGHT=0.02           # 感知损失权重
SYNC_LOSS_WEIGHT=10                   # SyncNet 损失权重（USE_SYNCNET=True 时生效）
SEE_RESULTS=False                     # 是否可视化训练中间结果

# ================== SyncNet 训练超参数（USE_SYNCNET=True 时生效） ==================
SYNCNET_EPOCHS=15                     # SyncNet 训练轮次
SYNCNET_BATCH_SIZE=32                 # SyncNet 批次大小
SYNCNET_LEARNING_RATE=0.001           # SyncNet 学习率
SYNCNET_SAVE_INTERVAL=20               # SyncNet 保存间隔（0=每轮保存）

# ================== 推理与打包配置 ==================
INFERENCE_START_FRAME=1500               # 推理起始帧（0=从第1帧开始）
INFERENCE_END_FRAME=1650                # 推理结束帧（-1=使用最后一帧；如 1:10~1:25 可设 1400~1699）
PACK_COUNT=150                        # 兜底打包数量（未设置 INFERENCE_END_FRAME 时，从起始帧起打包 N 张）

# ================================================================
#  以下为自动执行流程，一般无需修改
# ================================================================

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="./data_utils/${PROJECT_NAME}"
CHECKPOINT_DIR="./checkpoints/${PROJECT_NAME}"
SYNCNET_DIR="./checkpoints/${PROJECT_NAME}_syncnet"
SYNCNET_CHECKPOINT="${SYNCNET_DIR}/final.pth"

# 根据 ASR 模式确定目标帧率
if [ "$ASR_MODE" = "wenet" ]; then
    TARGET_FPS=20
elif [ "$ASR_MODE" = "hubert" ]; then
    TARGET_FPS=25
else
    echo "[错误] ASR_MODE 必须是 wenet 或 hubert，当前值: $ASR_MODE"
    exit 1
fi

log_step() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

check_file() {
    if [ ! -f "$1" ]; then
        echo "[错误] 文件不存在: $1"
        exit 1
    fi
}

cd "$ROOT_DIR"

# --------------------------------------------------
# Step 1: 视频预处理
# --------------------------------------------------
log_step "Step 1/7: 视频预处理（转帧率 + 提取音频/图片/关键点/音频特征）"

VIDEO_PATH="${DATA_DIR}/${VIDEO_FILE}"
check_file "$VIDEO_PATH"

# 确定音频特征文件名
if [ "$ASR_MODE" = "wenet" ]; then
    TRAIN_FEAT_FILE="${DATA_DIR}/aud_wenet.npy"
else
    TRAIN_FEAT_FILE="${DATA_DIR}/aud_hu.npy"
fi

# 检测预处理数据是否已完整存在
PREPROCESS_NEEDED=false
IMG_COUNT=$(ls "${DATA_DIR}/full_body_img/" 2>/dev/null | wc -l)
LMS_COUNT=$(ls "${DATA_DIR}/landmarks/" 2>/dev/null | wc -l)

if [ "$IMG_COUNT" -eq 0 ]; then
    echo "[检测] full_body_img/ 为空或不存在，需要预处理"
    PREPROCESS_NEEDED=true
elif [ "$LMS_COUNT" -eq 0 ]; then
    echo "[检测] landmarks/ 为空或不存在，需要预处理"
    PREPROCESS_NEEDED=true
elif [ "$IMG_COUNT" -ne "$LMS_COUNT" ]; then
    echo "[检测] 图片(${IMG_COUNT})与关键点(${LMS_COUNT})数量不匹配，需要重新预处理"
    PREPROCESS_NEEDED=true
elif [ ! -s "$TRAIN_FEAT_FILE" ]; then
    echo "[检测] 音频特征文件不存在，需要预处理"
    PREPROCESS_NEEDED=true
fi

if [ "$PREPROCESS_NEEDED" = "true" ]; then
    echo "开始预处理..."

    # 获取当前帧率
    CURRENT_FPS_RAW=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO_PATH")
    FPS_NUM=$(echo "$CURRENT_FPS_RAW" | cut -d'/' -f1)
    FPS_DEN=$(echo "$CURRENT_FPS_RAW" | cut -d'/' -f2)
    CURRENT_FPS=$((FPS_NUM / FPS_DEN))

    VIDEO_BASENAME="${VIDEO_FILE%.*}"
    VIDEO_CONVERTED="${DATA_DIR}/${VIDEO_BASENAME}_${TARGET_FPS}fps.mp4"

    if [ "$CURRENT_FPS" != "$TARGET_FPS" ]; then
        echo "转换帧率: ${CURRENT_FPS}fps -> ${TARGET_FPS}fps ..."
        ffmpeg -y -i "$VIDEO_PATH" -r "$TARGET_FPS" \
            -c:v libx264 -crf 18 -preset fast -c:a copy \
            "$VIDEO_CONVERTED" 2>&1 | tail -3
    else
        echo "帧率已是 ${TARGET_FPS}fps，跳过转换"
        VIDEO_CONVERTED="$VIDEO_PATH"
    fi

    # 检查转换后视频是否有音频轨
    HAS_AUDIO=$(ffprobe -v error -select_streams a -show_entries stream=codec_type \
        -of csv=p=0 "$VIDEO_CONVERTED" 2>/dev/null | head -1)

    # 运行预处理
    echo "运行 process.py 预处理流程..."
    cd "${ROOT_DIR}/data_utils"
    python process.py "${PROJECT_NAME}/$(basename "$VIDEO_CONVERTED")" --asr "$ASR_MODE"
    cd "$ROOT_DIR"

    # 如果转帧率视频无音频轨，从原始视频补提音频
    WAV_PATH="${DATA_DIR}/aud.wav"
    if [ ! -s "$WAV_PATH" ] || [ -z "$HAS_AUDIO" ]; then
        echo "从原始视频补充提取音频..."
        ffmpeg -y -i "$VIDEO_PATH" -f wav -ar 16000 -ac 1 "$WAV_PATH" 2>&1 | tail -3
        # 重新提取音频特征
        echo "重新提取音频特征..."
        cd "${ROOT_DIR}/data_utils"
        if [ "$ASR_MODE" = "wenet" ]; then
            python wenet_infer.py "${PROJECT_NAME}/aud.wav"
        else
            python hubert.py --wav "${PROJECT_NAME}/aud.wav"
        fi
        cd "$ROOT_DIR"
    fi

    # 重新统计
    IMG_COUNT=$(ls "${DATA_DIR}/full_body_img/" | wc -l)
    LMS_COUNT=$(ls "${DATA_DIR}/landmarks/" | wc -l)
    echo "[完成] 预处理: ${IMG_COUNT} 帧图片, ${LMS_COUNT} 个关键点"
else
    echo "[跳过] 预处理数据已完整: ${IMG_COUNT} 帧图片, ${LMS_COUNT} 个关键点, 音频特征已存在"
fi

# --------------------------------------------------
# Step 2: 训练 SyncNet（仅 USE_SYNCNET=True 时执行）
# --------------------------------------------------
if [ "$USE_SYNCNET" = "True" ]; then
    log_step "Step 2/7: 训练 SyncNet 模型"

    if [ -s "$SYNCNET_CHECKPOINT" ]; then
        echo "[跳过] SyncNet 模型已存在: ${SYNCNET_CHECKPOINT}"
    else
        echo "开始训练 SyncNet（${SYNCNET_EPOCHS} 轮）..."
        mkdir -p "$SYNCNET_DIR"

        python -c "
import syncnet
syncnet.DATASET_DIR = '${DATA_DIR}'
syncnet.SAVE_DIR = '${SYNCNET_DIR}'
syncnet.ASR_MODE = '${ASR_MODE}'
syncnet.EPOCHS = ${SYNCNET_EPOCHS}
syncnet.BATCH_SIZE = ${SYNCNET_BATCH_SIZE}
syncnet.LEARNING_RATE = ${SYNCNET_LEARNING_RATE}
syncnet.SAVE_INTERVAL = ${SYNCNET_SAVE_INTERVAL}
syncnet.NUM_WORKERS = ${NUM_WORKERS}
syncnet.train()
"
        echo "[完成] SyncNet 训练完毕，模型: ${SYNCNET_CHECKPOINT}"
    fi
else
    log_step "Step 2/7: 跳过 SyncNet 训练（USE_SYNCNET=False）"
fi

# --------------------------------------------------
# Step 3: 训练主模型
# --------------------------------------------------
log_step "Step 3/7: 训练主模型"

MAIN_MODEL="${CHECKPOINT_DIR}/final.pth"

if [ -s "$MAIN_MODEL" ]; then
    echo "[跳过] 主模型已存在: ${MAIN_MODEL}"
else
    echo "开始训练主模型（${EPOCHS} 轮）..."
    mkdir -p "$CHECKPOINT_DIR"

    python -c "
import train
train.DATASET_DIR = '${DATA_DIR}'
train.SAVE_DIR = '${CHECKPOINT_DIR}'
train.ASR_MODE = '${ASR_MODE}'
train.EPOCHS = ${EPOCHS}
train.BATCH_SIZE = ${BATCH_SIZE}
train.LEARNING_RATE = ${LEARNING_RATE}
train.LR_DECAY_STEP = ${LR_DECAY_STEP}
train.LR_DECAY_FACTOR = ${LR_DECAY_FACTOR}
train.SAVE_INTERVAL = ${SAVE_INTERVAL}
train.NUM_WORKERS = ${NUM_WORKERS}
train.USE_SYNCNET = ${USE_SYNCNET}
train.SYNCNET_CHECKPOINT = '${SYNCNET_CHECKPOINT}'
train.PERCEPTUAL_LOSS_WEIGHT = ${PERCEPTUAL_LOSS_WEIGHT}
train.SYNC_LOSS_WEIGHT = ${SYNC_LOSS_WEIGHT}
train.SEE_RESULTS = ${SEE_RESULTS}
train.train()
"
    echo "[完成] 主模型训练完毕，保存在 ${CHECKPOINT_DIR}/"
fi

# --------------------------------------------------
# Step 3: 推理生成视频
# --------------------------------------------------
log_step "Step 4/7: 推理合成视频"

TEST_AUDIO_PATH="${DATA_DIR}/${TEST_AUDIO_FILE}"
check_file "$TEST_AUDIO_PATH"

# 音频转 WAV（若非 wav 格式或采样率不对）
TEST_AUDIO_EXT="${TEST_AUDIO_FILE##*.}"
TEST_AUDIO_BASENAME="${TEST_AUDIO_FILE%.*}"
TEST_AUDIO_WAV="${DATA_DIR}/${TEST_AUDIO_BASENAME}.wav"

if [ "${TEST_AUDIO_EXT,,}" != "wav" ]; then
    echo "转换音频为 16kHz WAV ..."
    ffmpeg -y -i "$TEST_AUDIO_PATH" -f wav -ar 16000 -ac 1 "$TEST_AUDIO_WAV" 2>&1 | tail -3
else
    SAMPLE_RATE=$(ffprobe -v error -select_streams a:0 \
        -show_entries stream=sample_rate -of csv=p=0 "$TEST_AUDIO_PATH")
    if [ "$SAMPLE_RATE" != "16000" ]; then
        echo "转换音频采样率为 16kHz ..."
        ffmpeg -y -i "$TEST_AUDIO_PATH" -f wav -ar 16000 -ac 1 \
            "${TEST_AUDIO_WAV}.tmp" 2>&1 | tail -3
        mv "${TEST_AUDIO_WAV}.tmp" "$TEST_AUDIO_WAV"
    else
        TEST_AUDIO_WAV="$TEST_AUDIO_PATH"
    fi
fi

# 提取推理音频的特征
if [ "$ASR_MODE" = "wenet" ]; then
    AUDIO_FEAT_PATH="${DATA_DIR}/${TEST_AUDIO_BASENAME}_wenet.npy"
else
    AUDIO_FEAT_PATH="${DATA_DIR}/${TEST_AUDIO_BASENAME}_hu.npy"
fi

if [ -s "$AUDIO_FEAT_PATH" ]; then
    echo "[跳过] 推理音频特征已存在: $(basename "$AUDIO_FEAT_PATH")"
else
    echo "提取推理音频特征..."
    cd "${ROOT_DIR}/data_utils"
    if [ "$ASR_MODE" = "wenet" ]; then
        python wenet_infer.py "${PROJECT_NAME}/${TEST_AUDIO_BASENAME}.wav"
    else
        python hubert.py --wav "${PROJECT_NAME}/${TEST_AUDIO_BASENAME}.wav"
    fi
    cd "$ROOT_DIR"
fi

# 运行推理
OUTPUT_VIDEO="${DATA_DIR}/${PROJECT_NAME}_test.mp4"
SILENT_VIDEO="${DATA_DIR}/_tmp_silent.avi"

START_FRAME_ARG=""
if [ "$INFERENCE_START_FRAME" -gt 0 ] 2>/dev/null; then
    START_FRAME_ARG="--start_frame ${INFERENCE_START_FRAME}"
fi
END_FRAME_ARG=""
if [ "$INFERENCE_END_FRAME" -ge 0 ] 2>/dev/null; then
    END_FRAME_ARG="--end_frame ${INFERENCE_END_FRAME}"
fi

if [ -n "$END_FRAME_ARG" ]; then
    echo "生成视频（帧范围: ${INFERENCE_START_FRAME} ~ ${INFERENCE_END_FRAME}）..."
else
    echo "生成视频（起始帧: ${INFERENCE_START_FRAME}，结束帧: 自动到最后一帧）..."
fi
python inference.py \
    --asr "$ASR_MODE" \
    --dataset "$DATA_DIR" \
    --audio_feat "$AUDIO_FEAT_PATH" \
    --save_path "$SILENT_VIDEO" \
    --checkpoint "${CHECKPOINT_DIR}/final.pth" \
    $START_FRAME_ARG \
    $END_FRAME_ARG

# 合并音频
echo "合并音频生成最终视频..."
ffmpeg -y -i "$SILENT_VIDEO" -i "$TEST_AUDIO_PATH" \
    -c:v libx264 -crf 18 -preset fast -c:a aac -b:a 128k \
    -shortest "$OUTPUT_VIDEO" 2>&1 | tail -3
rm -f "$SILENT_VIDEO"

echo "[完成] 视频已生成: $OUTPUT_VIDEO"

# --------------------------------------------------
# Step 4: 打包图片和关键点
# --------------------------------------------------
log_step "Step 5/7: 打包前 ${PACK_COUNT} 张图片和关键点"

# 打包范围优先与推理范围保持一致；未设置结束帧时退化为从起始帧打包 PACK_COUNT 张
PACK_START=$INFERENCE_START_FRAME
if [ "$PACK_START" -lt 0 ] 2>/dev/null; then
    PACK_START=0
fi
if [ "$PACK_START" -gt $((IMG_COUNT - 1)) ] 2>/dev/null; then
    PACK_START=$((IMG_COUNT - 1))
fi

if [ "$INFERENCE_END_FRAME" -ge 0 ] 2>/dev/null; then
    PACK_END=$INFERENCE_END_FRAME
else
    PACK_END=$((PACK_START + PACK_COUNT - 1))
fi

if [ "$PACK_END" -gt $((IMG_COUNT - 1)) ] 2>/dev/null; then
    PACK_END=$((IMG_COUNT - 1))
fi
if [ "$PACK_END" -lt "$PACK_START" ] 2>/dev/null; then
    PACK_END=$PACK_START
fi

ACTUAL_COUNT=$((PACK_END - PACK_START + 1))
ZIP_FILE="${ROOT_DIR}/data_utils/${PROJECT_NAME}/${PROJECT_NAME}_${PACK_START}_${PACK_END}.zip"

if [ -s "$ZIP_FILE" ]; then
    echo "[跳过] 打包文件已存在: $(basename "$ZIP_FILE")"
else
    PACK_DIR=$(mktemp -d)
    mkdir -p "${PACK_DIR}/full_body_img" "${PACK_DIR}/landmarks"

    for i in $(seq "$PACK_START" "$PACK_END"); do
        cp "${DATA_DIR}/full_body_img/${i}.jpg" "${PACK_DIR}/full_body_img/${i}.jpg"
        cp "${DATA_DIR}/landmarks/${i}.lms" "${PACK_DIR}/landmarks/${i}.lms"
    done

    cd "$PACK_DIR"
    zip -qr "$ZIP_FILE" full_body_img/ landmarks/
    cd "$ROOT_DIR"
    rm -rf "$PACK_DIR"

    echo "[完成] 打包: $(basename "$ZIP_FILE")（帧范围 ${PACK_START}~${PACK_END}，共 ${ACTUAL_COUNT} 对文件）"
fi

# --------------------------------------------------
# Step 5: 转换 ONNX
# --------------------------------------------------
log_step "Step 6/7: 转换 PyTorch 模型为 ONNX"

PTH_FILE="${CHECKPOINT_DIR}/final.pth"
ONNX_FILE="${CHECKPOINT_DIR}/${PROJECT_NAME}_${ASR_MODE}.onnx"

if [ -s "$ONNX_FILE" ]; then
    echo "[跳过] ONNX 模型已存在: $(basename "$ONNX_FILE")"
else
    cd "$ROOT_DIR"
    TMP_CONVERT=$(mktemp "${ROOT_DIR}/_pth2onnx_XXXX.py")
    sed \
        -e "s|^PTH_PATH = .*|PTH_PATH = \"${PTH_FILE}\"|" \
        -e "s|^ONNX_PATH = .*|ONNX_PATH = \"${ONNX_FILE}\"|" \
        -e "s|^ASR_MODE = .*|ASR_MODE = \"${ASR_MODE}\"|" \
        pth2onnx.py > "$TMP_CONVERT"
    python "$TMP_CONVERT"
    rm -f "$TMP_CONVERT"

    echo "[完成] ONNX 模型: $(basename "$ONNX_FILE")"
fi

# --------------------------------------------------
# Step 6: 总结
# --------------------------------------------------
log_step "Step 7/7: 全部完成"

echo "项目名称:   ${PROJECT_NAME}"
echo "数据目录:   ${DATA_DIR}/"
echo "  图片帧数: ${IMG_COUNT}"
echo "  关键点数: ${LMS_COUNT}"
echo "  打包文件: $(basename "$ZIP_FILE")"
echo ""
if [ "$USE_SYNCNET" = "True" ]; then
echo "SyncNet:    ${SYNCNET_DIR}/final.pth"
fi
echo "模型目录:   ${CHECKPOINT_DIR}/"
echo "  PyTorch:  final.pth"
echo "  ONNX:     $(basename "$ONNX_FILE")"
echo ""
echo "推理视频:   ${OUTPUT_VIDEO}"
echo ""
echo "全部流程已完成！"
