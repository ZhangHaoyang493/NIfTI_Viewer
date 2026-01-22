import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image, ImageTk

class DicomViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DICOM Viewer & Converter")
        self.root.geometry("1400x800")
        
        # --- 变量初始化 ---
        self.root_dir = ""
        self.export_dir = ""    # 预设导出文件夹
        self.cases = []         # [{'path': str, 'name': str}]
        self.current_case_series = {} # {uid: {description, files, ...}}
        
        self.series_filter_var = tk.StringVar()
        self.series_filter_var.trace_add("write", self.on_filter_changed)
        self.current_series_uid = None
        self.current_image_data = None # numpy array (D, H, W)
        self.current_slice_index = 0
        self.total_slices = 0
        
        # 窗宽窗位 (Window/Level)
        self.window_width = 1.0
        self.window_level = 0.5
        self.default_ww = 1.0
        self.default_wl = 0.5

        # 图像引用防止GC
        self.tk_image = None
        
        # 状态变量
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.DoubleVar(value=0)
        self.info_text_var = tk.StringVar(value="")
        
        self._setup_ui()

    def _setup_ui(self):
        """三栏式布局初始化"""
        # 整体布局: 顶部工具栏 + 中间三栏 + 底部状态栏
        
        # --- 底部状态栏 ---
        status_bar = tk.Frame(self.root, relief=tk.SUNKEN, bd=1)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.lbl_status = tk.Label(status_bar, textvariable=self.status_var, anchor="w", padx=5)
        self.lbl_status.pack(side=tk.LEFT)
        
        self.progress_bar = ttk.Progressbar(status_bar, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

        # --- 主容器 (PanedWindow) ---
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=4, bg="#d9d9d9")
        main_pane.pack(fill=tk.BOTH, expand=True)

        # 1. 左栏 (合并了病例列表和序列列表)
        left_frame = tk.Frame(main_pane, bg="#f0f0f0")
        main_pane.add(left_frame, width=300)
        
        # 顶部按钮区
        btn_frame = tk.Frame(left_frame, bg="#f0f0f0", padx=5, pady=5)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="选择根文件夹 (Root)", command=self.select_root_folder).pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="设置导出文件夹 (Output)", command=self.select_export_folder).pack(fill=tk.X)
        self.lbl_export_dir = tk.Label(btn_frame, text="未设置导出路径 (默认询问)", bg="#f0f0f0", fg="gray", anchor="w", font=("Arial", 9))
        self.lbl_export_dir.pack(fill=tk.X, pady=(2, 0))

        # 列表区域 (使用垂直 PanedWindow 分隔病例和序列)
        list_pane = tk.PanedWindow(left_frame, orient=tk.VERTICAL, sashwidth=4, bg="#d9d9d9")
        list_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # -- 病例列表区域 --
        case_frame = tk.Frame(list_pane, bg="#f0f0f0")
        list_pane.add(case_frame, height=300) # 初始高度
        
        self.lbl_cases_title = tk.Label(case_frame, text="病例列表 (0)", bg="#f0f0f0", anchor="w", fg="black")
        self.lbl_cases_title.pack(fill=tk.X)
        self.lbl_case_parent = tk.Label(case_frame, text="来源: -", bg="#f0f0f0", anchor="w", fg="gray", font=("Arial", 10))
        self.lbl_case_parent.pack(fill=tk.X)
        
        self.case_listbox = tk.Listbox(case_frame, selectmode=tk.SINGLE, bg="white", fg="black", exportselection=False)
        self.case_listbox.pack(fill=tk.BOTH, expand=True)
        self.case_listbox.bind('<<ListboxSelect>>', self.on_case_selected)
        
        # -- 序列列表区域 --
        series_frame = tk.Frame(list_pane, bg="#f0f0f0")
        list_pane.add(series_frame)
        
        # 过滤框区
        filter_frame = tk.Frame(series_frame, bg="#f0f0f0")
        filter_frame.pack(fill=tk.X, padx=0, pady=(5,0))
        tk.Label(filter_frame, text="过滤(Regex):", bg="#f0f0f0", fg="black", font=("Arial", 10)).pack(side=tk.LEFT)
        tk.Entry(filter_frame, textvariable=self.series_filter_var, bg="white", fg="black", font=("Arial", 10)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_series_title = tk.Label(series_frame, text="MRI 序列 (0)", bg="#f0f0f0", anchor="w", fg="black")
        self.lbl_series_title.pack(fill=tk.X, pady=(2, 0))

        self.series_listbox = tk.Listbox(series_frame, selectmode=tk.SINGLE, bg="white", fg="black", exportselection=False)
        self.series_listbox.pack(fill=tk.BOTH, expand=True)
        self.series_listbox.bind('<<ListboxSelect>>', self.on_series_selected)
        
        # 底部操作区
        action_frame = tk.Frame(left_frame, bg="#f0f0f0", padx=5, pady=10)
        action_frame.pack(fill=tk.X)
        # 导出按钮
        self.btn_export = ttk.Button(action_frame, text="导出选中序列 NIfTI", command=self.export_nifti, state=tk.DISABLED)
        self.btn_export.pack(fill=tk.X, pady=(0, 5))
        # 元数据按钮
        self.btn_meta = ttk.Button(action_frame, text="查看元数据 (Tags)", command=self.show_metadata, state=tk.DISABLED)
        self.btn_meta.pack(fill=tk.X)

        # 2. 右栏: 图像查看器
        right_frame = tk.Frame(main_pane, bg="black")
        main_pane.add(right_frame)
        
        # 信息覆盖层
        self.overlay_info = tk.Label(right_frame, textvariable=self.info_text_var, 
                                   bg="black", fg="yellow", justify=tk.LEFT, anchor="nw")
        self.overlay_info.place(x=10, y=10)
        
        # 图像显示区
        self.img_label = tk.Label(right_frame, bg="black")
        self.img_label.pack(fill=tk.BOTH, expand=True)
        
        # 绑定事件
        self.img_label.bind("<MouseWheel>", self.on_scroll)   # Win/Mac
        self.img_label.bind("<Button-4>", self.on_scroll)     # Linux
        self.img_label.bind("<Button-5>", self.on_scroll)
        
        self.img_label.bind("<B1-Motion>", self.on_drag_windowing) # 窗宽窗位
        self.img_label.bind("<ButtonPress-1>", self.on_drag_start)

    def select_root_folder(self):
        """选择根目录"""
        init_dir = "/Volumes/Sandisk/WAIYUAN_DATA_DCM"
        if not os.path.exists(init_dir):
            init_dir = os.path.expanduser("~/Desktop")
            
        path = filedialog.askdirectory(initialdir=init_dir)
        if not path:
            return
        
        self.root_dir = path
        # 启动后台线程扫描
        threading.Thread(target=self.scan_directory_thread, daemon=True).start()

    def select_export_folder(self):
        """选择导出文件夹"""
        init_dir = os.path.expanduser("~/Desktop")
        path = filedialog.askdirectory(title="选择默认导出文件夹", initialdir=init_dir)
        if path:
            self.export_dir = path
            # 简单截断显示
            display_path = path if len(path) < 30 else "..." + path[-27:]
            self.lbl_export_dir.config(text=f"导出至: {display_path}", fg="#0066cc")


    def scan_directory_thread(self):
        """后台扫描目录线程"""
        self.status_var.set("正在扫描目录...")
        self.progress_bar.start(10) # 不确定进度模式
        
        self.cases = []
        # UI线程安全更新
        def clear_list():
            self.case_listbox.delete(0, tk.END)
            self.series_listbox.delete(0, tk.END)
        self.root.after(0, clear_list)

        try:
            temp_cases = []
            for root, dirs, files in os.walk(self.root_dir):
                has_dcm = False
                for f in files:
                    if f.lower().endswith('.dcm'):
                        has_dcm = True
                        break
                
                if has_dcm:
                    case_name = os.path.basename(root)
                    temp_cases.append({'path': root, 'name': case_name})
            
            # 排序（可选，按名称）
            temp_cases.sort(key=lambda x: x['name'])
            self.cases = temp_cases
            
            # 更新UI
            def update_ui_cases():
                self.case_listbox.delete(0, tk.END)
                for case in self.cases:
                    self.case_listbox.insert(tk.END, case['name'])
                
                # 更新标题显示数量
                self.lbl_cases_title.config(text=f"病例列表 ({len(self.cases)})")
                
                self.progress_bar.stop()
                self.status_var.set(f"扫描完成，找到 {len(self.cases)} 个病例文件夹。")
                
            self.root.after(0, update_ui_cases)

        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"扫描出错: {str(e)}"))
            self.root.after(0, self.progress_bar.stop)

    def on_filter_changed(self, *args):
        """当过滤关键词改变时触发"""
        self.update_series_list_display()

    def update_series_list_display(self):
        """根据当前序列数据和过滤词更新列表"""
        self.series_listbox.delete(0, tk.END)
        # 清空当前显示的keys
        self.series_keys = []
        
        if not hasattr(self, 'current_case_series') or not self.current_case_series:
            self.lbl_series_title.config(text="MRI 序列 (0)")
            return
            
        series_dict = self.current_case_series
        filter_txt = self.series_filter_var.get().strip()
        
        filtered_keys = []
        all_keys = list(series_dict.keys())
        
        # 1. 过滤
        if not filter_txt:
            filtered_keys = all_keys
        else:
            try:
                # 尝试编译正则
                pattern = re.compile(filter_txt, re.IGNORECASE)
                for uid in all_keys:
                    desc = series_dict[uid]['description']
                    if pattern.search(desc):
                        filtered_keys.append(uid)
            except re.error:
                # 正则错误时不进行任何匹配，或者可以当做空处理
                # 这里选择显示空，提示用户正则错? 或者保持上一次? 
                # 简单起见，如果正则错，就暂时不显示匹配结果 (显示0)
                pass
        
        self.series_keys = filtered_keys
        
        # 2. 显示
        if not self.series_keys:
            if series_dict and filter_txt:
                 self.series_listbox.insert(tk.END, "(无匹配序列)")
            elif not series_dict:
                 self.series_listbox.insert(tk.END, "(无 DICOM 序列)")
        else:
            for uid in self.series_keys:
                info = series_dict[uid]
                count = len(info['files'])
                label = f"{info['description']} [{count} images]"
                self.series_listbox.insert(tk.END, label)

        # 3. 更新计数标题
        count_display = len(self.series_keys)
        total_display = len(series_dict)
        if filter_txt:
            self.lbl_series_title.config(text=f"MRI 序列 ({count_display}/{total_display})")
        else:
            self.lbl_series_title.config(text=f"MRI 序列 ({total_display})")

    def on_case_selected(self, event):
        """选中病例，解析其中的序列"""
        selection = self.case_listbox.curselection()
        if not selection:
            return
            
        case_idx = selection[0]
        case_path = self.cases[case_idx]['path']
        
        # 显示来源子文件夹
        try:
            rel_path = os.path.relpath(case_path, self.root_dir)
            parent_dir = os.path.dirname(rel_path)
            if not parent_dir or parent_dir == ".":
                display_source = "Root"
            else:
                display_source = parent_dir
            self.lbl_case_parent.config(text=f"来源: {display_source}")
        except:
             self.lbl_case_parent.config(text="来源: -")
        
        self.status_var.set(f"正在解析病例: {self.cases[case_idx]['name']}...")
        self.series_listbox.delete(0, tk.END)
        self.btn_export.config(state=tk.DISABLED)
        self.btn_meta.config(state=tk.DISABLED)
        
        # 启动后台线程解析DICOM头
        threading.Thread(target=self.parse_series_thread, args=(case_path,), daemon=True).start()

    def parse_series_thread(self, case_path):
        """解析Dicom Series"""
        self.progress_bar.start(10)
        series_dict = {} # uid -> {info}
        
        try:
            # 简单遍历文件夹下的文件
            files = [os.path.join(case_path, f) for f in os.listdir(case_path) if f.lower().endswith('.dcm')]
            
            for fpath in files:
                try:
                    # 只读取头部，加快速度
                    ds = pydicom.dcmread(fpath, stop_before_pixels=True)
                    uid = ds.SeriesInstanceUID
                    desc = ds.get("SeriesDescription", "No Description")
                    
                    if uid not in series_dict:
                        series_dict[uid] = {
                            "description": desc,
                            "files": [],
                            "study_id": ds.get("StudyID", ""),
                            "patient_id": ds.get("PatientID", "")
                        }
                    series_dict[uid]["files"].append(fpath)
                except:
                    continue
            
            self.current_case_series = series_dict
            
            def update_ui_series():
                self.update_series_list_display()
                self.progress_bar.stop()
                self.status_var.set(f"解析完成，共 {len(series_dict)} 个序列。")
                
            self.root.after(0, update_ui_series)
            
        except Exception as e:
             self.root.after(0, lambda: self.status_var.set(f"解析出错: {e}"))
             self.root.after(0, self.progress_bar.stop)

    def on_series_selected(self, event):
        """选中序列，加载图像数据"""
        selection = self.series_listbox.curselection()
        if not selection or not hasattr(self, 'series_keys'):
            return
            
        idx = selection[0]
        if idx >= len(self.series_keys): return
        
        uid = self.series_keys[idx]
        self.current_series_uid = uid
        series_info = self.current_case_series[uid]
        
        self.status_var.set(f"正在加载图像卷: {series_info['description']}...")
        self.btn_export.config(state=tk.DISABLED)
        self.btn_meta.config(state=tk.DISABLED)
        
        threading.Thread(target=self.load_image_volume_thread, args=(uid,), daemon=True).start()

    def load_image_volume_thread(self, uid):
        """使用 SimpleITK 读取序列构建 3D 卷"""
        self.progress_bar.start(10)
        try:
            series_info = self.current_case_series[uid]
            reader = sitk.ImageSeriesReader()
            
            # 使用 SimpleITK 自动排序文件名
            dicom_names = reader.GetGDCMSeriesFileNames(os.path.dirname(series_info['files'][0]), uid)
            reader.SetFileNames(dicom_names)
            
            # 读取图像
            image_sitk = reader.Execute()
            
            # 转为 numpy
            # SimpleITK 顺序 (D, H, W)
            image_np = sitk.GetArrayFromImage(image_sitk)
            
            # 存储当前的SimpleITK对象以便导出时使用（如果需要原始meta），或者仅用numpy显示
            # 为了一致性，这里我们主要用于显示，导出时重新读取或使用此对象
            self.current_sitk_image = image_sitk 
            self.current_image_data = image_np
            
            # 读取默认 Window Level (尝试从第一个文件读)
            # 使用 pydicom 读取第一个文件的 tag 比较方便
            try:
                first_dcm = pydicom.dcmread(dicom_names[0], stop_before_pixels=True)
                ww = first_dcm.get("WindowWidth", 0)
                wl = first_dcm.get("WindowCenter", 0)
                
                # 有些dicom可能是多值的列表
                if hasattr(ww, '__iter__'): ww = ww[0]
                if hasattr(wl, '__iter__'): wl = wl[0]
                
                self.default_ww = float(ww) if ww else np.max(image_np) - np.min(image_np)
                self.default_wl = float(wl) if wl else (np.max(image_np) + np.min(image_np)) / 2
            except:
                self.default_ww = np.max(image_np) - np.min(image_np)
                self.default_wl = (np.max(image_np) + np.min(image_np)) / 2
                
            self.window_width = self.default_ww
            self.window_level = self.default_wl
            
            # 更新状态
            self.total_slices = image_np.shape[0]
            self.current_slice_index = self.total_slices // 2
            
            def update_viewer():
                self.update_display()
                self.btn_export.config(state=tk.NORMAL)
                self.btn_meta.config(state=tk.NORMAL)
                self.progress_bar.stop()
                self.status_var.set("图像加载完成。按住左键拖拽可调整窗宽窗位。")
                
            self.root.after(0, update_viewer)
            
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"加载卷出错: {e}"))
            self.root.after(0, self.progress_bar.stop)

    def update_display(self):
        """刷新图像显示"""
        if self.current_image_data is None:
            return
            
        # 1. 获取切片
        idx = max(0, min(self.current_slice_index, self.total_slices - 1))
        # SimpleITK numpy array is (Z, Y, X)
        slice_data = self.current_image_data[idx, :, :]
        
        # 2. 应用 Window/Level
        # 简单的线性变换: Output = (Input - (Level - 0.5 * Width)) / Width * 255
        min_val = self.window_level - (self.window_width / 2.0)
        max_val = self.window_level + (self.window_width / 2.0)
        
        img_norm = (slice_data - min_val) / (max_val - min_val)
        img_norm = np.clip(img_norm, 0, 1) * 255
        img_uint8 = img_norm.astype(np.uint8)
        
        # 3. 显示
        img_pil = Image.fromarray(img_uint8)
        
        # 自适应窗口大小
        disp_w = self.img_label.winfo_width()
        disp_h = self.img_label.winfo_height()
        if disp_w > 1 and disp_h > 1:
            # 保持比例缩放
            ratio = min(disp_w / img_pil.width, disp_h / img_pil.height)
            new_size = (int(img_pil.width * ratio), int(img_pil.height * ratio))
            img_pil = img_pil.resize(new_size, Image.Resampling.LANCZOS)
        
        self.tk_image = ImageTk.PhotoImage(img_pil)
        self.img_label.config(image=self.tk_image)
        
        # 4. 更新元数据文本
        info_str = f"Slice: {idx+1}/{self.total_slices}\n"
        info_str += f"WW: {self.window_width:.1f}  WL: {self.window_level:.1f}\n"
        
        try:
            # 获取Pixel Spacing等需从原SITK对象拿
            spacing = self.current_sitk_image.GetSpacing() #(x, y, z)
            info_str += f"Spacing: {spacing[0]:.2f} x {spacing[1]:.2f} x {spacing[2]:.2f} mm"
        except:
            pass
            
        self.info_text_var.set(info_str)

    def on_scroll(self, event):
        """鼠标滚轮切片"""
        if self.current_image_data is None: return
        
        # Linux (4/5) vs Win/Mac (delta)
        if event.num == 5 or event.delta < 0:
            step = 1 # 下一张
        elif event.num == 4 or event.delta > 0:
            step = -1 # 上一张
        else:
            step = 0
            
        new_idx = self.current_slice_index + step
        if 0 <= new_idx < self.total_slices:
            self.current_slice_index = new_idx
            self.update_display()

    def on_drag_start(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.start_ww = self.window_width
        self.start_wl = self.window_level

    def on_drag_windowing(self, event):
        """拖拽调整窗宽窗位"""
        if self.current_image_data is None: return

        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        
        # 灵敏度因子
        sensitivity = 1.0 # 可以根据图像动态范围调整
        
        # 左右拖动调整 Width (对比度)
        self.window_width = max(1, self.start_ww + dx * sensitivity)
        
        # 上下拖动调整 Level (亮度)
        self.window_level = self.start_wl - dy * sensitivity
        
        self.update_display()

    def export_nifti(self):
        """导出为 NIfTI"""
        # 重置状态栏颜色
        self.lbl_status.config(fg="black")

        if self.current_sitk_image is None or not self.current_series_uid:
            self.status_var.set("导出失败: 未选中已加载的序列")
            self.lbl_status.config(fg="red")
            return
            
        # 获取病例文件夹名
        selection = self.case_listbox.curselection()
        if not selection:
            self.status_var.set("导出失败: 未选中任何病例文件夹")
            self.lbl_status.config(fg="red")
            return
            
        case_idx = selection[0]
        root_folder_name = self.cases[case_idx]['name']
        
        default_filename = f"pcfd_{root_folder_name}_0000.nii.gz"
        
        # 确定保存路径
        if self.export_dir and os.path.exists(self.export_dir):
            save_path = os.path.join(self.export_dir, default_filename)
        else:
            self.status_var.set("导出失败: 请先设置有效的导出文件夹")
            self.lbl_status.config(fg="red")
            return
        
        # 后台保存 (覆盖不提示)
        threading.Thread(target=self.save_nifti_thread, args=(save_path,), daemon=True).start()
        
    def save_nifti_thread(self, save_path):
        self.status_var.set("正在导出 NIfTI...")
        self.lbl_status.config(fg="black")
        self.progress_bar.start(20)
        try:
            # 写入文件
            sitk.WriteImage(self.current_sitk_image, save_path)
            
            def success():
                self.progress_bar.stop()
                # 导出成功显示绿色字，显示路径
                self.lbl_status.config(fg="green")
                self.status_var.set(f"导出成功! 文件: {os.path.basename(save_path)}  路径: {os.path.dirname(save_path)}")
                
            self.root.after(0, success)
            
        except Exception as e:
            def fail(msg):
                self.progress_bar.stop()
                self.lbl_status.config(fg="red")
                self.status_var.set(f"导出失败: {msg}")
            self.root.after(0, lambda: fail(str(e)))

    def show_metadata(self):
        """弹窗显示元数据"""
        if not self.current_series_uid: return
        
        series_info = self.current_case_series[self.current_series_uid]
        first_file = series_info['files'][0]
        
        top = tk.Toplevel(self.root)
        top.title("DICOM Tags (First Slice)")
        top.geometry("600x600")
        
        text = tk.Text(top, wrap=tk.NONE)
        ys = ttk.Scrollbar(top, orient="vertical", command=text.yview)
        xs = ttk.Scrollbar(top, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        
        ys.pack(side=tk.RIGHT, fill=tk.Y)
        xs.pack(side=tk.BOTTOM, fill=tk.X)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        try:
            ds = pydicom.dcmread(first_file)
            text.insert(tk.END, str(ds))
        except Exception as e:
            text.insert(tk.END, f"读取失败: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = DicomViewerApp(root)
    root.mainloop()
