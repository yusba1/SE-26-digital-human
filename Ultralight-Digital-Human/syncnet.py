import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader
import cv2
import os
import numpy as np
from torch import optim
import random
from tqdm import tqdm

# ============================================================
# 可调整参数配置（修改这里即可，然后直接 python syncnet.py）
# ============================================================

# 数据集路径
DATASET_DIR = "./data_utils/Veo3"

# 模型保存路径
SAVE_DIR = "./checkpoints/Veo3_syncnet"

# 音频特征类型: "wenet" 或 "hubert"
ASR_MODE = "wenet"

# 训练轮次
EPOCHS = 15

# 批次大小
BATCH_SIZE = 32

# 初始学习率
LEARNING_RATE = 0.001

# 模型保存间隔（每多少轮保存一次，0 表示每轮都保存）
SAVE_INTERVAL = 29

# DataLoader 工作进程数
NUM_WORKERS = 4

# ============================================================
# 以下为模型与训练代码，一般无需修改
# ============================================================



class Dataset(object):
    def __init__(self, dataset_dir, mode):
        
        self.img_path_list = []
        self.lms_path_list = []
        
        for i in range(len(os.listdir(dataset_dir+"/full_body_img/"))):

            img_path = os.path.join(dataset_dir+"/full_body_img/", str(i)+".jpg")
            lms_path = os.path.join(dataset_dir+"/landmarks/", str(i)+".lms")
            self.img_path_list.append(img_path)
            self.lms_path_list.append(lms_path)
                
        if mode=="wenet":
            audio_feats_path = dataset_dir+"/aud_wenet.npy"
        if mode=="hubert":
            audio_feats_path = dataset_dir+"/aud_hu.npy"
        self.mode = mode
        self.audio_feats = np.load(audio_feats_path)
        self.audio_feats = self.audio_feats.astype(np.float32)
        
    def __len__(self):

        return self.audio_feats.shape[0]-1

    def get_audio_features(self, features, index):
        
        left = index - 4
        right = index + 4
        pad_left = 0
        pad_right = 0
        if left < 0:
            pad_left = -left
            left = 0
        if right > features.shape[0]:
            pad_right = right - features.shape[0]
            right = features.shape[0]
        auds = torch.from_numpy(features[left:right])
        if pad_left > 0:
            auds = torch.cat([torch.zeros_like(auds[:pad_left]), auds], dim=0)
        if pad_right > 0:
            auds = torch.cat([auds, torch.zeros_like(auds[:pad_right])], dim=0) # [8, 16]
        return auds
    
    def process_img(self, img, lms_path, img_ex, lms_path_ex):

        lms_list = []
        with open(lms_path, "r") as f:
            lines = f.read().splitlines()
            for line in lines:
                arr = line.split(" ")
                arr = np.array(arr, dtype=np.float32)
                lms_list.append(arr)
        lms = np.array(lms_list, dtype=np.int32)
        xmin = lms[1][0]
        ymin = lms[52][1]
        
        xmax = lms[31][0]
        width = xmax - xmin
        ymax = ymin + width
        
        crop_img = img[ymin:ymax, xmin:xmax]
        crop_img = cv2.resize(crop_img, (168, 168), cv2.INTER_AREA)
        img_real = crop_img[4:164, 4:164].copy()
        img_real_ori = img_real.copy()
        img_real_ori = img_real_ori.transpose(2,0,1).astype(np.float32)
        img_real_T = torch.from_numpy(img_real_ori / 255.0)
        
        return img_real_T

    def __getitem__(self, idx):
        img = cv2.imread(self.img_path_list[idx])
        lms_path = self.lms_path_list[idx]
        
        ex_int = random.randint(0, self.__len__()-1)
        img_ex = cv2.imread(self.img_path_list[ex_int])
        lms_path_ex = self.lms_path_list[ex_int]
        
        img_real_T = self.process_img(img, lms_path, img_ex, lms_path_ex)
        audio_feat = self.get_audio_features(self.audio_feats, idx) # 
        # print(audio_feat.shape)
        if self.mode=="wenet":
            audio_feat = audio_feat.reshape(128,16,32)
        if self.mode=="hubert":
            audio_feat = audio_feat.reshape(16,32,32)
        y = torch.ones(1).float()
        
        return img_real_T, audio_feat, y

class Conv2d(nn.Module):
    def __init__(self, cin, cout, kernel_size, stride, padding, residual=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conv_block = nn.Sequential(
                            nn.Conv2d(cin, cout, kernel_size, stride, padding),
                            nn.BatchNorm2d(cout)
                            )
        self.act = nn.ReLU()
        self.residual = residual

    def forward(self, x):
        out = self.conv_block(x)
        if self.residual:
            out += x
        return self.act(out)

class nonorm_Conv2d(nn.Module):
    def __init__(self, cin, cout, kernel_size, stride, padding, residual=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conv_block = nn.Sequential(
                            nn.Conv2d(cin, cout, kernel_size, stride, padding),
                            )
        self.act = nn.LeakyReLU(0.01, inplace=True)

    def forward(self, x):
        out = self.conv_block(x)
        return self.act(out)

class Conv2dTranspose(nn.Module):
    def __init__(self, cin, cout, kernel_size, stride, padding, output_padding=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conv_block = nn.Sequential(
                            nn.ConvTranspose2d(cin, cout, kernel_size, stride, padding, output_padding),
                            nn.BatchNorm2d(cout)
                            )
        self.act = nn.ReLU()

    def forward(self, x):
        out = self.conv_block(x)
        return self.act(out)

class SyncNet_color(nn.Module):
    def __init__(self, mode):
        super(SyncNet_color, self).__init__()

        self.face_encoder = nn.Sequential(
            Conv2d(3, 32, kernel_size=(7, 7), stride=1, padding=3),

            Conv2d(32, 64, kernel_size=5, stride=2, padding=1),
            Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(64, 64, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(128, 128, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(256, 512, kernel_size=3, stride=2, padding=1),
            Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(512, 512, kernel_size=3, stride=2, padding=1),
            Conv2d(512, 512, kernel_size=3, stride=1, padding=0),
            Conv2d(512, 512, kernel_size=1, stride=1, padding=0),)
        
        p1 = 128
        p2 = (1, 2)
        if mode == "hubert":
            p1 = 16
            p2 = (2, 2)
        
        self.audio_encoder = nn.Sequential(
            Conv2d(p1, 256, kernel_size=3, stride=1, padding=1),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
            
            Conv2d(256, 256, kernel_size=3, stride=p2, padding=1),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(256, 256, kernel_size=3, stride=2, padding=2),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(256, 256, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(256, 512, kernel_size=3, stride=2, padding=1),
            Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),
            Conv2d(512, 512, kernel_size=3, stride=1, padding=1, residual=True),

            Conv2d(512, 512, kernel_size=3, stride=1, padding=0),
            Conv2d(512, 512, kernel_size=1, stride=1, padding=0),)

    def forward(self, face_sequences, audio_sequences): # audio_sequences := (B, dim, T)
        face_embedding = self.face_encoder(face_sequences)
        audio_embedding = self.audio_encoder(audio_sequences)

        audio_embedding = audio_embedding.view(audio_embedding.size(0), -1)
        face_embedding = face_embedding.view(face_embedding.size(0), -1)

        audio_embedding = F.normalize(audio_embedding, p=2, dim=1)
        face_embedding = F.normalize(face_embedding, p=2, dim=1)
        
        return audio_embedding, face_embedding

device = 'cuda' if torch.cuda.is_available() else 'cpu'

logloss = nn.BCELoss()
def cosine_loss(a, v, y):
    d = nn.functional.cosine_similarity(a, v)
    loss = logloss(d.unsqueeze(1), y)
    return loss

def train():
    print("=" * 60)
    print("SyncNet 训练配置:")
    print(f"  数据集路径: {DATASET_DIR}")
    print(f"  模型保存路径: {SAVE_DIR}")
    print(f"  ASR 模式: {ASR_MODE}")
    print(f"  训练轮次: {EPOCHS}")
    print(f"  批次大小: {BATCH_SIZE}")
    print(f"  学习率: {LEARNING_RATE}")
    print(f"  模型保存间隔: 每 {SAVE_INTERVAL} 轮")
    print(f"  设备: {device}")
    print("=" * 60)

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    train_dataset = Dataset(DATASET_DIR, mode=ASR_MODE)
    train_data_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS
    )

    model = SyncNet_color(ASR_MODE).to(device)
    optimizer = optim.Adam(
        [p for p in model.parameters() if p.requires_grad],
        lr=LEARNING_RATE
    )

    for epoch in range(EPOCHS):
        model.train()
        epoch_loss = 0.0
        batch_count = 0

        with tqdm(total=len(train_dataset), desc=f'Epoch {epoch + 1}/{EPOCHS}', unit='sample') as pbar:
            for batch in train_data_loader:
                imgT, audioT, y = batch
                imgT = imgT.to(device)
                audioT = audioT.to(device)
                y = y.to(device)

                audio_embedding, face_embedding = model(imgT, audioT)
                loss = cosine_loss(audio_embedding, face_embedding, y)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                batch_count += 1
                pbar.set_postfix(loss=loss.item())
                pbar.update(imgT.shape[0])

        avg_loss = epoch_loss / max(batch_count, 1)
        print(f"Epoch {epoch + 1}/{EPOCHS} - 平均损失: {avg_loss:.6f}")

        # 保存模型
        if SAVE_INTERVAL == 0 or (epoch + 1) % SAVE_INTERVAL == 0:
            save_path = os.path.join(SAVE_DIR, f'{epoch}.pth')
            torch.save(model.state_dict(), save_path)
            print(f"模型已保存: {save_path}")

    # 保存最终模型
    final_path = os.path.join(SAVE_DIR, 'final.pth')
    torch.save(model.state_dict(), final_path)
    print(f"训练完成！最终模型已保存: {final_path}")

if __name__ == "__main__":
    train()
