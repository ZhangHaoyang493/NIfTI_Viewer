# NIfTI Viewer - 医学图像分割对比工具

这是一个基于 Python 和 Tkinter 开发的医学图像查看器，专为对比 MRI 原图、模型预测结果 (Pred) 和真值标签 (GT/Ground Truth) 而设计，支持 `.nii.gz` 格式。

![NIfTI Viewer](img/NIfTI_Viewer.png)

## 🌟 核心功能

- **智能数据加载**：自动扫描数据目录并匹配 `imagesTr / predictsTr / labelsTr`。
- **多视图布局**：
  - **双窗对比 (Dual)**：左侧 Pred，右侧 GT。
  - **单窗模式**：`Pred Only` / `GT Only`。
  - **差异分析 (Diff)**：高亮 FP/FN 区域。
  - **RAS 三窗布局**：`S | A | R` 三窗口并排显示，每窗滚轮独立切片。
- **RAS 交互增强**：
  - 左侧 `Slice Navigation` 在 RAS 模式默认绑定 `S` 轴。
  - 三窗顶部显示方位标记 `S / A / R`。
  - 支持按体素 spacing 进行物理比例显示，减少 A/R 方向“扁平”感。
- **交互式操作**：
  - 鼠标滚轮 / 滑动条切片。
  - `Ctrl/Command + 滚轮` 缩放。
  - 鼠标拖拽平移。
  - `↑/↓` 快速切换病例。
- **图像调节**：Gamma 校正、图层显示开关。
- **标注与修正**：
  - 画笔、橡皮擦、魔棒、填充。
  - 撤销（`Ctrl/Command + Z`）。
  - 当前切片 `Label 1 ↔ Label 2` 反转。
  - 按当前选中标签执行整卷序列反转（`0..N-1 -> N-1..0`）。
- **导出增强**：导出 Label 时恢复至原始参考方向，保持原始方向码一致。
- **数据统计面板**：
  - 逐例显示 `images/predicts/labels` 方向码（如 `RAS/PSI`）。
  - 显示 predicts/labels 的 mask 值分布。
  - 汇总方向不一致、单一 mask、缺失文件、读取错误病例。
- **自动评估**：实时计算并显示 Dice / IoU（Label 1 和 Label 2）。

## 🛠 安装依赖

### 方式一：使用 uv（推荐）

```bash
uv sync
```

### 方式二：使用 pip

```bash
pip install numpy nibabel pillow
```

- Python 版本建议：3.8+
- 系统支持：Windows / macOS / Linux

## 📂 数据准备规范

根目录需包含：

1. `imagesTr`（必须）：原图，文件名需以 `_0000.nii.gz` 结尾。
2. `predictsTr`（可选）：预测结果，文件名为 `{CaseName}.nii.gz`。
3. `labelsTr`（可选）：真值标签，文件名为 `{CaseName}.nii.gz`。

示例：

```text
Dataset_Root/
├── imagesTr/
│   ├── Case10_0000.nii.gz
│   └── ...
├── predictsTr/
│   ├── Case10.nii.gz
│   └── ...
└── labelsTr/
    ├── Case10.nii.gz
    └── ...
```

> 若缺少 `predictsTr` 或 `labelsTr`，对应功能会自动降级（如无 GT 时禁用 Diff）。

## 🚀 启动方式

### 使用 uv

```bash
uv run src/nii_viewer.py
```

### 使用 python

```bash
python src/nii_viewer.py
```

## 🧭 使用说明

1. 点击“选择根文件夹”，选择包含 `imagesTr` 的数据根目录。
2. 在左侧病例列表选择病例加载。
3. 根据需要切换布局（Dual / Pred Only / GT Only / Diff / RAS）。
4. 使用滚轮、滑动条或快捷键浏览切片。
5. 如需修正标签，开启编辑模式后使用工具栏进行编辑并导出。

## ⌨️ 常用操作与快捷键

| 功能 | 操作 |
| :--- | :--- |
| 切换切片 | 鼠标滚轮 / 左侧滑动条 / `←` `→` |
| 缩放 | `Ctrl/Command + 滚轮` |
| 平移 | 鼠标左键拖拽（编辑时可用中键拖拽） |
| 撤销 | `Ctrl/Command + Z` |
| 切换病例 | `↑` / `↓` |
| 旋转显示 | 左侧“旋转90°”按钮 |

## 🧪 编辑与导出说明

- 编辑优先级：有 GT 时基于 GT 编辑；无 GT 时基于 Pred；再无则基于空白 mask。
- “反转 1↔2”：仅作用于当前切片。
- “反转序列”：仅作用于当前选中标签值（Label 1 或 Label 2）。
- 导出路径：`<Dataset_Root>/EditLabelTrs/{CaseName}.nii.gz`。
- 导出结果：保持与原始参考图像方向一致。

## 📊 指标与统计

- 评估指标：Dice / IoU（Label 1, Label 2）。
- 数据统计面板：展示逐例方向码、mask 值及汇总异常信息。

## 📄 文档说明

历史文档 `doc/README_NIfTI_Viewer.md` 已并入本 README，后续以本文件为准。
