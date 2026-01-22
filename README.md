# Medical Imaging Analysis Suite

这是一个轻量级的医学图像处理工具包，包含两个基于 Python (Tkinter) 开发的独立应用程序，分别用于 **DICOM 序列浏览/导出** 和 **NIfTI 分割结果对比/评估**。

## 📦 包含软件

### 1. DICOM Viewer (`dicom_viewer.py`)
用于快速浏览 DICOM 序列数据，支持筛选和格式转换。

*   **主要功能**:
    *   两栏式高效浏览（病例+序列）。
    *   正则表达式筛选序列（如 `T2`, `Sag`）。
    *   **一键批量导出为 NIfTI** (`.nii.gz`)。
    *   窗宽窗位调整、元数据查看。
*   **[📄 查看详细文档 (README_DICOM_Viewer)](README_DICOM_Viewer.md)**

### 2. NIfTI Viewer (`nii_viewer.py`)
用于可视化查看和对比医学图像分割结果。

*   **主要功能**:
    *   **多模式对比**: 原图 vs 预测 (Pred) vs 真值 (GT)。
    *   **双窗同步**: 左右窗口同步缩放、平移、切片切换。
    *   **差异分析 (Diff)**: 自动高亮显示 False Positive 和 False Negative 区域。
    *   **指标计算**: 实时显示 Dice 和 IoU 评估指标。
*   **[📄 查看详细文档 (README_NIfTI_Viewer)](README_NIfTI_Viewer.md)**

## 🚀 快速开始

### 依赖安装
两个软件均依赖以下 Python 库：
```bash
pip install numpy nibabel pillow pydicom SimpleITK
```

### 启动方式
```bash
# 启动 DICOM 浏览器
python dicom_viewer.py

# 启动 NIfTI 对比工具
python nii_viewer.py
```
