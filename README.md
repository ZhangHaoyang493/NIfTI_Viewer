# Medical Imaging Analysis Suite

这是一个轻量级的医学图像处理工具包，包含两个基于 Python (Tkinter) 开发的独立应用程序，分别用于 **DICOM 序列浏览/导出** 和 **NIfTI 分割结果对比/评估**。

## 📦 包含软件

### 1. DICOM Viewer (`src/dicom_viewer.py`)
用于快速浏览 DICOM 序列数据，支持筛选和格式转换。

*   **主要功能**:
    *   两栏式高效浏览（病例+序列）。
    *   正则表达式筛选序列（如 `T2`, `Sag`）。
    *   **一键批量导出为 NIfTI** (`.nii.gz`)。
    *   窗宽窗位调整、元数据查看。
*   **[📄 查看详细文档 (README_DICOM_Viewer)](doc/README_DICOM_Viewer.md)**

### 2. NIfTI Viewer (`src/nii_viewer.py`)
用于可视化查看和对比医学图像分割结果。

*   **主要功能**:
    *   **多模式对比**: 原图 vs 预测 (Pred) vs 真值 (GT)。
    *   **双窗同步**: 左右窗口同步缩放、平移、切片切换。
    *   **差异分析 (Diff)**: 自动高亮显示 False Positive 和 False Negative 区域。
    *   **指标计算**: 实时显示 Dice 和 IoU 评估指标。
*   **[📄 查看详细文档 (README_NIfTI_Viewer)](doc/README_NIfTI_Viewer.md)**

## 🚀 快速开始

### 环境配置 (使用 uv)

本项目使用 [uv](https://docs.astral.sh/uv/) 进行依赖管理。

1. **安装 uv** (如果尚未安装):
   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # 或者 macOS: brew install uv
   
   # Windows
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   # 或者使用 pip: pip install uv
   ```

2. **同步环境**:
   在项目根目录下运行，这将自动创建虚拟环境并安装所需依赖：
   ```bash
   uv sync
   ```

### 启动方式
使用 `uv run` 直接运行应用程序（无需手动激活虚拟环境）：
```bash
# 启动 DICOM 浏览器
uv run src/dicom_viewer.py

# 启动 NIfTI 对比工具
uv run src/nii_viewer.py
```
