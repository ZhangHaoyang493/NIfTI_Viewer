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
        
        # 显示设置变量
        self.gamma_val = tk.DoubleVar(value=1.0)
        self.show_pred = tk.BooleanVar(value=True)
        self.show_gt = tk.BooleanVar(value=True)
        self.layout_mode = tk.StringVar(value="dual") # dual, left, right
        self.slice_info_text = tk.StringVar(value="Slice: 0 / 0")
        self.metrics_text = tk.StringVar(value="")

        # 缩放和平移状态
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
        # 1. 侧边栏
        sidebar = tk.Frame(self.root, width=250, bg="#f0f0f0", padx=10, pady=10)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False) # 固定宽度

        # 根目录选择按钮
        # ttk.Button 样式通常跟随系统，但在标准浅色模式下通常是黑字
        btn_open = ttk.Button(sidebar, text="选择根文件夹", command=self.select_root_folder)
        btn_open.pack(fill=tk.X, pady=(0, 10))

        # 文件夹列表
        lbl_list = tk.Label(sidebar, text="病例列表:", bg="#f0f0f0", fg="black", anchor="w")
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

        # 布局控制
        layout_frame = tk.LabelFrame(sidebar, text="窗口布局", bg="#f0f0f0", fg="black", padx=5, pady=5)
        layout_frame.pack(fill=tk.X, pady=10)
        
        rb_dual = tk.Radiobutton(layout_frame, text="双窗对比 (Dual)", variable=self.layout_mode, value="dual",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_dual.pack(anchor="w")
        
        rb_left = tk.Radiobutton(layout_frame, text="仅预测 (Pred Only)", variable=self.layout_mode, value="left",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_left.pack(anchor="w")
        
        rb_right = tk.Radiobutton(layout_frame, text="仅真值 (GT Only)", variable=self.layout_mode, value="right",
                                  bg="#f0f0f0", fg="black", command=self.update_display)
        rb_right.pack(anchor="w")

        self.rb_diff = tk.Radiobutton(layout_frame, text="差异分析 (Diff)", variable=self.layout_mode, value="diff",
                                      bg="#f0f0f0", fg="black", command=self.update_display, state=tk.DISABLED)
        self.rb_diff.pack(anchor="w")

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
        main_panel = tk.Frame(self.root, bg="white")
        main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 分为左右两块
        self.panel_left = tk.Label(main_panel, bg="#e0e0e0", text="MRI + Prediction", fg="black")
        self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        self.panel_right = tk.Label(main_panel, bg="#e0e0e0", text="MRI + Ground Truth", fg="black")
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

    def select_root_folder(self):
        """选择根目录并扫描子文件夹"""
        default_dir = os.path.expanduser("~/Desktop/WAIYUAN_DATA")
        path = filedialog.askdirectory(initialdir=default_dir)
        if not path:
            return
        
        self.root_dir = path
        self.scan_directories()

    def scan_directories(self):
        """扫描逻辑：查找符合 Case A 或 Case B 的文件夹"""
        self.valid_cases = []
        self.case_listbox.delete(0, tk.END)

        for root, dirs, files in os.walk(self.root_dir):
            # 获取当前文件夹下的所有nii.gz文件
            nii_files = [f for f in files if f.endswith('.nii.gz')]
            if not nii_files:
                continue

            pred_file = None
            gt_file = None
            mri_file = None

            # 简单的文件名匹配逻辑
            for f in nii_files:
                if 'pred' in f:
                    pred_file = os.path.join(root, f)
                elif 'gt' in f:
                    gt_file = os.path.join(root, f)
                else:
                    # 假设非pred非gt就是原图 (实际项目中可能需要更严格的规则)
                    mri_file = os.path.join(root, f)

            # 校验规则
            # 必须有 MRI 和 Pred
            if mri_file and pred_file:
                case_info = {
                    'name': os.path.basename(root),
                    'mri_path': mri_file,
                    'pred_path': pred_file,
                    'gt_path': gt_file # Case A时为None，Case B时有值
                }
                self.valid_cases.append(case_info)

        # 按名称排序
        self.valid_cases.sort(key=lambda x: x['name'])
        
        # 添加到列表框
        for case in self.valid_cases:
            self.case_listbox.insert(tk.END, case['name'])

        if not self.valid_cases:
            messagebox.showinfo("提示", "未找到符合要求的病例文件夹。")

    def load_selected_case(self, event):
        """加载选中的病例数据"""
        selection = self.case_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        case = self.valid_cases[index]

        try:
            # 加载 MRI
            mri_img = nib.load(case['mri_path'])
            mri_data = mri_img.get_fdata()
            # 确保是标准方向 (RAS)，这里简单处理，实际可能需要 as_closest_canonical
            # 并且处理 3D vs 4D 数据
            if mri_data.ndim == 4:
                mri_data = mri_data[..., 0] 
            
            # 加载 Pred
            pred_img = nib.load(case['pred_path'])
            pred_data = pred_img.get_fdata().astype(np.int8)

            # 加载 GT (如果存在)
            gt_data = None
            if case['gt_path']:
                gt_img = nib.load(case['gt_path'])
                gt_data = gt_img.get_fdata().astype(np.int8)

            # 检查维度一致性
            if mri_data.shape != pred_data.shape:
                raise ValueError(f"MRI维度 {mri_data.shape} 与 Pred维度 {pred_data.shape} 不匹配")
            
            if gt_data is not None and mri_data.shape != gt_data.shape:
                raise ValueError(f"MRI维度 {mri_data.shape} 与 GT维度 {gt_data.shape} 不匹配")

            # 存储数据
            self.current_case_data = {
                'mri': mri_data,
                'pred': pred_data,
                'gt': gt_data
            }

            # 计算指标
            if gt_data is not None:
                d1, i1, d2, i2 = self.calculate_metrics(pred_data, gt_data)
                msg = (f"Label 1:\n  Dice: {d1:.4f}\n  IoU : {i1:.4f}\n\n"
                       f"Label 2:\n  Dice: {d2:.4f}\n  IoU : {i2:.4f}")
                self.metrics_text.set(msg)
                
                # 启用差异分析
                self.rb_diff.config(state=tk.NORMAL)
            else:
                self.metrics_text.set("No Ground Truth")
                
                # 禁用差异分析并重置模式
                self.rb_diff.config(state=tk.DISABLED)
                if self.layout_mode.get() == "diff":
                    self.layout_mode.set("dual")

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
        if slice_data.max() == slice_data.min():
            return np.zeros_like(slice_data, dtype=np.uint8)
        
        # 线性归一化到 0-255
        norm = (slice_data - slice_data.min()) / (slice_data.max() - slice_data.min()) * 255
        
        # Gamma 变换
        gamma = self.gamma_val.get()
        # 防止除以0或溢出，先归一化回0-1计算gamma再乘255
        norm = 255 * np.power(norm / 255, 1.0 / gamma)
        
        return norm.astype(np.uint8)

    def create_overlay(self, mri_slice, mask_slice, color_mask_enabled=True):
        """
        创建叠加图像
        :param mri_slice: 2D numpy array (MRI values)
        :param mask_slice: 2D numpy array (Label values 0, 1, 2)
        :param color_mask_enabled: bool, 是否显示颜色叠加
        """
        # 1. 准备底图 MRI -> RGBA
        mri_norm = self.normalize_mri(mri_slice)
        # 将灰度转为 RGBA
        img_pil = Image.fromarray(mri_norm).convert("RGBA")

        if not color_mask_enabled or mask_slice is None:
            return img_pil

        # 2. 准备 Mask 层
        # 创建一个全透明的 RGBA 图像
        overlay = Image.new("RGBA", img_pil.size, (0, 0, 0, 0))
        width, height = img_pil.size
        
        # 我们使用 numpy 快速操作而不是逐像素遍历
        # 注意: PIL Image 和 numpy 数组的坐标系转换 (W, H) vs (H, W)
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

    def process_zoom_pan(self, img_pil, base_height):
        """应用缩放和平移"""
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
        
        # 计算目标显示尺寸 (保持与原图相同的长宽比，高度固定为 base_height)
        # 这样无论缩放多少倍，显示在屏幕上的物理尺寸不变，从而达到放大的视觉效果
        aspect_ratio = w / h
        disp_h = base_height
        disp_w = int(base_height * aspect_ratio)
        
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

        # 获取当前切片数据 (Axial view: [:, :, idx])
        # 不进行旋转，直接使用原始方向
        mri_slice = self.current_case_data['mri'][:, :, idx]
        pred_slice = self.current_case_data['pred'][:, :, idx]
        
        gt_slice = None
        if self.current_case_data['gt'] is not None:
            gt_slice = self.current_case_data['gt'][:, :, idx]

        # --- 布局与图像生成 ---
        mode = self.layout_mode.get()
        base_height = 512 if mode == "dual" else 750  # 单窗时放大
        
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
            img_left_display = self.process_zoom_pan(img_left_pil, base_height)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")
        elif mode == "diff":
            # 差异图模式
            img_diff_pil = self.create_diff_overlay(mri_slice, pred_slice, gt_slice)
            img_left_display = self.process_zoom_pan(img_diff_pil, base_height)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")

        # --- 生成右图 (MRI + GT or Empty) ---
        if mode in ["dual", "right"]:
            if gt_slice is not None:
                img_right_pil = self.create_overlay(mri_slice, gt_slice, self.show_gt.get())
                img_right_display = self.process_zoom_pan(img_right_pil, base_height)
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
