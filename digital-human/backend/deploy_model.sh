#!/bin/bash
# THG 模型部署脚本
# 用法: ./deploy_model.sh <模型文件路径>

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "THG 模型部署脚本"
echo "=========================================="

# 检查参数
if [ $# -lt 1 ]; then
    echo -e "${RED}错误: 请提供模型文件路径${NC}"
    echo "用法: $0 <模型文件路径>"
    echo "示例: $0 /path/to/stream_data"
    exit 1
fi

MODEL_PATH="$1"
TARGET_DIR="./stream_data"

# 检查源路径是否存在
if [ ! -d "$MODEL_PATH" ]; then
    echo -e "${RED}错误: 模型路径不存在: $MODEL_PATH${NC}"
    exit 1
fi

echo -e "${YELLOW}源路径: $MODEL_PATH${NC}"
echo -e "${YELLOW}目标路径: $TARGET_DIR${NC}"
echo ""

# 检查必需文件
echo "检查必需文件..."
REQUIRED_FILES=("unet.onnx" "encoder.onnx")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$MODEL_PATH/$file" ]; then
        MISSING_FILES+=("$file")
    else
        echo -e "  ${GREEN}✓${NC} $file"
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo -e "${RED}错误: 缺少必需文件:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo -e "  ${RED}✗${NC} $file"
    done
    exit 1
fi

# 检查目录
echo ""
echo "检查目录..."
REQUIRED_DIRS=("img_inference" "lms_inference")
MISSING_DIRS=()

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$MODEL_PATH/$dir" ]; then
        MISSING_DIRS+=("$dir")
    else
        file_count=$(find "$MODEL_PATH/$dir" -type f | wc -l)
        echo -e "  ${GREEN}✓${NC} $dir ($file_count 个文件)"
    fi
done

if [ ${#MISSING_DIRS[@]} -gt 0 ]; then
    echo -e "${RED}错误: 缺少必需目录:${NC}"
    for dir in "${MISSING_DIRS[@]}"; do
        echo -e "  ${RED}✗${NC} $dir"
    done
    exit 1
fi

# 检查图片和关键点数量
IMG_COUNT=$(find "$MODEL_PATH/img_inference" -name "*.jpg" | wc -l)
LMS_COUNT=$(find "$MODEL_PATH/lms_inference" -name "*.lms" | wc -l)

echo ""
echo "文件统计:"
echo "  图片文件: $IMG_COUNT"
echo "  关键点文件: $LMS_COUNT"

if [ "$IMG_COUNT" -ne "$LMS_COUNT" ]; then
    echo -e "${YELLOW}警告: 图片和关键点文件数量不一致${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 备份现有文件（如果存在）
if [ -d "$TARGET_DIR" ]; then
    echo ""
    echo -e "${YELLOW}目标目录已存在，是否备份? (y/n)${NC}"
    read -p "" -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        BACKUP_DIR="${TARGET_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
        echo "备份到: $BACKUP_DIR"
        mv "$TARGET_DIR" "$BACKUP_DIR"
    else
        echo -e "${YELLOW}删除现有目录...${NC}"
        rm -rf "$TARGET_DIR"
    fi
fi

# 复制文件
echo ""
echo "复制文件..."
mkdir -p "$TARGET_DIR"
cp "$MODEL_PATH/unet.onnx" "$TARGET_DIR/"
cp "$MODEL_PATH/encoder.onnx" "$TARGET_DIR/"
cp -r "$MODEL_PATH/img_inference" "$TARGET_DIR/"
cp -r "$MODEL_PATH/lms_inference" "$TARGET_DIR/"

echo -e "${GREEN}✓ 文件复制完成${NC}"

# 检查 .env 文件
echo ""
echo "检查配置..."
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}创建 .env 文件...${NC}"
    cat > "$ENV_FILE" << EOF
# THG 模型配置
THG_DATA_PATH=./stream_data
THG_USE_GPU=true
EOF
    echo -e "${GREEN}✓ .env 文件已创建${NC}"
else
    if grep -q "THG_DATA_PATH" "$ENV_FILE"; then
        echo -e "${GREEN}✓ .env 文件中已配置 THG_DATA_PATH${NC}"
    else
        echo -e "${YELLOW}添加 THG_DATA_PATH 到 .env 文件...${NC}"
        echo "" >> "$ENV_FILE"
        echo "# THG 模型配置" >> "$ENV_FILE"
        echo "THG_DATA_PATH=./stream_data" >> "$ENV_FILE"
        echo "THG_USE_GPU=true" >> "$ENV_FILE"
        echo -e "${GREEN}✓ 配置已添加${NC}"
    fi
fi

# 运行测试
echo ""
echo "运行配置测试..."
if [ -f "test_thg_config.py" ]; then
    python test_thg_config.py
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}=========================================="
        echo "部署成功！"
        echo "==========================================${NC}"
        echo ""
        echo "下一步:"
        echo "  1. 检查上述测试输出，确认配置正确"
        echo "  2. 启动服务: cd .. && ./start.sh"
        echo "  3. 或手动启动: python -m uvicorn app.main:app --reload"
    else
        echo -e "${RED}测试失败，请检查配置${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}警告: 未找到 test_thg_config.py，跳过测试${NC}"
    echo ""
    echo -e "${GREEN}=========================================="
    echo "文件部署完成！"
    echo "==========================================${NC}"
    echo ""
    echo "下一步:"
    echo "  1. 运行测试: python test_thg_config.py"
    echo "  2. 启动服务: cd .. && ./start.sh"
fi
