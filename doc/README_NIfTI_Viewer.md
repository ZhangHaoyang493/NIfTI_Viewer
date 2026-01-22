# NIfTI Viewer - 医学图像分割对比工具

这是一个基于 Python 和 Tkinter 开发的轻量级医学图像查看器，专为对比 MRI 原图、模型预测结果 (Pred) 和真值标签 (GT/Ground Truth) 而设计。支持 `.nii.gz` 格式。

![alt text](../img/NIfTI_Viewer.png)

## 🌟 核心功能

*   **智能数据加载**：自动扫描文件夹，识别 MRI、Pred 和 GT 文件。
*   **多视图布局**：
    *   **双窗对比 (Dual)**: 左右分屏同时显示预测和真值，方便横向对比。
    *   **单窗大图**: 支持“仅预测”、“仅真值”模式，最大化显示细节。
    *   **差异分析 (Diff)**: 自动生成 FP/FN 差异图，直观展示模型的多标与漏标区域。
*   **交互式操作**：
    *   **切片导航**: 支持鼠标滚轮和滑动条快速切换切片。
    *   **缩放与平移**: 支持 `Ctrl` + 滚轮无损缩放，鼠标拖拽平移，且**双窗完全同步**。
*   **图像调节**:
    *   **Gamma 校正**: 实时调整 MRI 图像对比度。
    *   **图层开关**: 可一键隐藏/显示分割 Mask。
*   **自动评估**: 实时计算并显示 Dice 系数和 IoU 指标（针对 Label 1 和 Label 2）。
*   **外观**: 简洁的浅色模式界面，高对比度字体。

## 🛠 安装依赖

在使用本软件前，请确保您的环境中安装了以下 Python 库：

```bash
pip install numpy nibabel pillow
```

*   **Python 版本**: 建议 Python 3.8+
*   **系统要求**: Windows / macOS / Linux

## � 数据预处理

本软件对输入数据的文件夹结构有严格要求，请确保您的数据符合以下规范：

**根目录必须包含以下文件夹**：
1.  **`imagesTr`** (必须): 存放 MRI 原图。文件名必须以 `_0000.nii.gz` 结尾。
2.  **`predictsTr`** (可选): 存放模型预测结果。文件名应为 `{CaseName}.nii.gz`。
3.  **`labelsTr`** (可选): 存放真实标签 (GT)。文件名应为 `{CaseName}.nii.gz`。

**文件对应关系示例**：
程序会根据原图文件名自动提取 `CaseName` 来匹配预测和GT。

```text
Dataset_Root/
├── imagesTr/                 # [必须] 原图文件夹
│   ├── Case10_0000.nii.gz    # CaseName = "Case10"
│   ├── Case11_0000.nii.gz
│   └── ...
├── predictsTr/               # [可选] 预测结果文件夹
│   ├── Case10.nii.gz         # 对应 Case10
│   ├── Case11.nii.gz
│   └── ...
└── labelsTr/                 # [可选] GT 文件夹
    ├── Case10.nii.gz         # 对应 Case10
    └── ...
```

> **提示**：如果缺少 `predictsTr` 或 `labelsTr` 文件夹，相关功能（如 Dice 计算、差异分析）将自动禁用。

## �🚀 使用指南

### 1. 启动软件
在终端中运行以下命令启动程序：

```bash
python nii_viewer.py
```

### 2. 加载数据
*   点击左上角的 **“选择根文件夹”** 按钮。
*   选择包含 `imagesTr`, `predictsTr`, `labelsTr` 的父级目录。
*   **默认路径**: 软件默认尝试打开 `~/Desktop/WAIYUAN_DATA`。
*   **文件夹结构要求**:
    必须包含 `imagesTr` 文件夹。可选 `predictsTr` 和 `labelsTr`。
*   示例路径：
```
Dataset_Root
├── imagesTr
│   ├── pcfd_1005_0000.nii.gz
│   └── ...
├── predictsTr
│   ├── pcfd_1005.nii.gz
│   └── ...
└── labelsTr
    ├── pcfd_1005.nii.gz
    └── ...
```

### 3. 操作说明

| 功能 | 操作方式 | 说明 |
| :--- | :--- | :--- |
| **切换切片** | 鼠标滚轮 (无修饰键) <br> 或 拖动左侧滑动条 | 上下翻阅 MRI 切片 |
| **图像缩放** | **Ctrl** (或 Command) + **鼠标滚轮** | 向上放大，向下缩小 |
| **移动视野** | 鼠标 **左键按住拖动** | 仅在放大状态下有效 |
| **调整亮度** | 拖动左侧 "Gamma" 滑动条 | 向右变亮，向左变暗 |
| **切换布局** | 点击左侧 Radio 按钮 | Dual / Pred Only / GT Only / Diff |

### 4. 颜色图例

#### 常规模式 (Dual / Pred / GT)
*   🟢 **Label 1**: 绿色 (Green)
*   🟡 **Label 2**: 黄色 (Yellow)
*   *(透明度约 30%，叠加在 MRI 原图上)*

#### 差异分析模式 (Diff)
仅当存在 GT 时可用。
*   **Label 1 (绿色系)**:
    *   🟢 **亮绿色**: 多标 (False Positive) - 模型标了但 GT 没有。
    *   🌲 **暗绿色**: 漏标 (False Negative) - GT 有但模型没标。
*   **Label 2 (黄色系)**:
    *   🟡 **亮黄色**: 多标 (False Positive)。
    *   🟠 **暗橙色**: 漏标 (False Negative)。

## 📊 评估指标
软件侧边栏会自动显示计算出的指标：
*   **Dice**: Dice Similarity Coefficient (0.0 - 1.0)
*   **IoU**: Intersection over Union (0.0 - 1.0)
