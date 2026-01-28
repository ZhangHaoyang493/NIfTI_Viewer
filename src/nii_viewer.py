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
        self.auto_fit_window = tk.BooleanVar(value=True) # 新增自适应变量
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

        # 编辑功能变量
        self.edit_mode = tk.BooleanVar(value=False)
        self.current_tool = tk.StringVar(value="pen") # pen, eraser, wand
        self.edit_label_val = tk.IntVar(value=1) # 1 or 2
        self.brush_size = tk.IntVar(value=1)
        self.wand_tolerance = tk.IntVar(value=5)
        self.undo_stack = [] # List[Tuple(slice_idx, slice_data_copy)]
        self.last_export_dir = os.path.expanduser("~")
        self.editable_mask = None # 3D numpy array
        self.edit_source = None # 'gt', 'pred', 'blank'
        self.is_drawing = False
        self.preview_cursor_pos = None # (x, y) internal image coordinates
        self.previous_layout_mode = None

        # 防止图片被垃圾回收
        self.tk_img_left = None
        self.tk_img_right = None

        # --- UI 布局 ---
        self._setup_ui()

    def _setup_ui(self):
        """配置界面布局"""
        # --- 顶部工具栏 (编辑工具) ---
        toolbar = tk.Frame(self.root, bg="#e0e0e0", height=40)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # Edit Toggle
        chk_edit = tk.Checkbutton(toolbar, text="开启编辑模式", variable=self.edit_mode, 
                                  bg="#e0e0e0", fg="black", command=self.toggle_edit_mode)
        chk_edit.pack(side=tk.LEFT, padx=10)
        
        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Tools
        self.tool_frame = tk.Frame(toolbar, bg="#e0e0e0")
        self.tool_frame.pack(side=tk.LEFT)
        
        tk.Label(self.tool_frame, text="工具:", bg="#e0e0e0", fg="black").pack(side=tk.LEFT, padx=5)
        
        rb_pen = tk.Radiobutton(self.tool_frame, text="画笔", variable=self.current_tool, value="pen", bg="#e0e0e0", fg="black")
        rb_pen.pack(side=tk.LEFT)
        
        rb_erase = tk.Radiobutton(self.tool_frame, text="橡皮擦", variable=self.current_tool, value="eraser", bg="#e0e0e0", fg="black")
        rb_erase.pack(side=tk.LEFT)
        
        rb_wand = tk.Radiobutton(self.tool_frame, text="魔棒", variable=self.current_tool, value="wand", bg="#e0e0e0", fg="black")
        rb_wand.pack(side=tk.LEFT)
        
        # Label Value
        tk.Label(self.tool_frame, text="| 标签值:", bg="#e0e0e0", fg="black").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(self.tool_frame, text="Label 1", variable=self.edit_label_val, value=1, bg="#e0e0e0", fg="black").pack(side=tk.LEFT)
        tk.Radiobutton(self.tool_frame, text="Label 2", variable=self.edit_label_val, value=2, bg="#e0e0e0", fg="black").pack(side=tk.LEFT)
        
        # Settings - Brush
        tk.Label(self.tool_frame, text="| 笔刷大小:", bg="#e0e0e0", fg="black").pack(side=tk.LEFT, padx=(10, 2))
        tk.Scale(self.tool_frame, from_=1, to=10, variable=self.brush_size, orient=tk.HORIZONTAL, length=80, bg="#e0e0e0", fg="black", highlightthickness=0).pack(side=tk.LEFT)
        
        # Settings - Wand
        tk.Label(self.tool_frame, text="| 魔棒阈值:", bg="#e0e0e0", fg="black").pack(side=tk.LEFT, padx=(10, 2))
        spin_wand = ttk.Spinbox(self.tool_frame, from_=0, to=100, textvariable=self.wand_tolerance, width=3)
        spin_wand.pack(side=tk.LEFT, padx=2)
        
        # Actions
        # 使用 ttk.Button 以获得更干净的外观（去除可能的黑色背景）
        ttk.Button(self.tool_frame, text="撤销 (Ctrl+Z)", command=self.undo_action).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(self.tool_frame, text="导出 Label", command=self.export_label).pack(side=tk.LEFT, padx=5)

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
        self.chk_gt = tk.Checkbutton(ctrl_frame, text="显示真值 (GT)", variable=self.show_gt, 
                                bg="#f0f0f0", fg="black", command=self.update_display)
        self.chk_gt.pack(anchor="w")

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
            
            # 平移: 左键拖拽 (非编辑模式) 或 右键拖拽 (编辑模式)
            panel.bind("<ButtonPress-1>", self.on_mouse_down)
            panel.bind("<B1-Motion>", self.on_mouse_drag)
            panel.bind("<ButtonRelease-1>", self.on_mouse_up)
            
            # 中键平移 (编辑模式专用)
            panel.bind("<ButtonPress-2>", self.on_pan_start)
            panel.bind("<B2-Motion>", self.on_pan_drag)
            panel.bind("<ButtonRelease-2>", self.on_pan_end)
            
            # 鼠标移动 (用于预览)
            panel.bind("<Motion>", self.on_mouse_move)
            panel.bind("<Leave>", self.on_mouse_leave)
            
        # 绑定 Undo 快捷键
        self.root.bind("<Control-z>", lambda e: self.undo_action())
        self.root.bind("<Command-z>", lambda e: self.undo_action()) # Mac Support

        # 初始化工具栏状态 (必须在 UI 元素创建完成后调用)
        self.toggle_edit_mode()

    def toggle_edit_mode(self):
        """切换编辑模式状态"""
        is_editing = self.edit_mode.get()
        # 启用/禁用工具栏控件
        state = tk.NORMAL if is_editing else tk.DISABLED
        for child in self.tool_frame.winfo_children():
            try:
                child.configure(state=state)
            except:
                pass 
        
        # 切换布局：如果进入编辑模式，强制显示 Editor (Right Panel)
        if is_editing:
            # 保存当前布局模式
            self.previous_layout_mode = self.layout_mode.get()
            # 自动切换到右侧编辑窗口
            self.layout_mode.set("right")
            self.rb_right.config(state=tk.NORMAL, text="编辑器 (Right)")
            
            # 如果editable_mask未初始化，则根据优先级设置
            if self.editable_mask is None and self.current_case_data:
                gt_data = self.current_case_data.get('gt')
                pred_data = self.current_case_data.get('pred')
                mri_data = self.current_case_data['mri']
                if gt_data is not None:
                    self.editable_mask = gt_data.copy()
                    self.edit_source = 'gt'
                elif pred_data is not None:
                    self.editable_mask = pred_data.copy()
                    self.edit_source = 'pred'
                else:
                    self.editable_mask = np.zeros_like(mri_data, dtype=np.int8)
                    self.edit_source = 'blank'
            else:
                # editable_mask已存在，使用已记录的来源
                pass
            
            # 更新状态栏显示编辑来源
            source_text = {
                'gt': 'GT标签',
                'pred': '模型预测', 
                'blank': '原图'
            }.get(self.edit_source, '未知')
            self.status_metrics_msg.set(f"编辑基于: {source_text}")
            self.lbl_metrics_bottom.config(fg="blue")
        else:
            # 退出编辑模式，恢复之前的布局
            if self.previous_layout_mode:
                self.layout_mode.set(self.previous_layout_mode)
                self.previous_layout_mode = None
            self.rb_right.config(text="仅真值 (GT Only)")
            
            # 如果没有GT，禁用GT查看; 否则启用
            if self.current_case_data and self.current_case_data.get('gt') is None:
                self.rb_right.config(state=tk.DISABLED)
                self.chk_gt.config(state=tk.DISABLED)
            else:
                self.rb_right.config(state=tk.NORMAL)
                self.chk_gt.config(state=tk.NORMAL)
            
            # 清除编辑状态信息
            self.status_metrics_msg.set("")
            self.lbl_metrics_bottom.config(fg="gray")
            
        self.update_display()


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

        # --- 重置状态: 退出编辑，默认双窗，清空显示 ---
        self.current_case_data = {}
        
        if self.edit_mode.get():
            self.edit_mode.set(False)
            self.toggle_edit_mode()
            
        self.layout_mode.set("dual")
        
        # 清空图像和文本
        self.tk_img_left = None
        self.tk_img_right = None
        self.panel_left.config(image='', text="MRI + Prediction")
        self.panel_right.config(image='', text="MRI + Ground Truth")
        
        # 恢复默认双窗布局
        self.panel_left.pack_forget()
        self.panel_right.pack_forget()
        self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)
        
        # 清空指标和Info
        self.metrics_text.set("")
        self.status_metrics_msg.set("")
        self.lbl_metrics_bottom.config(fg="gray")
        self.slice_info_text.set("Slice: 0 / 0")
        self.slice_scale.config(to=0)
        self.slice_scale.set(0)
        
        # 启用相关按钮 (等待加载新病例时再决定禁用与否)
        self.chk_gt.config(state=tk.NORMAL)
        self.rb_right.config(state=tk.NORMAL)
        self.rb_diff.config(state=tk.DISABLED) # Diff 默认禁用直到加载数据

        # 2. 检查可选文件夹
        self.root_dir = path
        self.checked_export_dir = False # 重置导出文件夹检查状态
        
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
                self.chk_gt.config(state=tk.NORMAL)
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
                    self.chk_gt.config(state=tk.DISABLED)
                else:
                    self.rb_right.config(state=tk.NORMAL)
                    self.chk_gt.config(state=tk.NORMAL)
                
                # 如果当前处于不可用模式(例如Diff)，强制切回左图
                if self.layout_mode.get() == "diff" or (self.layout_mode.get() == "right" and gt_data is None):
                     self.layout_mode.set("left")

            # --- 初始化编辑 Mask ---
            # 优先使用 GT，如果没有则使用 Pred，再没有则全0
            if gt_data is not None:
                self.editable_mask = gt_data.copy()
                self.edit_source = 'gt'
            elif pred_data is not None:
                self.editable_mask = pred_data.copy()
                self.edit_source = 'pred'
            else:
                self.editable_mask = np.zeros_like(mri_data, dtype=np.int8)
                self.edit_source = 'blank'
            
            self.undo_stack.clear() # 清空撤销栈

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

    def create_overlay(self, mri_slice, mask_slice, color_mask_enabled=True, preview_mask=None, preview_val=1):
        """
        创建叠加图像
        :param mri_slice: 2D numpy array (MRI values)
        :param mask_slice: 2D numpy array (Label values 0, 1, 2)
        :param color_mask_enabled: bool
        :param preview_mask: 2D boolean array (Preview mask)
        :param preview_val: int (Label value for preview)
        """
        if mri_slice is None:
            return None
            
        # 1. 准备底图 MRI -> RGBA
        mri_norm = self.normalize_mri(mri_slice)
        # 将灰度转为 RGBA
        img_pil = Image.fromarray(mri_norm).convert("RGBA")

        # 2. 准备 Mask 层 (包含已有 Label 和 预览)
        if (not color_mask_enabled or mask_slice is None) and preview_mask is None:
            return img_pil

        rgba_mask = np.zeros((mri_slice.shape[0], mri_slice.shape[1], 4), dtype=np.uint8)
        
        # 绘制已有 Label
        if color_mask_enabled and mask_slice is not None:
            # Label 1: 透明绿
            rgba_mask[mask_slice == 1] = [0, 255, 0, 76]
            # Label 2: 透明黄
            rgba_mask[mask_slice == 2] = [255, 255, 0, 76] 

        # 绘制预览 Label (覆盖在上面)
        if preview_mask is not None:
             # 设置预览颜色，稍微不透明一点以便区分，或者加个边框效果(这里简单处理)
             # Label 1: 亮绿 [0, 255, 0, 150]
             # Label 2: 亮黄 [255, 255, 0, 150]
             # Eraser (val=0): 红色或者是擦除效果? 
             # 如果是橡皮擦，preview_val应为0，我们可以显示红色半透明表示即将被擦除的区域
             
             if preview_val == 1:
                 color = [0, 255, 0, 160]
             elif preview_val == 2:
                 color = [255, 255, 0, 160]
             else: # Eraser / 0
                 color = [255, 0, 0, 128] # 红色示警
                 
             rgba_mask[preview_mask] = color

        # 转换为 PIL Overlay
        mask_layer = Image.fromarray(rgba_mask, mode="RGBA")

        # 3. 混合
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
        
        img_final = img_crop.resize((disp_w, disp_h), Image.Resampling.NEAREST)
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

        # --- 生成右图 (MRI + GT or Empty or Edited) ---
        if mode in ["dual", "right"]:
            # 如果在编辑模式，优先显示 editable_mask
            if self.edit_mode.get() and self.editable_mask is not None:
                # 获取切片视图，确保方向正确
                mask_slice = self.get_slice_view(self.editable_mask, idx)
                
                # 生成预览 Mask
                preview_mask = None
                preview_val = 1
                if self.preview_cursor_pos:
                    px, py = self.preview_cursor_pos
                    # 获取 MRI slice view 用于 wand 计算 (如果需要)
                    # 注意: get_tool_mask 需要的是 view 坐标系下的数据
                    # mri_slice 已经是 view
                    preview_mask = self.get_tool_mask(self.current_tool.get(), px, py, mri_slice)
                    preview_val = self.edit_label_val.get() if self.current_tool.get() != "eraser" else 0
                
                img_right_pil = self.create_overlay(mri_slice, mask_slice, self.show_gt.get(), preview_mask, preview_val)
                img_right_display = self.process_zoom_pan(img_right_pil, display_constraints)
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")
            elif gt_slice is not None:
                img_right_pil = self.create_overlay(mri_slice, gt_slice, self.show_gt.get())
                img_right_display = self.process_zoom_pan(img_right_pil, display_constraints)
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")
            else:
                img_right_pil = self.create_overlay(mri_slice, None, False)
                img_right_display = self.process_zoom_pan(img_right_pil, display_constraints)
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")

    def screen_to_image_coords(self, sx, sy, img_w, img_h):
        """将屏幕坐标转换为 Slice 图像坐标"""
        if not hasattr(self, 'current_disp_size') or not self.current_disp_size:
             return 0, 0
             
        disp_w, disp_h = self.current_disp_size
        
        # 获取 Panel 尺寸来计算居中偏移 (Tkinter Label 默认居中显示图像)
        # 这里使用 panel_right 的尺寸，因为编辑主要在右侧进行
        # 如果将来需要在左侧编辑，需要传入 widget 参数区分
        p_w = self.panel_right.winfo_width()
        p_h = self.panel_right.winfo_height()
        
        off_x = (p_w - disp_w) // 2
        off_y = (p_h - disp_h) // 2
        
        # 修正屏幕坐标到图像显示区域坐标
        sx_adj = sx - off_x
        sy_adj = sy - off_y
        
        # 1. 反转 Zoom/Pan 裁剪
        # process_zoom_pan 逻辑:
        # fov_w = w / zoom
        # left = center_x * w - fov/2
        # crop_x = left + (sx / disp_w) * fov_w
        
        fov_w = img_w / self.zoom_level
        fov_h = img_h / self.zoom_level
        
        left = (self.pan_center_x * img_w) - (fov_w / 2)
        top = (self.pan_center_y * img_h) - (fov_h / 2)
        
        # Clamp
        if left < 0: left = 0
        if left + fov_w > img_w: left = img_w - fov_w
        if top < 0: top = 0
        if top + fov_h > img_h: top = img_h - fov_h
        
        rel_x = sx_adj / disp_w
        rel_y = sy_adj / disp_h
        
        img_x = left + (rel_x * fov_w)
        img_y = top + (rel_y * fov_h)
        
        return int(img_x), int(img_y)

    def on_mouse_move(self, event):
        """处理鼠标移动 (用于预览)"""
        if not self.edit_mode.get() or self.editable_mask is None:
            return
        
        # 仅在右侧面板处理预览
        if event.widget != self.panel_right:
            if self.preview_cursor_pos is not None:
                self.preview_cursor_pos = None
                self.update_display()
            return
            
        # 注意: 这里我们需要 View 的尺寸来做坐标转换
        # 传递整个 Mri 数据到 get_slice_view，而不是部分切片
        mri_view = self.get_slice_view(self.current_case_data['mri'], self.current_slice_index)
        view_h, view_w = mri_view.shape
        
        img_x, img_y = self.screen_to_image_coords(event.x, event.y, view_w, view_h)
        
        # 如果超出边界，不显示预览
        if not (0 <= img_x < view_w and 0 <= img_y < view_h):
             if self.preview_cursor_pos is not None:
                 self.preview_cursor_pos = None
                 self.update_display()
             return

        # 更新预览位置并请求重绘
        self.preview_cursor_pos = (img_x, img_y)
        self.update_display()

    def on_mouse_leave(self, event):
        """鼠标离开控件"""
        if self.preview_cursor_pos is not None:
            self.preview_cursor_pos = None
            self.update_display()

    def on_mouse_down(self, event):
        """处理鼠标按下: 如果是编辑模式则开始绘制，否则平移"""
        if self.edit_mode.get() and self.editable_mask is not None:
            # 判断是否点击在右侧面板 (或双窗模式下的右半屏)
            if event.widget == self.panel_right:
                self.is_drawing = True
                self.start_edit_action() # 准备 Undo 栈
                self.apply_tool(event.x, event.y)
                return

        # 非编辑模式或非右侧面板时，开始左键平移
        self.on_pan_start(event)

    def on_mouse_drag(self, event):
        if self.is_drawing:
            # 更新预览位置
            mri_view = self.get_slice_view(self.current_case_data['mri'], self.current_slice_index)
            view_h, view_w = mri_view.shape
            img_x, img_y = self.screen_to_image_coords(event.x, event.y, view_w, view_h)
            
            if 0 <= img_x < view_w and 0 <= img_y < view_h:
                 self.preview_cursor_pos = (img_x, img_y)
                 
            self.apply_tool(event.x, event.y)
        else:
            self.on_pan_drag(event)

    def on_mouse_up(self, event):
        if self.is_drawing:
            self.is_drawing = False
        else:
            # Pan end
            pass

    def start_edit_action(self):
        """开始新的编辑动作时，保存当前切片状态到撤销栈"""
        if self.editable_mask is None:
            return
            
        idx = self.current_slice_index
        # 保存当前切片的副本
        # 注意：这里我们保存的是原始数据的副本 (RAS 空间)，而不是视图
        # 因为后续恢复时是直接覆盖 3D array 的这一层
        current_slice_data = self.editable_mask[:, :, idx].copy()
        
        self.undo_stack.append((idx, current_slice_data))
        # 限制栈大小
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def undo_action(self):
        """撤销上一次编辑"""
        if not self.undo_stack:
            return
            
        idx, old_data = self.undo_stack.pop()
        
        # 恢复数据
        self.editable_mask[:, :, idx] = old_data
        
        # 如果当前就在这个切片，刷新显示
        if idx == self.current_slice_index:
            self.update_display()

    def get_tool_mask(self, tool, img_x, img_y, mri_view):
        """
        计算当前工具产生的 Mask (View 坐标系)
        :param tool: 'pen', 'eraser', 'wand'
        :param img_x, img_y: 坐标
        :param mri_view: 当前显示的 MRI 切片 (用于 wand)
        """
        h, w = mri_view.shape
        # 将 brush_size 视为直径
        # size=1 -> radius=0.5 -> dist_sq <= 0.25 -> 仅中心点
        # size=2 -> radius=1.0 -> dist_sq <= 1.0 -> 十字
        draw_radius = self.brush_size.get() / 2.0
        
        y, x = np.ogrid[:h, :w]
        
        if tool in ["pen", "eraser"]:
            # 圆形笔刷
            dist_sq = (x - img_x)**2 + (y - img_y)**2
            mask = dist_sq <= (draw_radius**2 + 1e-9)
            return mask
            
        elif tool == "wand":
            # 返回连通区域 mask
            # 为了预览性能，我们可以做一些降级，但先尝试直接计算
            mask = np.zeros_like(mri_view, dtype=bool)
            self.region_grow_optimize(mri_view, mask, img_x, img_y, self.wand_tolerance.get())
            return mask
        
        return None

    def apply_tool(self, sx, sy):
        """应用画笔/橡皮擦/魔棒"""
        if self.editable_mask is None:
            return
            
        idx = self.current_slice_index
        
        # 1. 获取当前切片的 View (用于坐标映射和读取 intensities)
        mri_view = self.get_slice_view(self.current_case_data['mri'], idx)
        mask_view = self.get_slice_view(self.editable_mask, idx)
        
        # 2. 转换坐标
        h, w = mask_view.shape
        img_x, img_y = self.screen_to_image_coords(sx, sy, w, h)
        
        if not (0 <= img_x < w and 0 <= img_y < h):
            return

        tool = self.current_tool.get()
        target_val = self.edit_label_val.get() if tool != "eraser" else 0
        
        # 获取修改 Mask (View空间)
        change_mask = self.get_tool_mask(tool, img_x, img_y, mri_view)
        
        if change_mask is not None:
            # 应用修改
            mask_view[change_mask] = target_val

        self.update_display()

    def region_grow_optimize(self, img, mask, seed_x, seed_y, tolerance):
        """
        优化的区域生长/泛洪填充算法
        :param img: 2D MRI slice
        :param mask: 2D Bool Mask (Output)
        """
        h, w = img.shape
        seed_val = img[seed_y, seed_x]
        
        # 全局二值化 + 连通域标记 可能会更快?
        # 1. 找到所有 pixel 满足 tolerance
        diff = np.abs(img.astype(np.int16) - seed_val)
        binary_map = diff <= tolerance
        
        if not binary_map[seed_y, seed_x]:
             return # Seed not valid? should be
             
        # 2. 找到与 seed 连接的区域
        # 使用 BFS
        # 为了性能, 我们使用 deque (或者 list pop(0))
        # 也可以手动 while loop + 4 neighbors
        
        visited = np.zeros_like(img, dtype=bool)
        stack = [(seed_x, seed_y)]
        visited[seed_y, seed_x] = True
        mask[seed_y, seed_x] = True
        
        # 设定一个上限以防卡死 (例如 50000 像素)
        count = 0
        max_pixels = w * h # 允许全图
        
        while stack:
            cx, cy = stack.pop()
            count += 1
            if count > max_pixels: break
            
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if not visited[ny, nx] and binary_map[ny, nx]:
                        visited[ny, nx] = True
                        mask[ny, nx] = True
                        stack.append((nx, ny))

    def export_label(self):
        """导出编辑后的 Label"""
        if self.editable_mask is None:
            messagebox.showwarning("警告", "没有可导出的编辑数据")
            return
            
        # 检查是否有选中的case
        try:
            selection = self.case_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请先选择一个病例")
                return
            current_case = self.valid_cases[selection[0]]
        except (IndexError, TypeError):
            messagebox.showerror("错误", "无法获取当前病例信息")
            return

        # 确定导出文件夹路径
        export_dir = os.path.join(self.root_dir, "EditLabelTrs")
        
        # 第一次导出时检查/创建文件夹
        if not getattr(self, 'checked_export_dir', False):
            if os.path.exists(export_dir):
                if not os.path.isdir(export_dir):
                    messagebox.showerror("错误", f"路径存在但不是文件夹:\n{export_dir}")
                    return
                # 文件夹已存在，提醒用户
                if not messagebox.askyesno("文件夹已存在", 
                                           f"检测到导出文件夹 'EditLabelTrs' 已经在根目录中存在:\n{export_dir}\n\n是否继续使用该文件夹保存文件？"):
                    return
            else:
                # 文件夹不存在，创建
                try:
                    os.makedirs(export_dir)
                except Exception as e:
                    messagebox.showerror("创建文件夹失败", f"无法创建 'EditLabelTrs':\n{e}")
                    return
            
            # 标记为已检查，本次会话后续导出不再询问
            self.checked_export_dir = True
        
        # 构造文件名
        # 使用 CaseName.nii.gz 格式 (如果需要保留 _gt 后缀，可以修改此处)
        case_name = current_case.get('name', 'unknown')
        filename = f"{case_name}.nii.gz"
        file_path = os.path.join(export_dir, filename)
        
        # 检查文件覆盖
        if os.path.exists(file_path):
            if not messagebox.askyesno("覆盖确认", f"文件 {filename} 在 EditLabelTrs 中已存在。\n是否覆盖？", icon='warning'):
                return
            
        try:
            # 构造 NIfTI 对象
            # 重要: 使用原始 MRI 的 affine header，确保空间位置一致
            ref_img = nib.load(current_case['mri_path'])
            ref_img = nib.as_closest_canonical(ref_img) # 确保与我们编辑的空间一致
            
            new_img = nib.Nifti1Image(self.editable_mask.astype(np.float32), ref_img.affine, ref_img.header)
            nib.save(new_img, file_path)
            
            self.status_msg.set(f"成功导出: {filename} 至 EditLabelTrs")
            self.status_color.set("blue")
            self.root.event_generate("<<UpdateStatusColor>>")
            
        except Exception as e:
            messagebox.showerror("导出失败", f"保存文件时出错:\n{e}")

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

    def on_pan_end(self, event):
        """结束右键平移"""
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = NiiViewerApp(root)
    root.mainloop()
