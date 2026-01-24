import os
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import numpy as np
import nibabel as nib
from PIL import Image, ImageTk

class NiiViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NIfTI Viewer - MRI & Segmentation Comparator")
        self.root.geometry("1400x800")

        # --- 变量初始化 ---
        self.current_slice_index = 0
        self.total_slices = 0
        self.root_dir = ""
        self.valid_cases = [] # 存储字典: {'name': str, 'mri_path': str, 'pred_path': str, 'gt_path': str or None}
        self.current_case_data = {} # 存储加载后的numpy数组: 'mri', 'pred', 'gt'
        self.has_pred_folder = False
        self.has_gt_folder = False
        
        # 显示设置变量
        self.status_msg = tk.StringVar(value="请选择根文件夹 (需包含 imagesTr [必须], predictsTr [可选], labelsTr [可选])")
        self.status_color = tk.StringVar(value="black")
        self.status_metrics_msg = tk.StringVar(value="") # 状态栏的指标信息
        self.gamma_val = tk.DoubleVar(value=1.0)
        self.show_pred = tk.BooleanVar(value=True)
        self.show_gt = tk.BooleanVar(value=True)
        self.auto_fit_window = tk.BooleanVar(value=False) # 新增自适应变量
        self.layout_mode = tk.StringVar(value="dual") # dual, left, right
        self.slice_info_text = tk.StringVar(value="Slice: 0 / 0")
        self.metrics_text = tk.StringVar(value="")
        self.case_list_title = tk.StringVar(value="病例列表 (0):")

        # 缩放和平移状态
        self.rotation_k = 0  # 旋转次数 (k * 90度 逆时针)
        self.zoom_level = 1.0
        self.pan_center_x = 0.5  # 相对坐标 (0.0 - 1.0)
        self.pan_center_y = 0.5
        self.drag_start_x = 0
        self.drag_start_y = 0

        # 防止图片被垃圾回收
        self.tk_img_left = None
        self.tk_img_right = None

        # --- UI 布局 ---
        self._setup_ui()

    def _setup_ui(self):
        """配置界面布局"""
        # 0. 底部状态栏 (提示栏)
        # 增大高度：使用 Frame + height / padding
        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN, height=35, bg="#f8f8f8")
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        status_frame.pack_propagate(False) # 允许 height 生效

        # 左侧：状态消息
        self.lbl_status = tk.Label(status_frame, textvariable=self.status_msg, 
                                   fg="black", bg="#f8f8f8", font=("Arial", 11))
        # 增加左侧间距 padx
        self.lbl_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # 中间/紧随：指标信息
        self.lbl_metrics_bottom = tk.Label(status_frame, textvariable=self.status_metrics_msg,
                                           fg="blue", bg="#f8f8f8", font=("Arial", 11, "bold"))
        self.lbl_metrics_bottom.pack(side=tk.LEFT, padx=(30, 0))

        # 动态绑定颜色 (针对状态消息)
        self.root.bind_all("<<UpdateStatusColor>>", lambda e: self.lbl_status.config(fg=self.status_color.get()))

        # 1. 侧边栏
        sidebar = tk.Frame(self.root, width=250, bg="#f0f0f0", padx=10, pady=10)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False) # 固定宽度

        # 根目录选择按钮
        # ttk.Button 样式通常跟随系统，但在标准浅色模式下通常是黑字
        btn_open = ttk.Button(sidebar, text="选择根文件夹", command=self.select_root_folder)
        btn_open.pack(fill=tk.X, pady=(0, 10))

        # 文件夹列表
        lbl_list = tk.Label(sidebar, textvariable=self.case_list_title, bg="#f0f0f0", fg="black", anchor="w")
        lbl_list.pack(fill=tk.X)
        self.case_listbox = tk.Listbox(sidebar, selectmode=tk.SINGLE, fg="black", bg="white")
        self.case_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.case_listbox.bind('<<ListboxSelect>>', self.load_selected_case)

        # 控制区
        ctrl_frame = tk.LabelFrame(sidebar, text="显示控制", bg="#f0f0f0", fg="black", padx=5, pady=5)
        ctrl_frame.pack(fill=tk.X, pady=10)

        # Gamma 滑动条
        tk.Label(ctrl_frame, text="Gamma 校正:", bg="#f0f0f0", fg="black").pack(anchor="w")
        scale_gamma = tk.Scale(ctrl_frame, from_=0.1, to=3.0, resolution=0.1, 
                               orient=tk.HORIZONTAL, variable=self.gamma_val, 
                               bg="#f0f0f0", fg="black",
                               command=lambda x: self.update_display())
        scale_gamma.pack(fill=tk.X)

        # 复选框
        chk_pred = tk.Checkbutton(ctrl_frame, text="显示预测 (Pred)", variable=self.show_pred, 
                                  bg="#f0f0f0", fg="black", command=self.update_display)
        chk_pred.pack(anchor="w")
        chk_gt = tk.Checkbutton(ctrl_frame, text="显示真值 (GT)", variable=self.show_gt, 
                                bg="#f0f0f0", fg="black", command=self.update_display)
        chk_gt.pack(anchor="w")

        # 旋转按钮
        btn_rot = ttk.Button(ctrl_frame, text="旋转 90°", command=self.rotate_image)
        btn_rot.pack(fill=tk.X, pady=(5, 0))

        # 布局控制
        layout_frame = tk.LabelFrame(sidebar, text="窗口布局", bg="#f0f0f0", fg="black", padx=5, pady=5)
        layout_frame.pack(fill=tk.X, pady=10)
        
        rb_dual = tk.Radiobutton(layout_frame, text="双窗对比 (Dual)", variable=self.layout_mode, value="dual",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_dual.pack(anchor="w")
        
        rb_left = tk.Radiobutton(layout_frame, text="仅预测 (Pred Only)", variable=self.layout_mode, value="left",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_left.pack(anchor="w")
        
        self.rb_right = tk.Radiobutton(layout_frame, text="仅真值 (GT Only)", variable=self.layout_mode, value="right",
                                       bg="#f0f0f0", fg="black", command=self.update_display)
        self.rb_right.pack(anchor="w")

        self.rb_diff = tk.Radiobutton(layout_frame, text="差异分析 (Diff)", variable=self.layout_mode, value="diff",
                                      bg="#f0f0f0", fg="black", command=self.update_display, state=tk.DISABLED)
        self.rb_diff.pack(anchor="w")

        # 自适应窗口开关
        chk_autofit = tk.Checkbutton(layout_frame, text="自适应窗口大小", variable=self.auto_fit_window, 
                                     bg="#f0f0f0", fg="black", command=self.update_display)
        chk_autofit.pack(anchor="w", pady=(5, 0))

        # 切片控制
        slice_frame = tk.Frame(sidebar, bg="#f0f0f0")
        slice_frame.pack(fill=tk.X, pady=(20, 10))
        
        tk.Label(slice_frame, text="Slice Navigation:", bg="#f0f0f0", fg="black").pack(anchor="w")
        
        self.slice_scale = tk.Scale(slice_frame, from_=0, to=0, orient=tk.HORIZONTAL, 
                                    bg="#f0f0f0", fg="black", highlightthickness=0,
                                    command=self.on_slider_change)
        self.slice_scale.pack(fill=tk.X)
        
        self.lbl_slice_info = tk.Label(slice_frame, textvariable=self.slice_info_text, bg="#f0f0f0", fg="black", font=("Arial", 12, "bold"))
        self.lbl_slice_info.pack(anchor="c")

        # 评估指标
        lbl_metrics = tk.Label(sidebar, textvariable=self.metrics_text, bg="#f0f0f0", fg="black", justify=tk.LEFT, font=("Courier", 14, "bold"))
        lbl_metrics.pack(pady=10, fill=tk.X)

        # 2. 主显示区
        self.main_panel = tk.Frame(self.root, bg="white")
        self.main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        # 绑定大小改变事件
        self.main_panel.bind("<Configure>", self.on_resize)

        # 分为左右两块
        self.panel_left = tk.Label(self.main_panel, bg="#e0e0e0", text="MRI + Prediction", fg="black")
        self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        self.panel_right = tk.Label(self.main_panel, bg="#e0e0e0", text="MRI + Ground Truth", fg="black")
        self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)

        # 绑定鼠标滚轮事件 (Windows/Linux/Mac兼容)
        # Note: Linux 使用 Button-4/5, Windows/Mac 使用 MouseWheel
        self.panel_left.bind("<MouseWheel>", self.on_scroll)
        self.panel_left.bind("<Button-4>", self.on_scroll)
        self.panel_left.bind("<Button-5>", self.on_scroll)
        
        self.panel_right.bind("<MouseWheel>", self.on_scroll)
        self.panel_right.bind("<Button-4>", self.on_scroll)
        self.panel_right.bind("<Button-5>", self.on_scroll)

        # 绑定缩放和平移事件
        for panel in [self.panel_left, self.panel_right]:
            # 缩放: Ctrl + 滚轮 (Windows/Mac) / Ctrl + Button-4/5 (Linux)
            # Mac有些系统是 Command，这里先绑定 Control
            panel.bind("<Control-MouseWheel>", self.on_zoom)
            panel.bind("<Control-Button-4>", self.on_zoom)
            panel.bind("<Control-Button-5>", self.on_zoom)
            
            # 平移: 左键拖拽
            panel.bind("<ButtonPress-1>", self.on_pan_start)
            panel.bind("<B1-Motion>", self.on_pan_drag)


    def rotate_image(self):
        """顺时针旋转90度"""
        # np.rot90 默认 k=1 是逆时针90度
        # 我们想要顺时针，所以用 k=-1 (或者 k=3)
        self.rotation_k = (self.rotation_k - 1) % 4
        self.update_display()

    def select_root_folder(self):
        """选择根目录并扫描子文件夹"""
        default_dir = "/Volumes/Sandisk/WAIYUAN_DATA"
        path = filedialog.askdirectory(initialdir=default_dir)
        if not path:
            return
        
        # 1. 检查 imagesTr 是否存在
        images_tr_path = os.path.join(path, "imagesTr")
        if not os.path.exists(images_tr_path) or not os.path.isdir(images_tr_path):
            messagebox.showwarning("目录结构不符合要求", 
                                   "所选文件夹不符合规定！\n\n"
                                   "根目录下必须包含 'imagesTr' 文件夹。")
            self.status_msg.set("错误：根目录下未找到 'imagesTr' 文件夹")
            self.status_color.set("red")
            self.root.event_generate("<<UpdateStatusColor>>")
            return

        # 2. 检查可选文件夹
        self.root_dir = path
        
        pred_tr_path = os.path.join(path, "predictsTr")
        self.has_pred_folder = os.path.exists(pred_tr_path) and os.path.isdir(pred_tr_path)
        
        labels_tr_path = os.path.join(path, "labelsTr")
        self.has_gt_folder = os.path.exists(labels_tr_path) and os.path.isdir(labels_tr_path)

        # 3. 开始扫描
        self.scan_directories()

    def scan_directories(self):
        """扫描逻辑：基于 {name}_0000.nii.gz 规则查找"""
        self.valid_cases = []
        self.case_listbox.delete(0, tk.END)
        
        images_dir = os.path.join(self.root_dir, "imagesTr")
        
        # 遍历 imagesTr
        try:
            for root, _, files in os.walk(images_dir):
                for f in files:
                    # 规则：必须以 _0000.nii.gz 结尾
                    if not f.endswith('_0000.nii.gz') or f.startswith('._'):
                        continue
                        
                    # 提取 Case Name
                    # 例如: Case10_0000.nii.gz -> Case10
                    case_name = f[:-12] 
                    if not case_name: # 避免空名
                        continue
                        
                    mri_path = os.path.join(root, f)
                    
                    # 查找 Pred
                    pred_path = None
                    if self.has_pred_folder:
                        # 预测文件应该是 {name}.nii.gz
                        p_name = f"{case_name}.nii.gz"
                        p_path = os.path.join(self.root_dir, "predictsTr", p_name)
                        if os.path.exists(p_path):
                            pred_path = p_path
                            
                    # 查找 GT
                    gt_path = None
                    if self.has_gt_folder:
                        # GT文件应该是 {name}.nii.gz
                        g_name = f"{case_name}.nii.gz"
                        g_path = os.path.join(self.root_dir, "labelsTr", g_name)
                        if os.path.exists(g_path):
                            gt_path = g_path
                            
                    case_info = {
                        'name': case_name,
                        'mri_path': mri_path,
                        'pred_path': pred_path,
                        'gt_path': gt_path
                    }
                    self.valid_cases.append(case_info)

        except Exception as e:
            messagebox.showerror("扫描错误", f"扫描过程中发生错误: {e}")
            return

        # 按名称排序 (自然排序可能更好，但这里先用字典序)
        self.valid_cases.sort(key=lambda x: x['name'])
        
        # 更新数量显示
        self.case_list_title.set(f"病例列表 ({len(self.valid_cases)}):")
        
        # 添加到列表框
        for case in self.valid_cases:
            self.case_listbox.insert(tk.END, case['name'])

        if not self.valid_cases:
            messagebox.showinfo("提示", "在 imagesTr 中未找到符合 *_0000.nii.gz 规则的文件。")
            self.status_msg.set("未找到符合规则的图像文件")
            self.status_color.set("red")
        else:
            msg = f"扫描完成，找到 {len(self.valid_cases)} 个病例。"
            if not self.has_pred_folder:
                msg += " (未检测到 predictsTr)"
            if not self.has_gt_folder:
                msg += " (未检测到 labelsTr)"
            self.status_msg.set(msg)
            self.status_color.set("green")
        
        self.root.event_generate("<<UpdateStatusColor>>")

    def load_selected_case(self, event):
        """加载选中的病例数据"""
        selection = self.case_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        case = self.valid_cases[index]

        # --- 检查并提示缺失文件 ---
        missing_files = []
        if self.has_pred_folder and case['pred_path'] is None:
            missing_files.append("预测")
        if self.has_gt_folder and case['gt_path'] is None:
            missing_files.append("GT")
            
        if missing_files:
            msg = f"警告 ({case['name']}): 未找到对应的 {' 和 '.join(missing_files)} 文件"
            self.status_msg.set(msg)
            self.status_color.set("red")
        else:
            self.status_msg.set(f"成功加载: {case['name']}")
            self.status_color.set("green") # 使用深绿色看起来更舒适，或者默认绿色
        self.root.event_generate("<<UpdateStatusColor>>")

        try:
            # 加载 MRI
            mri_img = nib.load(case['mri_path'])
            # 转换为 RAS 标准方向，确保切片顺序 (Inferior -> Superior) 与 Slicer 等软件一致
            mri_img = nib.as_closest_canonical(mri_img)
            mri_data = mri_img.get_fdata()
            
            # 处理 3D vs 4D 数据
            if mri_data.ndim == 4:
                mri_data = mri_data[..., 0] 
            
            # 加载 Pred (可能不存在)
            pred_data = None
            if case['pred_path']:
                pred_img = nib.load(case['pred_path'])
                pred_img = nib.as_closest_canonical(pred_img)
                pred_data = pred_img.get_fdata().astype(np.int8)

            # 加载 GT (如果存在)
            gt_data = None
            if case['gt_path']:
                gt_img = nib.load(case['gt_path'])
                gt_img = nib.as_closest_canonical(gt_img)
                gt_data = gt_img.get_fdata().astype(np.int8)

            # 检查维度一致性
            if pred_data is not None and mri_data.shape != pred_data.shape:
                raise ValueError(f"MRI维度 {mri_data.shape} 与 Pred维度 {pred_data.shape} 不匹配")
            
            if gt_data is not None and mri_data.shape != gt_data.shape:
                raise ValueError(f"MRI维度 {mri_data.shape} 与 GT维度 {gt_data.shape} 不匹配")

            # --- 计算全局归一化参数 ---
            # 使用全局统计量进行归一化，避免不同 Slice 亮度跳变
            # 简单下采样以加速统计
            try:
                sample_data = mri_data[::2, ::2, ::2]
                g_min = np.percentile(sample_data, 0.5) 
                g_max = np.percentile(sample_data, 99.5)
            except Exception:
                g_min = np.min(mri_data)
                g_max = np.max(mri_data)

            if g_max <= g_min:
                g_max = g_min + 1

            # 存储数据
            self.current_case_data = {
                'mri': mri_data,
                'pred': pred_data,
                'gt': gt_data,
                'global_min': g_min,
                'global_max': g_max
            }

            # 计算指标 & UI状态
            if pred_data is not None and gt_data is not None:
                d1, i1, d2, i2 = self.calculate_metrics(pred_data, gt_data)
                
                # 更新侧边栏 (详细)
                msg_full = (f"Label 1:\n  Dice: {d1:.4f}\n  IoU : {i1:.4f}\n\n"
                            f"Label 2:\n  Dice: {d2:.4f}\n  IoU : {i2:.4f}")
                self.metrics_text.set(msg_full)
                
                # 更新底部状态栏 (简略)
                msg_short = f"Dice1:{d1:.3f} Dice2:{d2:.3f} | IoU1:{i1:.3f} IoU2:{i2:.3f}"
                self.status_metrics_msg.set(msg_short)
                self.lbl_metrics_bottom.config(fg="blue") # 设置为蓝色区分
                
                # 功能全开
                self.rb_diff.config(state=tk.NORMAL)
                self.rb_right.config(state=tk.NORMAL)
            else:
                # 缺失 Pred 或 GT，部分功能禁用
                if pred_data is None:
                    self.metrics_text.set("No Prediction Data")
                    self.status_metrics_msg.set("No Pred")
                else:
                    self.metrics_text.set("No Ground Truth")
                    self.status_metrics_msg.set("No GT")
                
                self.lbl_metrics_bottom.config(fg="gray") # 灰色表示无效
                
                # 禁用差异分析
                self.rb_diff.config(state=tk.DISABLED)
                
                # 如果没有GT，禁用GT查看; 否则启用
                if gt_data is None:
                    self.rb_right.config(state=tk.DISABLED)
                else:
                    self.rb_right.config(state=tk.NORMAL)
                
                # 如果当前处于不可用模式(例如Diff)，强制切回左图
                if self.layout_mode.get() == "diff" or (self.layout_mode.get() == "right" and gt_data is None):
                     self.layout_mode.set("left")

            # 重置切片索引到中间
            self.total_slices = mri_data.shape[2]
            self.current_slice_index = self.total_slices // 2
            
            # 更新滑动条
            self.slice_scale.config(to=self.total_slices - 1)
            self.slice_scale.set(self.current_slice_index)
            
            self.update_display()

        except Exception as e:
            messagebox.showerror("加载错误", f"无法加载文件: {str(e)}")
            self.current_case_data = {}
            self.metrics_text.set("")
            self.status_metrics_msg.set("")
            self.panel_left.config(image='', text="Error")
            self.panel_right.config(image='', text="Error")

    def calculate_metrics(self, pred, gt):
        """计算 Label 1 和 2 的 Dice 和 IoU"""
        def compute_dice_iou(p, g, label):
            p_mask = (p == label)
            g_mask = (g == label)
            
            intersection = np.logical_and(p_mask, g_mask).sum()
            union = np.logical_or(p_mask, g_mask).sum()
            sum_masks = p_mask.sum() + g_mask.sum()
            
            # Dice
            dice = 1.0 if sum_masks == 0 else 2.0 * intersection / sum_masks
            # IoU
            iou = 1.0 if union == 0 else intersection / union
                
            return dice, iou

        d1, i1 = compute_dice_iou(pred, gt, 1)
        d2, i2 = compute_dice_iou(pred, gt, 2)
        return d1, i1, d2, i2

    def normalize_mri(self, slice_data):
        """将MRI切片归一化到 0-255 并进行 Gamma 变换"""
        if slice_data is None:
            return None
            
        # 使用全局统计量，如果不存在则退化为局部统计量
        g_min = self.current_case_data.get('global_min', slice_data.min())
        g_max = self.current_case_data.get('global_max', slice_data.max())
        
        # 截断数据到全局范围内
        slice_data = np.clip(slice_data, g_min, g_max)
        
        if g_max == g_min:
            return np.zeros_like(slice_data, dtype=np.uint8)
        
        # 线性归一化到 0-255
        norm = (slice_data - g_min) / (g_max - g_min) * 255
        
        # Gamma 变换
        gamma = self.gamma_val.get()
        # 防止除以0或溢出，先归一化回0-1计算gamma再乘255
        norm = 255 * np.power(norm / 255, 1.0 / gamma)
        
        return norm.astype(np.uint8)

    def get_slice_view(self, data, idx):
        """提取切片并转换为 Radiological 视图 (Ant-Top, Right-Left)"""
        if data is None:
            return None
        
        # 原始数据 (RAS): Dim 0 = L->R, Dim 1 = P->A
        raw_slice = data[:, :, idx]
        
        # 转换为 Radiological View:
        # 目标: Rows = A->P (Top=Ant), Cols = R->L (Left=Right)
        
        # 1. Transpose: (X, Y) -> (Y, X) => Rows: P->A, Cols: L->R
        # 2. Flip Both: Rows: A->P, Cols: R->L
        slice_radio = raw_slice.T[::-1, ::-1]
        
        # 应用用户旋转
        if self.rotation_k != 0:
            slice_radio = np.rot90(slice_radio, k=self.rotation_k)
            
        return slice_radio

    def create_overlay(self, mri_slice, mask_slice, color_mask_enabled=True):
        """
        创建叠加图像
        :param mri_slice: 2D numpy array (MRI values)
        :param mask_slice: 2D numpy array (Label values 0, 1, 2)
        :param color_mask_enabled: bool, 是否显示颜色叠加
        """
        if mri_slice is None:
            return None
            
        # 1. 准备底图 MRI -> RGBA
        mri_norm = self.normalize_mri(mri_slice)
        # 将灰度转为 RGBA
        img_pil = Image.fromarray(mri_norm).convert("RGBA")

        if not color_mask_enabled or mask_slice is None:
            return img_pil

        # 2. 准备 Mask 层
        # 创建一个全透明的 RGBA 图像
        # overlay = Image.new("RGBA", img_pil.size, (0, 0, 0, 0)) # Unused
        # width, height = img_pil.size # Unused
        
        # 我们使用 numpy 快速操作而不是逐像素遍历
        # mask_slice.T 是因为 image.fromarray 默认行是高度
        # 这里为了简化，我们先生成 numpy RGBA 数组
        
        rgba_mask = np.zeros((mri_slice.shape[0], mri_slice.shape[1], 4), dtype=np.uint8)
        
        # Label 1: 透明黄色 (255, 255, 0, alpha=76)  (76 ≈ 0.3 * 255)
        rgba_mask[mask_slice == 1] = [0, 255, 0, 76]
        
        # Label 2: 透明绿色 (0, 255, 0, alpha=76)
        rgba_mask[mask_slice == 2] = [255, 255, 0, 76] 

        # 转换为 PIL Overlay
        mask_layer = Image.fromarray(rgba_mask, mode="RGBA")

        # 3. 混合
        # alpha_composite 需要两张图都是 RGBA
        combined = Image.alpha_composite(img_pil, mask_layer)
        return combined

    def create_diff_overlay(self, mri_slice, pred_slice, gt_slice):
        """
        创建差异分析图
        Green系: Label 1 (FP=亮绿, FN=暗绿)
        Yellow系: Label 2 (FP=亮黄, FN=暗橙黄)
        """
        mri_norm = self.normalize_mri(mri_slice)
        img_pil = Image.fromarray(mri_norm).convert("RGBA")
        
        if pred_slice is None or gt_slice is None:
            return img_pil
            
        rgba_mask = np.zeros((mri_slice.shape[0], mri_slice.shape[1], 4), dtype=np.uint8)
        
        # --- Label 1 (Green) ---
        # False Positive (多标): Pred=1, GT!=1 -> 亮绿色
        # RGBA: [0, 255, 0, 100]
        mask_fp_1 = (pred_slice == 1) & (gt_slice != 1)
        rgba_mask[mask_fp_1] = [0, 255, 0, 100]
        
        # False Negative (少标/漏标): Pred!=1, GT=1 -> 暗绿色 (ForestGreen)
        # RGBA: [34, 139, 34, 120]
        mask_fn_1 = (pred_slice != 1) & (gt_slice == 1)
        rgba_mask[mask_fn_1] = [34, 139, 34, 120] 

        # --- Label 2 (Yellow) ---
        # False Positive (多标): Pred=2, GT!=2 -> 亮黄色
        # RGBA: [255, 255, 0, 100]
        mask_fp_2 = (pred_slice == 2) & (gt_slice != 2)
        rgba_mask[mask_fp_2] = [255, 255, 0, 100]
        
        # False Negative (少标/漏标): Pred!=2, GT=2 -> 暗橙色 (DarkOrange)
        # RGBA: [255, 140, 0, 120]
        mask_fn_2 = (pred_slice != 2) & (gt_slice == 2)
        rgba_mask[mask_fn_2] = [255, 140, 0, 120]
        
        mask_layer = Image.fromarray(rgba_mask, mode="RGBA")
        return Image.alpha_composite(img_pil, mask_layer)

    def on_resize(self, event):
        """窗口大小改变时的回调"""
        # 只有在开启自适应且有数据加载时才自动刷新
        if self.auto_fit_window.get() and self.current_case_data:
            self.update_display()

    def process_zoom_pan(self, img_pil, display_constraints):
        """
        应用缩放和平移
        :param display_constraints: 
            int: 固定高度模式，值为 height
            tuple (w, h): 自适应模式，值为容器最大宽高
        """
        w, h = img_pil.size
        
        # 确保 zoom_level >= 1.0
        if self.zoom_level < 1.0:
            self.zoom_level = 1.0
            
        fov_w = w / self.zoom_level
        fov_h = h / self.zoom_level
        
        # 计算左上角位置
        left = (self.pan_center_x * w) - (fov_w / 2)
        top = (self.pan_center_y * h) - (fov_h / 2)
        
        # 边界限制 clamping
        # 确保不会超出图像边界
        if left < 0: left = 0
        if left + fov_w > w: left = w - fov_w
        
        if top < 0: top = 0
        if top + fov_h > h: top = h - fov_h
        
        # 更新实际中心点 (因为可能被Clamp移动了)
        self.pan_center_x = (left + fov_w / 2) / w
        self.pan_center_y = (top + fov_h / 2) / h
        
        # 裁剪
        crop_box = (left, top, left + fov_w, top + fov_h)
        img_crop = img_pil.crop(crop_box)
        
        # 计算目标显示尺寸
        aspect_ratio = w / h
        
        if isinstance(display_constraints, int):
            # 固定高度模式
            disp_h = display_constraints
            disp_w = int(disp_h * aspect_ratio)
        else:
            # 自适应模式 (max_w, max_h)
            max_w, max_h = display_constraints
            
            # 防止无效尺寸
            if max_w <= 10: max_w = 400
            if max_h <= 10: max_h = 400
            
            win_ratio = max_w / max_h
            if aspect_ratio > win_ratio:
                # 图片更宽，以宽为准 (contain)
                disp_w = max_w
                disp_h = int(max_w / aspect_ratio)
            else:
                # 图片更高，以高为准
                disp_h = max_h
                disp_w = int(max_h * aspect_ratio)
        
        img_final = img_crop.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.current_disp_size = (disp_w, disp_h)
        
        return img_final

    def update_display(self):
        """刷新双面板图像"""
        if not self.current_case_data:
            return

        idx = self.current_slice_index
        
        # 更新文本信息
        self.slice_info_text.set(f"Slice: {idx + 1} / {self.total_slices}")

        # 使用 helper 获取转换视角的切片
        mri_slice = self.get_slice_view(self.current_case_data['mri'], idx)
        pred_slice = self.get_slice_view(self.current_case_data.get('pred'), idx)
        gt_slice = self.get_slice_view(self.current_case_data.get('gt'), idx)

        # --- 布局与图像生成 ---
        mode = self.layout_mode.get()
        
        # 计算显示约束
        if self.auto_fit_window.get():
            # 获取主显示区的实时尺寸
            mw = self.main_panel.winfo_width()
            mh = self.main_panel.winfo_height()
            
            # 减去一点边距，避免撑爆
            mw = max(100, mw - 20)
            mh = max(100, mh - 20)
            
            if mode == "dual":
                display_constraints = (mw // 2, mh)
            else:
                display_constraints = (mw, mh)
        else:
            # 固定高度模式
            display_constraints = 512 if mode == "dual" else 750

        # 1. 重置布局 (防止残留)
        self.panel_left.pack_forget()
        self.panel_right.pack_forget()

        # 2. 根据模式 Pack
        if mode == "dual":
            self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)
        elif mode == "left" or mode == "diff":
            self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        elif mode == "right":
            self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)

        # 强制更新布局计算，防止渲染和变量延迟
        self.root.update_idletasks()

        # --- 生成左图 (MRI + Pred) OR (Diff Map) ---
        if mode in ["dual", "left"]:
            img_left_pil = self.create_overlay(mri_slice, pred_slice, self.show_pred.get())
            img_left_display = self.process_zoom_pan(img_left_pil, display_constraints)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")
        elif mode == "diff":
            # 差异图模式
            img_diff_pil = self.create_diff_overlay(mri_slice, pred_slice, gt_slice)
            img_left_display = self.process_zoom_pan(img_diff_pil, display_constraints)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")

        # --- 生成右图 (MRI + GT or Empty) ---
        if mode in ["dual", "right"]:
            if gt_slice is not None:
                img_right_pil = self.create_overlay(mri_slice, gt_slice, self.show_gt.get())
                img_right_display = self.process_zoom_pan(img_right_pil, display_constraints)
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")
            else:
                self.panel_right.config(image='', text="No Ground Truth Available")

    def on_scroll(self, event):
        """处理鼠标滚轮事件，实现双窗同步"""
        # 如果按下了 Control 键，则不进行切片切换 (避免与缩放冲突)
        if event.state & 0x0004: # Windows/Linux Control mask
             return
        # Mac Control is usually bit 2 or similar, keep simple for now
        # Mac default is different, but let's try to detect context or assume zoom handles its own.
        
        if not self.current_case_data:
            return

        # 跨平台滚轮处理
        if event.num == 5 or event.delta < 0:
            step = -1
        elif event.num == 4 or event.delta > 0:
            step = 1
        else:
            step = 0

        new_index = self.current_slice_index + step
        
        # 边界检查
        if 0 <= new_index < self.total_slices:
            self.current_slice_index = new_index
            self.slice_scale.set(new_index) # 同步更新滑动条
            self.update_display()

    def on_slider_change(self, val):
        """处理滑动条拖动"""
        if not self.current_case_data:
            return
            
        new_index = int(val)
        if new_index != self.current_slice_index:
            self.current_slice_index = new_index
            self.update_display()

    def on_zoom(self, event):
        """处理 Zoom (Ctrl + Wheel)"""
        if not self.current_case_data:
            return
            
        scale_factor = 1.1
        if event.num == 5 or event.delta < 0:
            # Zoom Out
            self.zoom_level /= scale_factor
        elif event.num == 4 or event.delta > 0:
            # Zoom In
            self.zoom_level *= scale_factor
            
        # 限制最小缩放
        if self.zoom_level < 1.0:
            self.zoom_level = 1.0
            
        self.update_display()

    def on_pan_start(self, event):
        """开始拖拽平移"""
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_pan_drag(self, event):
        """拖拽中"""
        if not self.current_case_data or not hasattr(self, 'current_disp_size'):
            return

        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        
        # 将屏幕像素偏移转换为相对坐标偏移
        # 注意: 拖拽方向与移动视野方向相反 (类似手机地图) -> 鼠标往左拖，视野向右看(中心点减小? 不，鼠标往左，图片往左，中心点变大)
        # 或者是: 拖拽图片。鼠标向右拖(dx > 0)，图片向右动，说明我们想看左边的内容。中心点 x 应减小。
        
        disp_w, disp_h = self.current_disp_size
        
        # 相对位移 = 像素位移 / 显示尺寸 / 缩放级别 (因为我们在Zoom后的图上操作)
        # 但实际上 process_zoom_pan 是基于 pan_center_x (0-1) 在原图上切 crop
        # FOV在原图上的宽度是 W / zoom.
        # 屏幕显示宽度是 disp_w.
        # 所以屏幕 1px 对应原图 (W / zoom) / disp_w 像素.
        # 转化为相对坐标 (0-1), 还需要除以 W.
        # relative_delta = (1 / zoom) * (dx / disp_w)
        
        rel_dx = (dx / disp_w) / self.zoom_level
        rel_dy = (dy / disp_h) / self.zoom_level
        
        # 鼠标向右拖 (dx>0)，我们希望图片向右移，也就意味着视野中心向左移
        self.pan_center_x -= rel_dx
        self.pan_center_y -= rel_dy
        
        # 记录新起点
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        
        self.update_display()

if __name__ == "__main__":
    root = tk.Tk()
    app = NiiViewerApp(root)
    root.mainloop()
