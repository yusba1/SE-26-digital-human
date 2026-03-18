import os
import cv2
import torch
import numpy as np
import torch.nn as nn
from torch import optim
from tqdm import tqdm
from torch.utils.data import DataLoader
from datasetsss import MyDataset
from syncnet import SyncNet_color
from unet import Model
import random
import torchvision.models as models

# ============================================================
# 可调整参数配置（修改这里即可）
# ============================================================

# 数据集路径
DATASET_DIR = "./data_utils/Veo3"

# 模型保存路径
SAVE_DIR = "./checkpoints/Veo3"

# 音频特征类型: "wenet" 或 "hubert"
ASR_MODE = "wenet"

# 训练轮次
EPOCHS = 60

# 批次大小
BATCH_SIZE = 32

# 初始学习率
LEARNING_RATE = 0.001

# 学习率衰减间隔（每多少轮衰减一次）
LR_DECAY_STEP = 20

# 学习率衰减因子（衰减至原来的多少倍）
LR_DECAY_FACTOR = 0.5

# 模型保存间隔（每多少轮保存一次）
SAVE_INTERVAL = 29

# 是否使用 SyncNet
USE_SYNCNET = False

# SyncNet 权重路径（USE_SYNCNET=True 时需要设置）
SYNCNET_CHECKPOINT = ""

# 是否可视化训练结果
SEE_RESULTS = False

# 感知损失权重
PERCEPTUAL_LOSS_WEIGHT = 0.01

# SyncNet 损失权重（USE_SYNCNET=True 时生效）
SYNC_LOSS_WEIGHT = 10

# DataLoader 工作进程数
NUM_WORKERS = 4

# ============================================================
# 以下为训练代码，一般无需修改
# ============================================================

device = 'cuda' if torch.cuda.is_available() else 'cpu'

class PerceptualLoss():
    
    def contentFunc(self):
        conv_3_3_layer = 14
        cnn = models.vgg19(pretrained=True).features
        cnn = cnn.to(device)
        model = nn.Sequential()
        model = model.to(device)
        for i, layer in enumerate(list(cnn)):
            model.add_module(str(i), layer)
            if i == conv_3_3_layer:
                break
        return model

    def __init__(self, loss):
        self.criterion = loss
        self.contentFunc = self.contentFunc()

    def get_loss(self, fakeIm, realIm):
        f_fake = self.contentFunc.forward(fakeIm)
        f_real = self.contentFunc.forward(realIm)
        f_real_no_grad = f_real.detach()
        loss = self.criterion(f_fake, f_real_no_grad)
        return loss

logloss = nn.BCELoss()

def cosine_loss(a, v, y):
    d = nn.functional.cosine_similarity(a, v)
    loss = logloss(d.unsqueeze(1), y)
    return loss

def adjust_learning_rate(optimizer, epoch, initial_lr, decay_step, decay_factor):
    """每 decay_step 轮衰减学习率"""
    lr = initial_lr * (decay_factor ** (epoch // decay_step))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    return lr

def train():
    print("=" * 60)
    print("训练配置:")
    print(f"  数据集路径: {DATASET_DIR}")
    print(f"  模型保存路径: {SAVE_DIR}")
    print(f"  ASR 模式: {ASR_MODE}")
    print(f"  训练轮次: {EPOCHS}")
    print(f"  批次大小: {BATCH_SIZE}")
    print(f"  初始学习率: {LEARNING_RATE}")
    print(f"  学习率衰减间隔: 每 {LR_DECAY_STEP} 轮")
    print(f"  学习率衰减因子: {LR_DECAY_FACTOR}")
    print(f"  模型保存间隔: 每 {SAVE_INTERVAL} 轮")
    print(f"  使用 SyncNet: {USE_SYNCNET}")
    print(f"  设备: {device}")
    print("=" * 60)
    
    # 创建模型
    net = Model(6, ASR_MODE).to(device)
    
    # 创建感知损失
    content_loss = PerceptualLoss(torch.nn.MSELoss())
    
    # 加载 SyncNet（如果使用）
    if USE_SYNCNET:
        if SYNCNET_CHECKPOINT == "":
            raise ValueError("使用 SyncNet 时需要设置 SYNCNET_CHECKPOINT 路径")
        syncnet = SyncNet_color(ASR_MODE).eval().to(device)
        syncnet.load_state_dict(torch.load(SYNCNET_CHECKPOINT))
    
    # 创建保存目录
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    
    # 加载数据集
    dataset = MyDataset(DATASET_DIR, ASR_MODE)
    train_dataloader = DataLoader(
        dataset, 
        batch_size=BATCH_SIZE, 
        shuffle=True, 
        drop_last=False, 
        num_workers=NUM_WORKERS
    )
    
    # 优化器和损失函数
    optimizer = optim.Adam(net.parameters(), lr=LEARNING_RATE)
    criterion = nn.L1Loss()
    
    # 训练循环
    for epoch in range(EPOCHS):
        net.train()
        
        # 调整学习率
        current_lr = adjust_learning_rate(
            optimizer, epoch, LEARNING_RATE, LR_DECAY_STEP, LR_DECAY_FACTOR
        )
        
        with tqdm(total=len(dataset), desc=f'Epoch {epoch + 1}/{EPOCHS} (lr={current_lr:.6f})', unit='img') as pbar:
            for batch in train_dataloader:
                imgs, labels, audio_feat = batch
                imgs = imgs.to(device)
                labels = labels.to(device)
                audio_feat = audio_feat.to(device)
                
                preds = net(imgs, audio_feat)
                
                # 计算损失
                loss_pixel = criterion(preds, labels)
                loss_perceptual = content_loss.get_loss(preds, labels)
                
                if USE_SYNCNET:
                    y = torch.ones([preds.shape[0], 1]).float().to(device)
                    a, v = syncnet(preds, audio_feat)
                    sync_loss = cosine_loss(a, v, y)
                    loss = loss_pixel + loss_perceptual * PERCEPTUAL_LOSS_WEIGHT + SYNC_LOSS_WEIGHT * sync_loss
                else:
                    loss = loss_pixel + loss_perceptual * PERCEPTUAL_LOSS_WEIGHT
                
                pbar.set_postfix(**{'loss': loss.item(), 'lr': current_lr})
                
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
                pbar.update(imgs.shape[0])
        
        # 保存模型
        if epoch % SAVE_INTERVAL == 0:
            save_path = os.path.join(SAVE_DIR, f'{epoch}.pth')
            torch.save(net.state_dict(), save_path)
            print(f"模型已保存: {save_path}")
        
        # 可视化结果
        if SEE_RESULTS:
            net.eval()
            os.makedirs("./train_tmp_img", exist_ok=True)
            idx = random.randint(0, len(dataset) - 1)
            img_concat_T, img_real_T, audio_feat = dataset[idx]
            img_concat_T = img_concat_T[None].to(device)
            audio_feat = audio_feat[None].to(device)
            with torch.no_grad():
                pred = net(img_concat_T, audio_feat)[0]
            pred = pred.cpu().numpy().transpose(1, 2, 0) * 255
            pred = np.array(pred, dtype=np.uint8)
            img_real = img_real_T.numpy().transpose(1, 2, 0) * 255
            img_real = np.array(img_real, dtype=np.uint8)
            cv2.imwrite(f"./train_tmp_img/epoch_{epoch}.jpg", pred)
            cv2.imwrite(f"./train_tmp_img/epoch_{epoch}_real.jpg", img_real)
    
    # 保存最终模型
    final_path = os.path.join(SAVE_DIR, 'final.pth')
    torch.save(net.state_dict(), final_path)
    print(f"训练完成！最终模型已保存: {final_path}")

if __name__ == '__main__':
    train()
