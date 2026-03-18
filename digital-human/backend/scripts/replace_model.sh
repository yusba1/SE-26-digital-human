#!/bin/bash

# 数字人模型替换脚本
# 用法: ./replace_model.sh <your_model_directory>

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$BACKEND_DIR"

# 检查参数
if [ $# -lt 1 ]; then
    echo -e "${RED}❌ 错误: 请提供模型目录路径${NC}"
    echo ""
    echo "用法: $0 <your_model_directory> [--backup]"
    echo ""
    echo "参数:"
    echo "  your_model_directory  你的模型目录路径（包含 unet.onnx, encoder.onnx, img_inference/, lms_inference/）"
    echo "  --backup               备份现有模型（可选）"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/your/model"
    echo "  $0 /path/to/your/model --backup"
    exit 1
fi

MODEL_DIR="$1"
BACKUP_FLAG="$2"

# 检查模型目录是否存在
if [ ! -d "$MODEL_DIR" ]; then
    echo -e "${RED}❌ 错误: 模型目录不存在: $MODEL_DIR${NC}"
    exit 1
fi

# 检查必需文件
echo -e "${BLUE}🔍 检查模型文件...${NC}"

MISSING_FILES=0

if [ ! -f "$MODEL_DIR/unet.onnx" ]; then
    echo -e "${RED}  ❌ 未找到: unet.onnx${NC}"
    MISSING_FILES=1
else
    echo -e "${GREEN}  ✅ 找到: unet.onnx${NC}"
fi

if [ ! -f "$MODEL_DIR/encoder.onnx" ]; then
    echo -e "${RED}  ❌ 未找到: encoder.onnx${NC}"
    MISSING_FILES=1
else
    echo -e "${GREEN}  ✅ 找到: encoder.onnx${NC}"
fi

if [ ! -d "$MODEL_DIR/img_inference" ]; then
    echo -e "${RED}  ❌ 未找到: img_inference/ 目录${NC}"
    MISSING_FILES=1
else
    IMG_COUNT=$(ls -1 "$MODEL_DIR/img_inference"/*.jpg 2>/dev/null | wc -l)
    echo -e "${GREEN}  ✅ 找到: img_inference/ ($IMG_COUNT 张图片)${NC}"
fi

if [ ! -d "$MODEL_DIR/lms_inference" ]; then
    echo -e "${RED}  ❌ 未找到: lms_inference/ 目录${NC}"
    MISSING_FILES=1
else
    LMS_COUNT=$(ls -1 "$MODEL_DIR/lms_inference"/*.lms 2>/dev/null | wc -l)
    echo -e "${GREEN}  ✅ 找到: lms_inference/ ($LMS_COUNT 个文件)${NC}"
fi

if [ $MISSING_FILES -eq 1 ]; then
    echo -e "${RED}❌ 模型文件不完整，请检查模型目录${NC}"
    exit 1
fi

# 检查图片和关键点数量是否匹配
if [ "$IMG_COUNT" != "$LMS_COUNT" ]; then
    echo -e "${YELLOW}⚠️  警告: 图片数量 ($IMG_COUNT) 与关键点数量 ($LMS_COUNT) 不匹配${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 备份现有模型
if [ "$BACKUP_FLAG" == "--backup" ]; then
    BACKUP_DIR="stream_data_backup_$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}📦 备份现有模型到: $BACKUP_DIR${NC}"
    cp -r stream_data "$BACKUP_DIR"
    echo -e "${GREEN}✅ 备份完成${NC}"
fi

# 替换模型文件
echo -e "${BLUE}🔄 替换模型文件...${NC}"

# 替换 ONNX 模型
echo -e "${YELLOW}  替换 unet.onnx...${NC}"
cp "$MODEL_DIR/unet.onnx" stream_data/

echo -e "${YELLOW}  替换 encoder.onnx...${NC}"
cp "$MODEL_DIR/encoder.onnx" stream_data/

# 备份并替换数据目录
if [ -d "stream_data/img_inference" ]; then
    echo -e "${YELLOW}  备份 img_inference...${NC}"
    mv stream_data/img_inference stream_data/img_inference_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
fi

if [ -d "stream_data/lms_inference" ]; then
    echo -e "${YELLOW}  备份 lms_inference...${NC}"
    mv stream_data/lms_inference stream_data/lms_inference_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
fi

echo -e "${YELLOW}  复制 img_inference...${NC}"
cp -r "$MODEL_DIR/img_inference" stream_data/

echo -e "${YELLOW}  复制 lms_inference...${NC}"
cp -r "$MODEL_DIR/lms_inference" stream_data/

echo -e "${GREEN}✅ 模型替换完成${NC}"

# 显示替换后的文件信息
echo ""
echo -e "${BLUE}📊 替换后的模型信息:${NC}"
echo -e "  UNet 模型: $(ls -lh stream_data/unet.onnx | awk '{print $5}')"
echo -e "  Encoder 模型: $(ls -lh stream_data/encoder.onnx | awk '{print $5}')"
echo -e "  图片数量: $(ls -1 stream_data/img_inference/*.jpg 2>/dev/null | wc -l)"
echo -e "  关键点数量: $(ls -1 stream_data/lms_inference/*.lms 2>/dev/null | wc -l)"

echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo -e "  1. 请重启服务以使新模型生效: ${BLUE}./stop.sh && ./start.sh${NC}"
echo -e "  2. 查看后端日志确认模型加载: ${BLUE}tail -f backend.log${NC}"
echo -e "  3. 如果遇到问题，请参考: ${BLUE}backend/MODEL_REPLACEMENT_GUIDE.md${NC}"
