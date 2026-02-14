import os
import json
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
        self.current_case_info = None  # 当前已加载病例的元信息字典
        self.ui_state_path = os.path.join(os.path.expanduser("~"), ".nifti_viewer_ui.json")
        self.sidebar_group_state = self.load_sidebar_group_state()
        self.has_pred_folder = False
        self.has_gt_folder = False
        
        # 显示设置变量
        self.status_msg = tk.StringVar(value="请选择根文件夹 (需包含 imagesTr [必须], predictsTr [可选], labelsTr [可选])")
        self.status_color = tk.StringVar(value="black")
        self.status_metrics_msg = tk.StringVar(value="") # 状态栏的指标信息
        self.status_summary_msg = tk.StringVar(value="")
        self.gamma_val = tk.DoubleVar(value=1.0)
        self.show_pred = tk.BooleanVar(value=True)
        self.show_gt = tk.BooleanVar(value=True)
        self.auto_fit_window = tk.BooleanVar(value=True) # 新增自适应变量
        self.layout_mode = tk.StringVar(value="dual") # dual, left, right
        self.edit_ref_fixed = tk.BooleanVar(value=True)
        self.edit_ref_width = tk.IntVar(value=220)
        self.fill_strategy = tk.StringVar(value="仅填充空白")
        self.fill_scope = tk.StringVar(value="整卷")
        self.guide_overlay_mode = tk.StringVar(value="无")
        self.guide_overlay_alpha = tk.IntVar(value=45)
        self.guide_edges_only = tk.BooleanVar(value=False)
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
        self.edit_label_name = tk.StringVar(value="Label 1")
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
        self.tk_img_center = None
        self.tk_img_ref_mri = None
        self.tk_img_ref_pred = None
        self.tk_img_ref_gt = None
        self.panel_disp_sizes = {}
        self.current_disp_size_editor = None

        # --- UI 布局 ---
        self._setup_ui()

    def _setup_styles(self):
        """统一 ttk 控件视觉样式"""
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # 基础样式
        style.configure(
            "TButton",
            padding=(10, 5),
            font=("Arial", 10),
            background="#ffffff",
            foreground="#1f2937",
            borderwidth=1,
            relief="solid"
        )
        style.map(
            "TButton",
            background=[("active", "#f3f4f6"), ("pressed", "#e5e7eb")],
            foreground=[("disabled", "#9ca3af")]
        )

        # 分组标题按钮
        style.configure(
            "Group.TButton",
            padding=(8, 4),
            font=("Arial", 10, "bold"),
            background="#ffffff",
            foreground="#111827",
            borderwidth=1,
            relief="solid"
        )
        style.map("Group.TButton", background=[("active", "#f8fafc"), ("pressed", "#f3f4f6")])

        # 强调按钮（导入/导出）
        style.configure(
            "Accent.TButton",
            padding=(10, 5),
            font=("Arial", 10, "bold"),
            background="#0ea5e9",
            foreground="#ffffff",
            borderwidth=1,
            relief="solid"
        )
        style.map("Accent.TButton", background=[("active", "#0284c7"), ("pressed", "#0369a1")])

        style.configure("TCombobox", padding=3, font=("Arial", 10), fieldbackground="#ffffff")
        style.configure("TLabelframe.Label", font=("Arial", 10, "bold"))
        style.configure("TSeparator", background="#d1d5db")

    def load_sidebar_group_state(self):
        """读取侧栏分组展开状态"""
        try:
            if os.path.exists(self.ui_state_path):
                with open(self.ui_state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    groups = data.get("sidebar_groups", {})
                    if isinstance(groups, dict):
                        return groups
        except Exception:
            pass
        return {}

    def save_sidebar_group_state(self):
        """保存侧栏分组展开状态"""
        try:
            data = {"sidebar_groups": self.sidebar_group_state}
            with open(self.ui_state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # 状态保存失败不影响主流程
            pass

    def _setup_ui(self):
        """配置界面布局"""
        self._setup_styles()
        self.colors = {
            "app_bg": "#eef2f7",
            "toolbar_bg": "#f8fafc",
            "sidebar_bg": "#e9eef5",
            "card_bg": "#ffffff",
            "text": "#1f2937",
            "muted_text": "#6b7280",
            "divider": "#d1d5db"
        }
        self.root.configure(bg=self.colors["app_bg"])

        # --- 顶部工具栏 (编辑工具) ---
        toolbar = tk.Frame(self.root, bg=self.colors["toolbar_bg"], height=48)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar.pack_propagate(False)
        
        # Edit Toggle
        chk_edit = tk.Checkbutton(toolbar, text="编辑模式", variable=self.edit_mode, 
                                  bg=self.colors["toolbar_bg"], fg=self.colors["text"], command=self.toggle_edit_mode)
        chk_edit.pack(side=tk.LEFT, padx=(10, 8), pady=7)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8), pady=6)
        
        # Tools
        self.tool_frame = tk.Frame(toolbar, bg=self.colors["toolbar_bg"])
        self.tool_frame.pack(side=tk.LEFT)
        
        tk.Label(self.tool_frame, text="工具:", bg=self.colors["toolbar_bg"], fg=self.colors["text"]).pack(side=tk.LEFT, padx=5)
        
        rb_pen = tk.Radiobutton(self.tool_frame, text="画笔", variable=self.current_tool, value="pen", bg=self.colors["toolbar_bg"], fg=self.colors["text"])
        rb_pen.pack(side=tk.LEFT)
        
        rb_erase = tk.Radiobutton(self.tool_frame, text="橡皮擦", variable=self.current_tool, value="eraser", bg=self.colors["toolbar_bg"], fg=self.colors["text"])
        rb_erase.pack(side=tk.LEFT)
        
        rb_wand = tk.Radiobutton(self.tool_frame, text="魔棒", variable=self.current_tool, value="wand", bg=self.colors["toolbar_bg"], fg=self.colors["text"])
        rb_wand.pack(side=tk.LEFT)
        
        # Label Value
        tk.Label(self.tool_frame, text="| 标签值:", bg=self.colors["toolbar_bg"], fg=self.colors["text"]).pack(side=tk.LEFT, padx=5)
        self.cmb_edit_label = ttk.Combobox(
            self.tool_frame,
            textvariable=self.edit_label_name,
            values=["Label 1", "Label 2"],
            width=8,
            state="readonly"
        )
        self.cmb_edit_label.pack(side=tk.LEFT, padx=2)
        self.cmb_edit_label.bind("<<ComboboxSelected>>", self.on_edit_label_changed)
        
        # Settings - Brush / Wand（按工具动态显示）
        self.brush_ctrl_frame = tk.Frame(self.tool_frame, bg=self.colors["toolbar_bg"])
        tk.Label(self.brush_ctrl_frame, text="| 笔刷大小:", bg=self.colors["toolbar_bg"], fg=self.colors["text"]).pack(side=tk.LEFT, padx=(10, 2))
        self.scale_brush = tk.Scale(
            self.brush_ctrl_frame,
            from_=1,
            to=10,
            variable=self.brush_size,
            orient=tk.HORIZONTAL,
            length=80,
            bg=self.colors["toolbar_bg"],
            fg=self.colors["text"],
            highlightthickness=0
        )
        self.scale_brush.pack(side=tk.LEFT)
        self.brush_ctrl_frame.pack(side=tk.LEFT)

        self.wand_ctrl_frame = tk.Frame(self.tool_frame, bg=self.colors["toolbar_bg"])
        tk.Label(self.wand_ctrl_frame, text="| 魔棒阈值:", bg=self.colors["toolbar_bg"], fg=self.colors["text"]).pack(side=tk.LEFT, padx=(10, 2))
        self.spin_wand = ttk.Spinbox(self.wand_ctrl_frame, from_=0, to=100, textvariable=self.wand_tolerance, width=3)
        self.spin_wand.pack(side=tk.LEFT, padx=2)

        # Actions
        # 使用 ttk.Button 以获得更干净的外观（去除可能的黑色背景）
        self.btn_undo_top = ttk.Button(self.tool_frame, text="撤销", command=self.undo_action, width=6)
        self.btn_undo_top.pack(side=tk.LEFT, padx=(20, 5))
        ttk.Separator(self.tool_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=6)
        ttk.Button(self.tool_frame, text="导入 Pred", command=lambda: self.fill_editor_from_source('pred'), width=9, style="Accent.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(self.tool_frame, text="导入 GT", command=lambda: self.fill_editor_from_source('gt'), width=8, style="Accent.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(self.tool_frame, text="减去 Pred", command=lambda: self.subtract_editor_by_source('pred'), width=9).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.tool_frame, text="减去 GT", command=lambda: self.subtract_editor_by_source('gt'), width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.tool_frame, text="全部转 Label 1", command=lambda: self.convert_all_labels_to(1), width=12).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.tool_frame, text="全部转 Label 2", command=lambda: self.convert_all_labels_to(2), width=12).pack(side=tk.LEFT, padx=4)
        self.current_tool.trace_add("write", lambda *_: self.update_tool_param_visibility())
        self.update_tool_param_visibility()

        # 0. 底部状态栏 (提示栏)
        # 增大高度：使用 Frame + height / padding
        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN, height=35, bg=self.colors["card_bg"])
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        status_frame.pack_propagate(False) # 允许 height 生效

        # 左侧：状态消息
        self.lbl_status = tk.Label(status_frame, textvariable=self.status_msg, 
                                   fg=self.colors["text"], bg=self.colors["card_bg"], font=("Arial", 11))
        # 增加左侧间距 padx
        self.lbl_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # 中间/紧随：指标信息
        self.lbl_metrics_bottom = tk.Label(status_frame, textvariable=self.status_metrics_msg,
                                           fg="#2563eb", bg=self.colors["card_bg"], font=("Arial", 11, "bold"))
        self.lbl_metrics_bottom.pack(side=tk.LEFT, padx=(30, 0))
        self.lbl_summary = tk.Label(status_frame, textvariable=self.status_summary_msg,
                                    fg=self.colors["muted_text"], bg=self.colors["card_bg"], font=("Arial", 10))
        self.lbl_summary.pack(side=tk.RIGHT, padx=(0, 12))

        # 动态绑定颜色 (针对状态消息)
        self.root.bind_all("<<UpdateStatusColor>>", lambda e: self.lbl_status.config(fg=self.status_color.get()))

        # 1. 侧边栏
        self.sidebar_outer = tk.Frame(self.root, width=260, bg=self.colors["sidebar_bg"])
        self.sidebar_outer.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_outer.pack_propagate(False) # 固定宽度
        self.sidebar_canvas = tk.Canvas(self.sidebar_outer, bg=self.colors["sidebar_bg"], highlightthickness=0, bd=0)
        self.sidebar_scrollbar = ttk.Scrollbar(self.sidebar_outer, orient=tk.VERTICAL, command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        sidebar = tk.Frame(self.sidebar_canvas, bg=self.colors["sidebar_bg"], padx=10, pady=10)
        self.sidebar_content = sidebar
        self.sidebar_window_id = self.sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        self.sidebar_content.bind("<Configure>", self._on_sidebar_content_configure)
        self.sidebar_canvas.bind("<Configure>", self._on_sidebar_canvas_configure)
        self.root.bind_all("<MouseWheel>", self.on_sidebar_mousewheel)
        self.root.bind_all("<Button-4>", self.on_sidebar_mousewheel)
        self.root.bind_all("<Button-5>", self.on_sidebar_mousewheel)

        # 根目录选择按钮
        # ttk.Button 样式通常跟随系统，但在标准浅色模式下通常是黑字
        btn_open = ttk.Button(sidebar, text="选择根文件夹", command=self.select_root_folder)
        btn_open.pack(fill=tk.X, pady=(0, 10))

        # 文件夹列表
        lbl_list = tk.Label(sidebar, textvariable=self.case_list_title, bg="#f0f0f0", fg="black", anchor="w")
        lbl_list.pack(fill=tk.X)
        case_list_frame = tk.Frame(sidebar, bg="#f0f0f0")
        case_list_frame.pack(fill=tk.X, pady=5)
        self.case_listbox = tk.Listbox(case_list_frame, selectmode=tk.SINGLE, fg="black", bg="white", height=5)
        self.case_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.case_list_scrollbar = ttk.Scrollbar(case_list_frame, orient=tk.VERTICAL, command=self.case_listbox.yview)
        self.case_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.case_listbox.configure(yscrollcommand=self.case_list_scrollbar.set)
        self.case_listbox.bind('<<ListboxSelect>>', self.load_selected_case)

        # 可折叠分组
        self.sidebar_groups = {}
        ctrl_frame = self.create_collapsible_group(sidebar, "显示控制", "display", default_open=False)
        layout_frame = self.create_collapsible_group(sidebar, "窗口布局", "layout", default_open=False)
        edit_ctrl_frame = self.create_collapsible_group(sidebar, "编辑设置", "edit", default_open=True)

        # Gamma 滑动条
        tk.Label(ctrl_frame, text="Gamma 校正:", bg="#f0f0f0", fg="black").pack(anchor="w")
        scale_gamma = tk.Scale(ctrl_frame, from_=0.1, to=3.0, resolution=0.1, 
                               orient=tk.HORIZONTAL, variable=self.gamma_val, 
                               bg="#f0f0f0", fg="black",
                               command=lambda x: self.update_display())
        scale_gamma.pack(fill=tk.X)

        # 复选框
        chk_pred = tk.Checkbutton(ctrl_frame, text="显示Pred", variable=self.show_pred, 
                                  bg="#f0f0f0", fg="black", command=self.update_display)
        chk_pred.pack(anchor="w")
        self.chk_gt = tk.Checkbutton(ctrl_frame, text="显示GT", variable=self.show_gt, 
                                bg="#f0f0f0", fg="black", command=self.update_display)
        self.chk_gt.pack(anchor="w")

        # 旋转按钮
        btn_rot = ttk.Button(ctrl_frame, text="旋转90°", command=self.rotate_image)
        btn_rot.pack(fill=tk.X, pady=(5, 0))

        rb_dual = tk.Radiobutton(layout_frame, text="双窗", variable=self.layout_mode, value="dual",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_dual.pack(anchor="w")
        
        rb_left = tk.Radiobutton(layout_frame, text="Pred", variable=self.layout_mode, value="left",
                                 bg="#f0f0f0", fg="black", command=self.update_display)
        rb_left.pack(anchor="w")
        
        self.rb_right = tk.Radiobutton(layout_frame, text="GT", variable=self.layout_mode, value="right",
                                       bg="#f0f0f0", fg="black", command=self.update_display)
        self.rb_right.pack(anchor="w")

        self.rb_diff = tk.Radiobutton(layout_frame, text="Diff", variable=self.layout_mode, value="diff",
                                      bg="#f0f0f0", fg="black", command=self.update_display, state=tk.DISABLED)
        self.rb_diff.pack(anchor="w")

        # 自适应窗口开关
        chk_autofit = tk.Checkbutton(layout_frame, text="自适应", variable=self.auto_fit_window, 
                                     bg="#f0f0f0", fg="black", command=self.update_display)
        chk_autofit.pack(anchor="w", pady=(5, 0))

        edit_ctrl_frame.grid_columnconfigure(0, weight=1)

        row_fill = tk.Frame(edit_ctrl_frame, bg="#f0f0f0")
        row_fill.grid(row=0, column=0, sticky="ew")
        tk.Label(row_fill, text="填充", bg="#f0f0f0", fg="black").pack(side=tk.LEFT, padx=(0, 6))
        self.cmb_fill_strategy = ttk.Combobox(
            row_fill,
            textvariable=self.fill_strategy,
            values=["仅填充空白", "替换全部"],
            state="readonly",
            width=9
        )
        self.cmb_fill_strategy.pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_fill_scope = ttk.Combobox(
            row_fill,
            textvariable=self.fill_scope,
            values=["整卷", "当前切片"],
            state="readonly",
            width=8
        )
        self.cmb_fill_scope.pack(side=tk.LEFT)

        row_guide = tk.Frame(edit_ctrl_frame, bg="#f0f0f0")
        row_guide.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        tk.Label(row_guide, text="引导", bg="#f0f0f0", fg="black").pack(side=tk.LEFT, padx=(0, 6))
        self.cmb_guide_overlay = ttk.Combobox(
            row_guide,
            textvariable=self.guide_overlay_mode,
            values=["无", "Pred", "GT", "Pred+GT"],
            state="readonly",
            width=9
        )
        self.cmb_guide_overlay.pack(side=tk.LEFT, padx=(0, 4))
        self.cmb_guide_overlay.bind("<<ComboboxSelected>>", lambda e: self.update_display())
        self.chk_guide_edges_only = tk.Checkbutton(
            row_guide,
            text="仅边界",
            variable=self.guide_edges_only,
            bg="#f0f0f0",
            fg="black",
            command=self.update_display
        )
        self.chk_guide_edges_only.pack(side=tk.LEFT)

        self.scale_guide_alpha = tk.Scale(
            edit_ctrl_frame,
            from_=0,
            to=80,
            variable=self.guide_overlay_alpha,
            orient=tk.HORIZONTAL,
            bg="#f0f0f0",
            fg="black",
            highlightthickness=0,
            label="引导透明度",
            command=lambda x: self.update_display()
        )
        self.scale_guide_alpha.grid(row=2, column=0, sticky="ew", pady=(2, 0))

        row_ref = tk.Frame(edit_ctrl_frame, bg="#f0f0f0")
        row_ref.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        chk_ref_fixed = tk.Checkbutton(
            row_ref,
            text="固定参考窗宽度",
            variable=self.edit_ref_fixed,
            bg="#f0f0f0",
            fg="black",
            command=self.on_edit_ref_setting_changed
        )
        chk_ref_fixed.pack(side=tk.LEFT)
        self.scale_ref_width = tk.Scale(
            edit_ctrl_frame,
            from_=140,
            to=360,
            variable=self.edit_ref_width,
            orient=tk.HORIZONTAL,
            length=170,
            bg="#f0f0f0",
            fg="black",
            highlightthickness=0,
            label="参考窗宽度",
            command=lambda x: self.update_display()
        )
        self.scale_ref_width.grid(row=4, column=0, sticky="ew", pady=(2, 0))

        self.edit_widgets = [
            self.cmb_fill_strategy,
            self.cmb_fill_scope,
            self.cmb_guide_overlay,
            self.scale_guide_alpha,
            self.chk_guide_edges_only,
            chk_ref_fixed,
            self.scale_ref_width
        ]
        self.on_edit_ref_setting_changed()

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

        # 编辑快捷操作
        action_row = tk.Frame(sidebar, bg=self.colors["sidebar_bg"])
        action_row.pack(fill=tk.X, pady=(4, 8))
        self.btn_undo_sidebar = ttk.Button(action_row, text="撤销 (Ctrl+Z)", command=self.undo_action, state=tk.DISABLED, width=14)
        self.btn_undo_sidebar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.btn_export_sidebar = ttk.Button(action_row, text="导出 Label", command=self.export_label, state=tk.DISABLED, width=12, style="Accent.TButton")
        self.btn_export_sidebar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

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

        self.panel_center = tk.Label(self.main_panel, bg="#dcdcdc", text="Editor", fg="black")

        # 编辑模式参考区：左侧上下两个小窗（Pred / Label）
        self.ref_container = tk.Frame(self.main_panel, bg="#f3f3f3", width=260)
        self.ref_mri_frame = tk.LabelFrame(self.ref_container, text="原图参考", bg="#f3f3f3", fg="black")
        self.panel_ref_mri = tk.Label(self.ref_mri_frame, bg="#e0e0e0", text="MRI", fg="black")
        self.panel_ref_mri.pack(fill=tk.BOTH, expand=True)
        self.ref_pred_frame = tk.LabelFrame(self.ref_container, text="Pred 参考", bg="#f3f3f3", fg="black")
        self.panel_ref_pred = tk.Label(self.ref_pred_frame, bg="#e0e0e0", text="无 Predict", fg="black")
        self.panel_ref_pred.pack(fill=tk.BOTH, expand=True)
        self.ref_gt_frame = tk.LabelFrame(self.ref_container, text="Label 参考", bg="#f3f3f3", fg="black")
        self.panel_ref_gt = tk.Label(self.ref_gt_frame, bg="#e0e0e0", text="无 Label", fg="black")
        self.panel_ref_gt.pack(fill=tk.BOTH, expand=True)
        
        self.panel_right = tk.Label(self.main_panel, bg="#e0e0e0", text="MRI + Ground Truth", fg="black")
        self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)

        # 绑定鼠标滚轮事件 (Windows/Linux/Mac兼容)
        # Note: Linux 使用 Button-4/5, Windows/Mac 使用 MouseWheel
        self.panel_left.bind("<MouseWheel>", self.on_scroll)
        self.panel_left.bind("<Button-4>", self.on_scroll)
        self.panel_left.bind("<Button-5>", self.on_scroll)

        self.panel_center.bind("<MouseWheel>", self.on_scroll)
        self.panel_center.bind("<Button-4>", self.on_scroll)
        self.panel_center.bind("<Button-5>", self.on_scroll)

        self.panel_ref_mri.bind("<MouseWheel>", self.on_scroll)
        self.panel_ref_mri.bind("<Button-4>", self.on_scroll)
        self.panel_ref_mri.bind("<Button-5>", self.on_scroll)

        self.panel_ref_pred.bind("<MouseWheel>", self.on_scroll)
        self.panel_ref_pred.bind("<Button-4>", self.on_scroll)
        self.panel_ref_pred.bind("<Button-5>", self.on_scroll)

        self.panel_ref_gt.bind("<MouseWheel>", self.on_scroll)
        self.panel_ref_gt.bind("<Button-4>", self.on_scroll)
        self.panel_ref_gt.bind("<Button-5>", self.on_scroll)
        
        self.panel_right.bind("<MouseWheel>", self.on_scroll)
        self.panel_right.bind("<Button-4>", self.on_scroll)
        self.panel_right.bind("<Button-5>", self.on_scroll)

        # 绑定缩放和平移事件
        for panel in [self.panel_left, self.panel_center, self.panel_right, self.panel_ref_mri, self.panel_ref_pred, self.panel_ref_gt]:
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
        # 绑定方向键切片导航
        self.root.bind("<Left>", lambda e: self.step_slice(-1))
        self.root.bind("<Right>", lambda e: self.step_slice(1))
        self.root.bind("<Up>", lambda e: self.step_slice(1))
        self.root.bind("<Down>", lambda e: self.step_slice(-1))

        # 初始化工具栏状态 (必须在 UI 元素创建完成后调用)
        self.toggle_edit_mode()

    def _set_widget_state_recursive(self, widget, is_editing):
        """递归设置控件状态，处理嵌套 Frame 内子控件"""
        for child in widget.winfo_children():
            try:
                if isinstance(child, ttk.Combobox):
                    child.configure(state="readonly" if is_editing else "disabled")
                else:
                    child.configure(state=tk.NORMAL if is_editing else tk.DISABLED)
            except Exception:
                pass
            self._set_widget_state_recursive(child, is_editing)

    def toggle_edit_mode(self):
        """切换编辑模式状态"""
        is_editing = self.edit_mode.get()
        # 启用/禁用工具栏控件
        state = tk.NORMAL if is_editing else tk.DISABLED
        self._set_widget_state_recursive(self.tool_frame, is_editing)
        if hasattr(self, "edit_widgets"):
            for widget in self.edit_widgets:
                try:
                    if isinstance(widget, ttk.Combobox):
                        widget.configure(state="readonly" if is_editing else "disabled")
                    else:
                        widget.configure(state=state)
                except:
                    pass
        if hasattr(self, "btn_undo_sidebar"):
            self.btn_undo_sidebar.config(state=state)
        if hasattr(self, "btn_export_sidebar"):
            self.btn_export_sidebar.config(state=state)
        self.on_edit_ref_setting_changed()
        
        # 切换布局：如果进入编辑模式，强制显示 Editor (Right Panel)
        if is_editing:
            # 保存当前布局模式
            self.previous_layout_mode = self.layout_mode.get()
            # 自动切换到右侧编辑窗口
            self.layout_mode.set("right")
            self.rb_right.config(state=tk.NORMAL, text="编辑器模式")
            
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
            
        self.update_tool_param_visibility()
        self.update_display()

    def on_edit_label_changed(self, event=None):
        """下拉框切换标签值"""
        self.edit_label_val.set(1 if self.edit_label_name.get() == "Label 1" else 2)

    def update_tool_param_visibility(self):
        """仅显示当前工具相关参数，降低顶栏噪声"""
        if not hasattr(self, "brush_ctrl_frame") or not hasattr(self, "wand_ctrl_frame"):
            return
        tool = self.current_tool.get()
        self.brush_ctrl_frame.pack_forget()
        self.wand_ctrl_frame.pack_forget()
        if tool in ["pen", "eraser"]:
            self.brush_ctrl_frame.pack(side=tk.LEFT, before=self.btn_undo_top)
        elif tool == "wand":
            self.wand_ctrl_frame.pack(side=tk.LEFT, before=self.btn_undo_top)

    def _on_sidebar_content_configure(self, event=None):
        """更新侧栏滚动区域"""
        if hasattr(self, "sidebar_canvas"):
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

    def _on_sidebar_canvas_configure(self, event):
        """保持侧栏内容宽度与画布一致"""
        if hasattr(self, "sidebar_window_id"):
            self.sidebar_canvas.itemconfigure(self.sidebar_window_id, width=event.width)

    def _is_sidebar_widget(self, widget):
        """判断事件控件是否在侧栏内"""
        cur = widget
        while cur is not None:
            if cur == getattr(self, "sidebar_content", None) or cur == getattr(self, "sidebar_canvas", None):
                return True
            cur = getattr(cur, "master", None)
        return False

    def on_sidebar_mousewheel(self, event):
        """侧栏滚轮滚动（仅在侧栏区域生效）"""
        if not hasattr(self, "sidebar_canvas"):
            return
        if not self._is_sidebar_widget(event.widget):
            return
        if event.num == 5 or event.delta < 0:
            self.sidebar_canvas.yview_scroll(1, "units")
        elif event.num == 4 or event.delta > 0:
            self.sidebar_canvas.yview_scroll(-1, "units")

    def create_collapsible_group(self, parent, title, key, default_open=True):
        """创建可折叠分组"""
        container = tk.Frame(parent, bg=self.colors["sidebar_bg"])
        container.pack(fill=tk.X, pady=(6, 0))
        btn = ttk.Button(container, text="", style="Group.TButton", command=lambda k=key: self.toggle_sidebar_group(k))
        btn.pack(fill=tk.X)
        body = tk.Frame(container, bg=self.colors["card_bg"], padx=6, pady=6, highlightthickness=1, highlightbackground=self.colors["divider"])
        initial_open = self.sidebar_group_state.get(key, default_open)
        self.sidebar_groups[key] = {
            "title": title,
            "container": container,
            "button": btn,
            "body": body,
            "open": initial_open
        }
        self._refresh_sidebar_group(key)
        return body

    def _refresh_sidebar_group(self, key):
        group = self.sidebar_groups[key]
        arrow = "▼" if group["open"] else "▶"
        summary = self.get_sidebar_group_summary(key)
        if summary and len(summary) > 34:
            summary = summary[:31] + "..."
        if summary:
            group["button"].configure(text=f"{arrow} {group['title']}  |  {summary}")
        else:
            group["button"].configure(text=f"{arrow} {group['title']}")
        if group["open"]:
            group["body"].pack(fill=tk.X, pady=(4, 0))
        else:
            group["body"].pack_forget()
        self._on_sidebar_content_configure()

    def toggle_sidebar_group(self, key):
        """切换分组展开状态"""
        if key not in self.sidebar_groups:
            return
        self.sidebar_groups[key]["open"] = not self.sidebar_groups[key]["open"]
        self.sidebar_group_state[key] = self.sidebar_groups[key]["open"]
        self.save_sidebar_group_state()
        self._refresh_sidebar_group(key)

    def get_sidebar_group_summary(self, key):
        """生成折叠分组标题摘要"""
        if key == "display":
            pred = "Pred" if self.show_pred.get() else "-Pred"
            gt = "GT" if self.show_gt.get() else "-GT"
            return f"显示:{pred}/{gt} Γ{self.gamma_val.get():.1f}"
        if key == "layout":
            mode_map = {
                "dual": "双窗",
                "left": "Pred",
                "right": "GT",
                "diff": "Diff"
            }
            mode = mode_map.get(self.layout_mode.get(), self.layout_mode.get())
            fit = "自适应" if self.auto_fit_window.get() else "固定"
            return f"布局:{mode} · {fit}"
        if key == "edit":
            guide = self.guide_overlay_mode.get()
            if guide != "无":
                suffix = "边界" if self.guide_edges_only.get() else "填充"
                guide = f"{guide}/{suffix}"
            fill = "空白" if self.fill_strategy.get() == "仅填充空白" else "替换"
            scope = "当前" if self.fill_scope.get() == "当前切片" else "整卷"
            return f"引导:{guide} · 填充:{fill}/{scope}"
        return ""

    def refresh_sidebar_group_headers(self):
        """刷新所有分组标题摘要"""
        if not hasattr(self, "sidebar_groups"):
            return
        for key in self.sidebar_groups.keys():
            self._refresh_sidebar_group(key)


    def rotate_image(self):
        """顺时针旋转90度"""
        # np.rot90 默认 k=1 是逆时针90度
        # 我们想要顺时针，所以用 k=-1 (或者 k=3)
        self.rotation_k = (self.rotation_k - 1) % 4
        self.update_display()

    def on_edit_ref_setting_changed(self):
        """编辑参考窗设置改变"""
        if not self.edit_mode.get():
            state = tk.DISABLED
        else:
            state = tk.NORMAL if self.edit_ref_fixed.get() else tk.DISABLED
        self.scale_ref_width.config(state=state)
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
        self.current_case_info = None
        
        if self.edit_mode.get():
            self.edit_mode.set(False)
            self.toggle_edit_mode()
            
        self.layout_mode.set("dual")
        
        # 清空图像和文本
        self.tk_img_left = None
        self.tk_img_right = None
        self.tk_img_center = None
        self.tk_img_ref_mri = None
        self.tk_img_ref_pred = None
        self.tk_img_ref_gt = None
        self.panel_left.config(image='', text="MRI + Prediction")
        self.panel_center.config(image='', text="Editor")
        self.panel_right.config(image='', text="MRI + Ground Truth")
        self.panel_ref_mri.config(image='', text="MRI")
        self.panel_ref_pred.config(image='', text="无 Predict")
        self.panel_ref_gt.config(image='', text="无 Label")
        
        # 恢复默认双窗布局
        self.ref_container.pack_forget()
        self.ref_mri_frame.pack_forget()
        self.ref_pred_frame.pack_forget()
        self.ref_gt_frame.pack_forget()
        self.panel_left.pack_forget()
        self.panel_center.pack_forget()
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
        self.current_case_info = case

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

            # 默认切片: 第一个含 Pred/GT 标签的切片；若无则回退到中间
            self.total_slices = mri_data.shape[2]
            self.current_slice_index = self.get_default_slice_index(pred_data, gt_data, self.total_slices)
            
            # 更新滑动条
            self.slice_scale.config(to=self.total_slices - 1)
            self.slice_scale.set(self.current_slice_index)
            
            self.update_display()

        except Exception as e:
            messagebox.showerror("加载错误", f"无法加载文件: {str(e)}")
            self.current_case_data = {}
            self.current_case_info = None
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

    def get_default_slice_index(self, pred_data, gt_data, total_slices):
        """默认切片: 第一个包含 Pred 或 GT 标签的切片；若无则回退到中间切片"""
        has_label_slices = np.zeros(total_slices, dtype=bool)

        if pred_data is not None:
            has_label_slices |= np.any(pred_data != 0, axis=(0, 1))
        if gt_data is not None:
            has_label_slices |= np.any(gt_data != 0, axis=(0, 1))

        labeled_indices = np.flatnonzero(has_label_slices)
        if labeled_indices.size > 0:
            return int(labeled_indices[0])
        return total_slices // 2

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

    def create_overlay(
        self,
        mri_slice,
        mask_slice,
        color_mask_enabled=True,
        preview_mask=None,
        preview_val=1,
        guide_mode="无",
        guide_alpha=0,
        guide_edges_only=False,
        guide_pred_slice=None,
        guide_gt_slice=None
    ):
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
        use_guide = guide_mode != "无" and guide_alpha > 0 and (guide_pred_slice is not None or guide_gt_slice is not None)
        if (not color_mask_enabled or mask_slice is None) and preview_mask is None and not use_guide:
            return img_pil

        rgba_mask = np.zeros((mri_slice.shape[0], mri_slice.shape[1], 4), dtype=np.uint8)
        guide_fill_rgba = np.zeros_like(rgba_mask)
        guide_edge_rgba = np.zeros_like(rgba_mask)

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

        # 绘制引导层（在已有标签之上再叠加边界，提高可见性）
        if use_guide:
            a_fill = int(max(0, min(255, guide_alpha * 255 / 100)))
            # 边界线透明度更高，保证重合时也可见
            a_edge = min(255, max(140, int(a_fill * 1.8)))

            def compute_edge(mask):
                if mask is None:
                    return None
                up = np.zeros_like(mask, dtype=bool)
                up[1:, :] = mask[:-1, :]
                down = np.zeros_like(mask, dtype=bool)
                down[:-1, :] = mask[1:, :]
                left = np.zeros_like(mask, dtype=bool)
                left[:, 1:] = mask[:, :-1]
                right = np.zeros_like(mask, dtype=bool)
                right[:, :-1] = mask[:, 1:]
                return mask & (~(up & down & left & right))

            def paint_guide(mask, fill_color, edge_color):
                if mask is None or not np.any(mask):
                    return
                if not guide_edges_only:
                    guide_fill_rgba[mask] = [fill_color[0], fill_color[1], fill_color[2], a_fill]
                edge = compute_edge(mask)
                guide_edge_rgba[edge] = [edge_color[0], edge_color[1], edge_color[2], a_edge]

            use_pred = guide_mode in ["Pred", "Pred+GT"] and guide_pred_slice is not None
            use_gt = guide_mode in ["GT", "Pred+GT"] and guide_gt_slice is not None

            if use_pred:
                # Pred 用红系，和绿色/黄色编辑标签反差大
                paint_guide(guide_pred_slice == 1, [255, 70, 70], [255, 255, 255])
                paint_guide(guide_pred_slice == 2, [255, 20, 120], [255, 255, 255])
            if use_gt:
                # GT 用青紫系
                paint_guide(guide_gt_slice == 1, [0, 230, 255], [255, 255, 255])
                paint_guide(guide_gt_slice == 2, [170, 90, 255], [255, 255, 255])

            if use_pred and use_gt:
                overlap = (guide_pred_slice > 0) & (guide_gt_slice > 0)
                guide_edge_rgba[overlap] = [255, 255, 255, 255]

        # 转换为 PIL Overlay
        mask_layer = Image.fromarray(rgba_mask, mode="RGBA")
        guide_fill_layer = Image.fromarray(guide_fill_rgba, mode="RGBA")
        guide_edge_layer = Image.fromarray(guide_edge_rgba, mode="RGBA")

        # 3. 混合
        combined = Image.alpha_composite(img_pil, mask_layer)
        if use_guide:
            combined = Image.alpha_composite(combined, guide_fill_layer)
            combined = Image.alpha_composite(combined, guide_edge_layer)
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

    def process_zoom_pan(self, img_pil, display_constraints, panel=None, track_for_editor=False):
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
        if panel is not None:
            self.panel_disp_sizes[panel] = (disp_w, disp_h)
        if track_for_editor:
            self.current_disp_size_editor = (disp_w, disp_h)
        
        return img_final

    def update_display(self):
        """刷新双面板图像"""
        if not self.current_case_data:
            self.status_summary_msg.set("")
            self.refresh_sidebar_group_headers()
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
            
            if self.edit_mode.get():
                has_pred_ref = pred_slice is not None
                has_gt_ref = gt_slice is not None
                ref_slots = 1 + int(has_pred_ref) + int(has_gt_ref)  # MRI 参考始终占 1 个
                has_ref = True
                if self.edit_ref_fixed.get():
                    ref_w = int(self.edit_ref_width.get())
                    if has_ref:
                        max_ref = max(140, mw - 320)
                        ref_w = max(140, min(ref_w, max_ref))
                    center_w = mw - ref_w if has_ref else mw
                else:
                    ref_w = max(180, min(320, mw // 4))
                    center_w = mw - ref_w if has_ref else mw
                    if has_ref and center_w < 320:
                        ref_w = max(140, mw - 320)
                        center_w = mw - ref_w
                center_constraints = (max(320, center_w), mh)
                mini_constraints = (max(140, ref_w - 10), max(120, mh // ref_slots - 16))
            elif mode == "dual":
                display_constraints = (mw // 2, mh)
            else:
                display_constraints = (mw, mh)
        else:
            # 固定高度模式
            if self.edit_mode.get():
                center_constraints = (720, 750)
                mini_constraints = (260, 750)
            else:
                display_constraints = 512 if mode == "dual" else 750

        # 1. 重置布局 (防止残留)
        self.ref_container.pack_forget()
        self.ref_mri_frame.pack_forget()
        self.ref_pred_frame.pack_forget()
        self.ref_gt_frame.pack_forget()
        self.panel_left.pack_forget()
        self.panel_center.pack_forget()
        self.panel_right.pack_forget()

        # 2. 根据模式 Pack
        if self.edit_mode.get():
            self.ref_container.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=2)
            self.ref_mri_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 2))
            if pred_slice is not None:
                self.ref_pred_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(2, 2))
            if gt_slice is not None:
                self.ref_gt_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(2, 0))
            self.panel_center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        else:
            if mode == "dual":
                self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
                self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)
            elif mode == "left" or mode == "diff":
                self.panel_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            elif mode == "right":
                self.panel_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)

        # 强制更新布局计算，防止渲染和变量延迟
        self.root.update_idletasks()

        # --- 编辑模式：左侧上下参考窗 + 中间编辑 ---
        if self.edit_mode.get():
            # MRI 参考（上）
            img_ref_mri_pil = self.create_overlay(mri_slice, None, False)
            img_ref_mri_display = self.process_zoom_pan(img_ref_mri_pil, mini_constraints, panel=self.panel_ref_mri)
            self.tk_img_ref_mri = ImageTk.PhotoImage(img_ref_mri_display)
            self.panel_ref_mri.config(image=self.tk_img_ref_mri, text="")

            # Pred 参考（上）
            if pred_slice is not None:
                img_ref_pred_pil = self.create_overlay(mri_slice, pred_slice, True)
                img_ref_pred_display = self.process_zoom_pan(img_ref_pred_pil, mini_constraints, panel=self.panel_ref_pred)
                self.tk_img_ref_pred = ImageTk.PhotoImage(img_ref_pred_display)
                self.panel_ref_pred.config(image=self.tk_img_ref_pred, text="")
            else:
                self.panel_ref_pred.config(image="", text="无 Predict")
                self.tk_img_ref_pred = None

            # Label 参考（下）
            if gt_slice is not None:
                img_ref_gt_pil = self.create_overlay(mri_slice, gt_slice, True)
                img_ref_gt_display = self.process_zoom_pan(img_ref_gt_pil, mini_constraints, panel=self.panel_ref_gt)
                self.tk_img_ref_gt = ImageTk.PhotoImage(img_ref_gt_display)
                self.panel_ref_gt.config(image=self.tk_img_ref_gt, text="")
            else:
                self.panel_ref_gt.config(image="", text="无 Label")
                self.tk_img_ref_gt = None

            # 中间编辑窗
            if self.editable_mask is not None:
                mask_slice = self.get_slice_view(self.editable_mask, idx)
                preview_mask = None
                preview_val = 1
                if self.preview_cursor_pos:
                    px, py = self.preview_cursor_pos
                    preview_mask = self.get_tool_mask(self.current_tool.get(), px, py, mri_slice)
                    preview_val = self.edit_label_val.get() if self.current_tool.get() != "eraser" else 0
                img_edit_pil = self.create_overlay(
                    mri_slice,
                    mask_slice,
                    self.show_gt.get(),
                    preview_mask,
                    preview_val,
                    guide_mode=self.guide_overlay_mode.get(),
                    guide_alpha=self.guide_overlay_alpha.get(),
                    guide_edges_only=self.guide_edges_only.get(),
                    guide_pred_slice=pred_slice,
                    guide_gt_slice=gt_slice
                )
            else:
                img_edit_pil = self.create_overlay(mri_slice, None, False)

            img_edit_display = self.process_zoom_pan(
                img_edit_pil,
                center_constraints,
                panel=self.panel_center,
                track_for_editor=True
            )
            self.tk_img_center = ImageTk.PhotoImage(img_edit_display)
            self.panel_center.config(image=self.tk_img_center, text="")
            self.update_status_summary(mode)
            self.refresh_sidebar_group_headers()
            return

        # --- 生成左图 (MRI + Pred) OR (Diff Map) ---
        if mode in ["dual", "left"]:
            img_left_pil = self.create_overlay(mri_slice, pred_slice, self.show_pred.get())
            img_left_display = self.process_zoom_pan(img_left_pil, display_constraints, panel=self.panel_left)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")
        elif mode == "diff":
            # 差异图模式
            img_diff_pil = self.create_diff_overlay(mri_slice, pred_slice, gt_slice)
            img_left_display = self.process_zoom_pan(img_diff_pil, display_constraints, panel=self.panel_left)
            self.tk_img_left = ImageTk.PhotoImage(img_left_display)
            self.panel_left.config(image=self.tk_img_left, text="")

        # --- 生成右图 (MRI + GT or Empty) ---
        if mode in ["dual", "right"]:
            if gt_slice is not None:
                img_right_pil = self.create_overlay(mri_slice, gt_slice, self.show_gt.get())
                img_right_display = self.process_zoom_pan(
                    img_right_pil,
                    display_constraints,
                    panel=self.panel_right,
                    track_for_editor=(mode == "right")
                )
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")
            else:
                img_right_pil = self.create_overlay(mri_slice, None, False)
                img_right_display = self.process_zoom_pan(
                    img_right_pil,
                    display_constraints,
                    panel=self.panel_right,
                    track_for_editor=(mode == "right")
                )
                self.tk_img_right = ImageTk.PhotoImage(img_right_display)
                self.panel_right.config(image=self.tk_img_right, text="")

        self.update_status_summary(mode)
        self.refresh_sidebar_group_headers()

    def update_status_summary(self, mode):
        """底部单行摘要：当前病例、切片、引导层、填充策略"""
        case_name = "未加载"
        if getattr(self, "current_case_info", None):
            case_name = self.current_case_info.get("name", "未知病例")
        guide_part = self.guide_overlay_mode.get()
        if self.edit_mode.get() and guide_part != "无":
            if self.guide_edges_only.get():
                guide_part = f"{guide_part}-边界"
            guide_part = f"{guide_part}({self.guide_overlay_alpha.get()}%)"
        summary = (
            f"Case: {case_name} | Slice: {self.current_slice_index + 1}/{self.total_slices} | "
            f"Mode: {mode} | Guide: {guide_part} | Fill: {self.fill_strategy.get()}/{self.fill_scope.get()}"
        )
        self.status_summary_msg.set(summary)
        if self.edit_mode.get():
            self.lbl_summary.config(fg="#0369a1")
        else:
            self.lbl_summary.config(fg=self.colors["muted_text"])

    def get_active_edit_panel(self):
        """当前用于编辑的主面板"""
        return self.panel_center if self.edit_mode.get() else self.panel_right

    def screen_to_image_coords(self, sx, sy, img_w, img_h):
        """将屏幕坐标转换为 Slice 图像坐标"""
        if not self.current_disp_size_editor:
             return 0, 0

        disp_w, disp_h = self.current_disp_size_editor
        panel = self.get_active_edit_panel()
        p_w = panel.winfo_width()
        p_h = panel.winfo_height()
        
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
        
        # 仅在编辑主面板处理预览
        edit_panel = self.get_active_edit_panel()
        if event.widget != edit_panel:
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
            # 判断是否点击在编辑主面板
            if event.widget == self.get_active_edit_panel():
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
        self.push_undo_entry({
            "kind": "slice",
            "idx": idx,
            "data": current_slice_data
        })

    def push_undo_entry(self, entry):
        """压入撤销栈并控制栈大小"""
        self.undo_stack.append(entry)
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def fill_editor_from_source(self, source_key):
        """将 Pred/GT 整体填充到编辑掩码（可撤销）"""
        if not self.current_case_data:
            return

        source_data = self.current_case_data.get(source_key)
        if source_data is None:
            source_name = "GT" if source_key == "gt" else "Pred"
            messagebox.showwarning("提示", f"当前病例没有可用的 {source_name} 数据")
            return

        if self.editable_mask is None:
            self.editable_mask = np.zeros_like(self.current_case_data['mri'], dtype=np.int8)

        source_data = source_data.astype(np.int8)
        strategy = self.fill_strategy.get()   # 仅填充空白 / 替换全部
        scope = self.fill_scope.get()         # 整卷 / 当前切片
        replace_all = strategy == "替换全部"
        slice_only = scope == "当前切片"
        changed = False

        if slice_only:
            idx = self.current_slice_index
            old_slice = self.editable_mask[:, :, idx].copy()
            src_slice = source_data[:, :, idx]
            dst_slice = self.editable_mask[:, :, idx]

            if replace_all:
                changed = np.any(dst_slice != src_slice)
                if changed:
                    self.push_undo_entry({"kind": "slice", "idx": idx, "data": old_slice})
                    dst_slice[:, :] = src_slice
            else:
                fill_mask = (dst_slice == 0) & (src_slice != 0)
                changed = np.any(fill_mask)
                if changed:
                    self.push_undo_entry({"kind": "slice", "idx": idx, "data": old_slice})
                    dst_slice[fill_mask] = src_slice[fill_mask]
        else:
            if replace_all:
                changed = np.any(self.editable_mask != source_data)
                if changed:
                    self.push_undo_entry({"kind": "full", "data": self.editable_mask.copy()})
                    self.editable_mask = source_data.copy()
            else:
                fill_mask = (self.editable_mask == 0) & (source_data != 0)
                changed = np.any(fill_mask)
                if changed:
                    self.push_undo_entry({"kind": "full", "data": self.editable_mask.copy()})
                    self.editable_mask[fill_mask] = source_data[fill_mask]

        if not changed:
            self.status_metrics_msg.set("填充完成: 无变化（目标区域已存在标注）")
            self.lbl_metrics_bottom.config(fg="gray")
            return

        self.edit_source = source_key
        source_text = "模型预测" if source_key == "pred" else "GT标签"
        self.status_metrics_msg.set(f"已填充: {source_text} | 策略: {strategy} | 范围: {scope}")
        self.lbl_metrics_bottom.config(fg="blue")
        self.update_display()

    def subtract_editor_by_source(self, source_key):
        """从当前编辑掩码中减去 Pred/GT 标签（可撤销）"""
        if not self.current_case_data:
            return
        if self.editable_mask is None:
            self.status_metrics_msg.set("当前没有可减去的编辑结果")
            self.lbl_metrics_bottom.config(fg="gray")
            return

        source_data = self.current_case_data.get(source_key)
        if source_data is None:
            source_name = "GT" if source_key == "gt" else "Pred"
            messagebox.showwarning("提示", f"当前病例没有可用的 {source_name} 数据")
            return

        source_data = source_data.astype(np.int8)
        scope = self.fill_scope.get()  # 整卷 / 当前切片
        slice_only = scope == "当前切片"
        changed = False

        if slice_only:
            idx = self.current_slice_index
            old_slice = self.editable_mask[:, :, idx].copy()
            src_slice = source_data[:, :, idx]
            dst_slice = self.editable_mask[:, :, idx]
            subtract_mask = (src_slice != 0) & (dst_slice != 0)
            changed = np.any(subtract_mask)
            if changed:
                self.push_undo_entry({"kind": "slice", "idx": idx, "data": old_slice})
                dst_slice[subtract_mask] = 0
        else:
            subtract_mask = (source_data != 0) & (self.editable_mask != 0)
            changed = np.any(subtract_mask)
            if changed:
                self.push_undo_entry({"kind": "full", "data": self.editable_mask.copy()})
                self.editable_mask[subtract_mask] = 0

        if not changed:
            self.status_metrics_msg.set("减去完成: 无变化（没有重叠标签）")
            self.lbl_metrics_bottom.config(fg="gray")
            return

        source_text = "模型预测" if source_key == "pred" else "GT标签"
        self.status_metrics_msg.set(f"已减去: {source_text} | 范围: {scope}")
        self.lbl_metrics_bottom.config(fg="blue")
        self.update_display()

    def convert_all_labels_to(self, target_label):
        """将编辑掩码中的全部非0标签一键转换为指定标签（可撤销）"""
        if not self.current_case_data:
            return
        if self.editable_mask is None:
            self.status_metrics_msg.set("当前没有可转换的编辑结果")
            self.lbl_metrics_bottom.config(fg="gray")
            return

        scope = self.fill_scope.get()  # 整卷 / 当前切片
        slice_only = scope == "当前切片"
        changed = False

        if slice_only:
            idx = self.current_slice_index
            old_slice = self.editable_mask[:, :, idx].copy()
            dst_slice = self.editable_mask[:, :, idx]
            convert_mask = (dst_slice != 0) & (dst_slice != target_label)
            changed = np.any(convert_mask)
            if changed:
                self.push_undo_entry({"kind": "slice", "idx": idx, "data": old_slice})
                dst_slice[convert_mask] = target_label
        else:
            convert_mask = (self.editable_mask != 0) & (self.editable_mask != target_label)
            changed = np.any(convert_mask)
            if changed:
                self.push_undo_entry({"kind": "full", "data": self.editable_mask.copy()})
                self.editable_mask[convert_mask] = target_label

        if not changed:
            self.status_metrics_msg.set(f"转换完成: 无变化（已全部为 Label {target_label} 或为空）")
            self.lbl_metrics_bottom.config(fg="gray")
            return

        # 同步当前编辑标签选择，方便继续绘制
        self.edit_label_val.set(target_label)
        self.edit_label_name.set(f"Label {target_label}")
        self.status_metrics_msg.set(f"已一键转换: 全部标签 -> Label {target_label} | 范围: {scope}")
        self.lbl_metrics_bottom.config(fg="blue")
        self.update_display()

    def undo_action(self):
        """撤销上一次编辑"""
        if not self.undo_stack:
            return

        entry = self.undo_stack.pop()

        # 兼容旧格式 tuple: (idx, slice_data)
        if isinstance(entry, tuple) and len(entry) == 2:
            idx, old_data = entry
            self.editable_mask[:, :, idx] = old_data
            self.update_display()
            return

        kind = entry.get("kind") if isinstance(entry, dict) else None
        if kind == "slice":
            idx = entry["idx"]
            self.editable_mask[:, :, idx] = entry["data"]
        elif kind == "full":
            self.editable_mask = entry["data"]
        else:
            return

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

        
        # 优先使用当前已加载病例；若不存在再回退到列表选中项
        current_case = self.current_case_info
        if current_case is None:
            try:
                selection = self.case_listbox.curselection()
                if not selection:
                    messagebox.showwarning("警告", "请先加载一个病例后再导出")
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
            
            new_img = nib.Nifti1Image(self.editable_mask.astype(np.int8), ref_img.affine, ref_img.header)
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

        self.step_slice(step)

    def step_slice(self, step):
        """按步长切换切片（用于滚轮/方向键）"""
        if not self.current_case_data or step == 0:
            return

        new_index = self.current_slice_index + step
        if 0 <= new_index < self.total_slices:
            self.current_slice_index = new_index
            self.slice_scale.set(new_index)
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
        if not self.current_case_data:
            return

        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        
        # 将屏幕像素偏移转换为相对坐标偏移
        # 注意: 拖拽方向与移动视野方向相反 (类似手机地图) -> 鼠标往左拖，视野向右看(中心点减小? 不，鼠标往左，图片往左，中心点变大)
        # 或者是: 拖拽图片。鼠标向右拖(dx > 0)，图片向右动，说明我们想看左边的内容。中心点 x 应减小。
        
        disp_size = self.panel_disp_sizes.get(event.widget)
        if disp_size is None:
            if self.current_disp_size_editor:
                disp_size = self.current_disp_size_editor
            else:
                return
        disp_w, disp_h = disp_size
        
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
