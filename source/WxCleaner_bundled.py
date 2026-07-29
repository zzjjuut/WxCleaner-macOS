import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import os
import sys
import time
import hashlib
import concurrent.futures
from collections import defaultdict
from send2trash import send2trash
# from PIL import Image, ImageTk # 移除未使用的引用
from ctypes import windll

# ==========================================
# 辅助函数
# ==========================================

def resource_path(relative_path):
    """ 获取资源绝对路径，适配 PyInstaller 打包后的路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ==========================================
# 核心扫描逻辑
# ==========================================

def calculate_hash(file_path, block_size=65536, partial=False):
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            if partial:
                buf = f.read(1024)
                hasher.update(buf)
            else:
                buf = f.read(block_size)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(block_size)
        return hasher.hexdigest()
    except (OSError, IOError):
        return None

def find_duplicates(scan_path, progress_callback=None):
    if progress_callback:
        progress_callback(0, 0, "正在统计文件总数...")
    
    total_files = 0
    for root, _, files in os.walk(scan_path):
        total_files += len(files)
    
    if progress_callback:
        progress_callback(0, total_files, f"共找到 {total_files} 个文件，开始分析...")

    size_groups = defaultdict(list)
    processed_count = 0
    
    for root, _, files in os.walk(scan_path):
        for name in files:
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
                if size > 0: 
                    size_groups[size].append(path)
            except OSError:
                continue
            
            processed_count += 1
            if progress_callback and processed_count % 100 == 0:
                progress_callback(processed_count, total_files, "正在按大小筛选...")

    potential_duplicates_count = sum(len(paths) for paths in size_groups.values() if len(paths) > 1)
    current_hash_processed = 0
    
    partial_hash_groups = defaultdict(list)
    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue
        for path in paths:
            h = calculate_hash(path, partial=True)
            if h:
                partial_hash_groups[(size, h)].append(path)
            
            current_hash_processed += 1
            if progress_callback and current_hash_processed % 10 == 0:
                 if potential_duplicates_count > 0:
                     p = 0.5 * total_files + 0.25 * total_files * (current_hash_processed / potential_duplicates_count)
                     progress_callback(p, total_files, "正在计算头部哈希...")

    potential_full_hash_count = sum(len(paths) for paths in partial_hash_groups.values() if len(paths) > 1)
    current_full_hash_processed = 0
    
    duplicates = defaultdict(list)
    for (size, phash), paths in partial_hash_groups.items():
        if len(paths) < 2:
            continue
        for path in paths:
            h = calculate_hash(path, partial=False)
            if h:
                duplicates[h].append(path)
            
            current_full_hash_processed += 1
            if progress_callback:
                if potential_full_hash_count > 0:
                    p = 0.75 * total_files + 0.25 * total_files * (current_full_hash_processed / potential_full_hash_count)
                    progress_callback(p, total_files, "正在进行全量校验...")

    return {h: paths for h, paths in duplicates.items() if len(paths) > 1}


# ==========================================
# UI 逻辑
# ==========================================

class WxCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("微信重复文件清理工具")
        self.root.geometry("1100x800")
        
        # 恢复默认字体设置
        self.ui_font_normal = ("Microsoft YaHei", 10)
        self.ui_font_bold = ("Microsoft YaHei", 10, "bold")
        
        # 设置窗口图标
        try:
            icon_file = resource_path("icon.ico")
            if os.path.exists(icon_file):
                self.root.iconbitmap(icon_file)
        except Exception as e:
            print(f"图标加载失败: {e}")
        
        # 设置全局字体
        self.root.option_add("*Font", self.ui_font_normal)
        
        style = ttk.Style()
        style.configure("Treeview", font=self.ui_font_normal, rowheight=30)
        style.configure("Treeview.Heading", font=self.ui_font_bold)
        
        self.scan_path = tk.StringVar()
        self.duplicates = {} 
        
        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=BOTH, expand=YES)
        
        top_frame = ttk.Labelframe(main_frame, text="扫描设置", padding="10")
        top_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(top_frame, text="扫描路径:", font=self.ui_font_bold).pack(side=LEFT)
        self.entry = ttk.Entry(top_frame, textvariable=self.scan_path, font=self.ui_font_normal)
        self.entry.pack(side=LEFT, fill=X, expand=YES, padx=10)
        
        ttk.Button(top_frame, text="浏览", command=self.browse_folder, bootstyle="outline-primary").pack(side=LEFT, padx=5)
        ttk.Button(top_frame, text="开始扫描", command=self.start_scan_thread, bootstyle="primary").pack(side=LEFT, padx=5)
        
        list_frame = ttk.Labelframe(main_frame, text="重复文件列表 (红色标记为建议清理项)", padding="10")
        list_frame.pack(fill=BOTH, expand=YES)
        
        tree_scroll = ttk.Scrollbar(list_frame, bootstyle="round")
        tree_scroll.pack(side=RIGHT, fill=Y)
        
        columns = ("num", "path", "size", "mtime", "status")
        self.tree = ttk.Treeview(
            list_frame, 
            columns=columns, 
            show="headings", 
            selectmode="extended",
            bootstyle="info",
            yscrollcommand=tree_scroll.set
        )
        tree_scroll.config(command=self.tree.yview)
        
        self.tree.heading("num", text="序号", anchor=CENTER, command=lambda: self.sort_column("num", False))
        self.tree.heading("path", text="文件路径", command=lambda: self.sort_column("path", False))
        self.tree.heading("size", text="大小", command=lambda: self.sort_column("size", False))
        self.tree.heading("mtime", text="修改时间", command=lambda: self.sort_column("mtime", False))
        self.tree.heading("status", text="状态", command=lambda: self.sort_column("status", False))
        
        self.tree.column("num", width=70, anchor=CENTER, stretch=False)
        self.tree.column("path", width=500, anchor=W)
        self.tree.column("size", width=120, anchor=E)
        self.tree.column("mtime", width=180, anchor=CENTER)
        self.tree.column("status", width=100, anchor=CENTER)
        
        self.tree.pack(fill=BOTH, expand=YES)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="打开文件位置", command=self.open_file_location)
        self.menu.add_separator()
        self.menu.add_command(label="保留此文件 (设为绿色)", command=self.unmark_item)
        self.menu.add_command(label="标记为删除 (设为红色)", command=self.mark_item)
        self.tree.bind("<Button-3>", self.show_menu)
        
        bottom_frame = ttk.Frame(main_frame, padding="10")
        bottom_frame.pack(fill=X, pady=(10, 0))
        
        self.progress = ttk.Progressbar(bottom_frame, orient=HORIZONTAL, mode='determinate', bootstyle="success-striped")
        self.progress.pack(fill=X, pady=(0, 10))
        
        info_frame = ttk.Frame(bottom_frame)
        info_frame.pack(fill=X)
        
        self.status_label = ttk.Label(info_frame, text="准备就绪", bootstyle="secondary", font=self.ui_font_normal)
        self.status_label.pack(side=LEFT)
        
        self.selection_label = ttk.Label(info_frame, text="", bootstyle="danger", font=self.ui_font_bold)
        self.selection_label.pack(side=LEFT, padx=20)
        
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(side=RIGHT)
        
        ttk.Button(btn_frame, text="全选重复项", command=self.select_all_duplicates, bootstyle="warning-outline").pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="移至回收站", command=self.delete_selected, bootstyle="danger").pack(side=LEFT, padx=5)

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.scan_path.set(path)

    def start_scan_thread(self):
        path = self.scan_path.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("警告", "请选择有效的文件夹")
            return
        
        self.status_label.config(text="正在初始化...", bootstyle="info")
        self.progress['value'] = 0
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.selection_label.config(text="")
            
        threading.Thread(target=self.run_scan, args=(path,), daemon=True).start()

    def run_scan(self, path):
        def progress_callback(current, total, status_text):
            def _update():
                self.status_label.config(text=status_text)
                if total > 0:
                    if "统计" in status_text:
                        self.progress['mode'] = 'indeterminate'
                        self.progress.start(10)
                    else:
                        self.progress.stop()
                        self.progress['mode'] = 'determinate'
                        if "筛选" in status_text:
                            pct = (current / total) * 50
                        else:
                            pct = (current / total) * 100
                        self.progress['value'] = pct
            self.root.after(0, _update)

        try:
            self.duplicates = find_duplicates(path, progress_callback=progress_callback)
            self.root.after(0, self.update_results)
        except Exception as e:
            def _error():
                messagebox.showerror("错误", f"扫描出错: {e}")
                self.status_label.config(text="扫描失败", bootstyle="danger")
            self.root.after(0, _error)

    def update_results(self):
        self.progress['value'] = 100
        self.tree.tag_configure("duplicate", foreground="#e74c3c")
        self.tree.tag_configure("original", foreground="#27ae60")
        
        total_groups = len(self.duplicates)
        total_files = sum(len(p) for p in self.duplicates.values())
        
        def format_size(size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024: return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} TB"

        count = 1
        for h, paths in self.duplicates.items():
            paths.sort(key=lambda x: len(x))
            
            for i, p in enumerate(paths):
                try:
                    stat = os.stat(p)
                    size = stat.st_size
                    size_str = format_size(size)
                    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                except:
                    size_str = "未知"
                    mtime_str = "未知"
                
                status = "保留" if i == 0 else "重复"
                tags = ("original",) if i == 0 else ("duplicate",)
                
                self.tree.insert("", tk.END, values=(count, p, size_str, mtime_str, status), tags=tags)
                count += 1
        
        self.status_label.config(text=f"完成！找到 {total_groups} 组重复，共 {total_files} 个文件", bootstyle="success")

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        count = len(selected_items)
        total_size = 0.0
        
        for item in selected_items:
            try:
                size_str = self.tree.item(item)['values'][2]
                parts = size_str.split()
                if len(parts) == 2:
                    val = float(parts[0])
                    unit = parts[1]
                    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                    total_size += val * multipliers.get(unit, 0)
            except:
                pass
        
        size_disp = f"{total_size:.2f} B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if total_size < 1024:
                size_disp = f"{total_size:.2f} {unit}"
                break
            total_size /= 1024
            
        self.selection_label.config(text=f"已选中: {count} 个文件 ({size_disp})")

    def show_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def open_file_location(self):
        selected = self.tree.selection()
        if not selected: return
        path = self.tree.item(selected[0])['values'][1]
        try:
            folder = os.path.dirname(path)
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}")

    def unmark_item(self):
        for item in self.tree.selection():
            vals = list(self.tree.item(item)['values'])
            vals[4] = "保留"
            self.tree.item(item, values=vals, tags=("original",))
        self.on_tree_select(None)

    def mark_item(self):
        for item in self.tree.selection():
            vals = list(self.tree.item(item)['values'])
            vals[4] = "重复"
            self.tree.item(item, values=vals, tags=("duplicate",))
        self.on_tree_select(None)

    def select_all_duplicates(self):
        self.tree.selection_remove(self.tree.selection())
        items_to_select = []
        for item in self.tree.get_children():
            if self.tree.item(item)['values'][4] == "重复":
                items_to_select.append(item)
        if items_to_select:
            self.tree.selection_add(items_to_select)
        self.on_tree_select(None)

    def delete_selected(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要清理的文件")
            return

        if not messagebox.askyesno("清理确认", f"确定要将选中的 {len(selected_items)} 个文件移至回收站吗？\n\n注意：这不会永久删除文件，您可以在回收站中找回。"):
            return
        
        # 创建删除进度窗口
        progress_win = tk.Toplevel(self.root)
        progress_win.title("正在清理...")
        progress_win.geometry("400x150")
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        # 设置弹窗图标
        try:
            icon_file = resource_path("icon.ico")
            if os.path.exists(icon_file):
                progress_win.iconbitmap(icon_file)
        except: pass
        
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        progress_win.geometry(f"+{x}+{y}")

        ttk.Label(progress_win, text="正在移动文件到回收站...", font=self.ui_font_normal).pack(pady=10)
        
        p_bar = ttk.Progressbar(progress_win, orient=HORIZONTAL, length=300, mode='determinate', bootstyle="danger-striped")
        p_bar.pack(pady=10)
        p_bar['maximum'] = len(selected_items)
        
        status_var = tk.StringVar(value="准备中...")
        ttk.Label(progress_win, textvariable=status_var, font=self.ui_font_normal).pack(pady=5)
        
        stop_flag = False
        def stop_deletion():
            nonlocal stop_flag
            stop_flag = True
            status_var.set("正在停止...")
            btn_stop.configure(state="disabled")

        btn_stop = ttk.Button(progress_win, text="停止清理", command=stop_deletion, bootstyle="secondary")
        btn_stop.pack(pady=5)

        items_to_process = []
        for item in selected_items:
            raw_path = self.tree.item(item)['values'][1]
            path = os.path.abspath(raw_path)
            items_to_process.append((item, path))
        
        success_count = 0
        errors = []
        processed_count = 0
        
        ui_lock = threading.Lock()
        
        def delete_task(item_data):
            if stop_flag: return None
            
            item_id, file_path = item_data
            
            # 使用 send2trash
            try:
                send2trash(file_path)
                return (True, item_id, file_path, None)
            except Exception as e:
                return (False, item_id, file_path, str(e))

        def run_batch_delete():
            nonlocal success_count, processed_count
            
            # 多线程并发 send2trash
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(delete_task, item): item for item in items_to_process}
                
                for future in concurrent.futures.as_completed(futures):
                    if stop_flag: break
                    
                    try:
                        result = future.result()
                    except Exception:
                        continue
                        
                    if result is None: continue 
                    
                    success, item_id, fpath, err = result
                    
                    with ui_lock:
                        processed_count += 1
                        
                        def update_ui(p=processed_count, t=len(items_to_process)):
                            if not progress_win.winfo_exists(): return
                            p_bar['value'] = p
                            status_var.set(f"已处理: {p} / {t}")
                        
                        self.root.after(0, update_ui)
                        
                        if success:
                            success_count += 1
                            self.root.after(0, lambda i=item_id: self.tree.delete(i))
                        else:
                            errors.append(f"{os.path.basename(fpath)}: {err}")

            self.root.after(0, lambda: progress_win.destroy() if progress_win.winfo_exists() else None)
            self.root.after(0, lambda: self.show_delete_report(success_count, errors, stop_flag))

        threading.Thread(target=run_batch_delete, daemon=True).start()

    def show_delete_report(self, success_count, errors, stopped):
        if stopped:
            messagebox.showwarning("已停止", f"清理已停止。\n成功移至回收站: {success_count} 个文件")
        elif success_count > 0 and not errors:
            messagebox.showinfo("清理完成", f"已成功将 {success_count} 个文件移动至系统回收站。")
        
        if errors:
            error_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n... 以及其他 {len(errors)-5} 个错误"
            messagebox.showerror("部分失败", f"成功: {success_count} 个\n失败: {len(errors)} 个\n\n失败详情:\n{error_msg}")
        
        self.selection_label.config(text="")

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        if col == "size":
            def get_bytes(s):
                try:
                    parts = s.split()
                    if len(parts) != 2: return 0
                    return float(parts[0]) * {'B':1, 'KB':1024, 'MB':1024**2, 'GB':1024**3}.get(parts[1], 1)
                except: return 0
            l.sort(key=lambda x: get_bytes(x[0]), reverse=reverse)
        elif col == "num":
             l.sort(key=lambda x: int(x[0]), reverse=reverse)
        else:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))


# ==========================================
# 程序入口
# ==========================================

if __name__ == "__main__":
    root = ttk.Window(themename="cosmo") 
    app = WxCleanerApp(root)
    root.mainloop()