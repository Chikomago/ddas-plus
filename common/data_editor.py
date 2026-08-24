import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import openpyxl
import os
import logging
import platform
from common.config_schema import validate_headers

class DataEditor:
    def show_data_editor(self, code_entry, field_rows):
        """从 DDAS 字段行打开公共配置编辑器。"""
        try:
            # 查找对应的文件路径
            for row_info in field_rows:
                if row_info['field_entry'] == code_entry:
                    file_path = row_info['file_path']
                    break
            else:
                logging.error("未找到对应的字段行信息")
                messagebox.showerror("错误", "未找到对应的字段行信息")
                return

            self.show_file(file_path)
        except Exception as e:
            logging.error(f"打开数据编辑器时出错: {str(e)}")
            messagebox.showerror("错误", f"打开数据编辑器时出错: {str(e)}")

    def show_file(self, file_path, parent=None):
        """打开 DDAS/PIM 共用的五列 Excel 配置文件。"""
        try:
            if not file_path or not os.path.isfile(file_path):
                messagebox.showerror("错误", "请先选择有效的配置文件", parent=parent)
                return

            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=False)
            sheet = wb.active
            headers = [cell.value for cell in sheet[1]]
            rows = list(sheet.iter_rows(min_row=2, values_only=True))
            wb.close()

            if not validate_headers(headers):
                messagebox.showerror(
                    "配置格式不兼容",
                    "配置文件应包含：选项名（或选项值名称）、PC选项值、移动选项值、PC图路径、移动图路径",
                    parent=parent,
                )
                return

            columns = tuple(str(value) for value in headers[:5])
            logging.info(f"打开公共配置编辑器: {file_path}")

            # 创建数据编辑器窗口
            editor_window = tk.Toplevel(parent)
            editor_window.title(f"数据编辑器 - {file_path}")
            editor_window.geometry("800x600")

            # 创建主框架
            main_frame = ttk.Frame(editor_window)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # 创建Treeview来显示数据
            tree = ttk.Treeview(main_frame, columns=columns, show="headings", selectmode="browse")
            tree.pack(fill=tk.BOTH, expand=True)

            # 设置列标题
            for col in columns:
                tree.heading(col, text=col)

            for row in rows:
                tree.insert("", "end", values=row[:5])

            # 添加前后缀输入框
            prefix_frame = ttk.Frame(main_frame)
            prefix_frame.pack(fill=tk.X, pady=5)

            ttk.Label(prefix_frame, text="前缀:").pack(side=tk.LEFT)
            prefix_entry = ttk.Entry(prefix_frame, width=20)
            prefix_entry.pack(side=tk.LEFT, padx=5)

            ttk.Label(prefix_frame, text="后缀:").pack(side=tk.LEFT)
            suffix_entry = ttk.Entry(prefix_frame, width=20)
            suffix_entry.pack(side=tk.LEFT, padx=5)

            # 列选择框架
            column_frame = ttk.Frame(prefix_frame)
            column_frame.pack(side=tk.LEFT, padx=10)

            # 创建列选择复选框
            column_vars = {}
            for col in columns[:3]:  # 仅对前三列应用前后缀
                var = tk.BooleanVar(value=False)
                column_vars[col] = var
                ttk.Checkbutton(
                    column_frame,
                    text=col,
                    variable=var
                ).pack(side=tk.LEFT, padx=5)

            # 添加按钮框架
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(pady=10)

            # 添加插入前后缀按钮
            def apply_prefix_suffix():
                prefix = prefix_entry.get()
                suffix = suffix_entry.get()

                if not prefix and not suffix:
                    messagebox.showwarning("警告", "请至少输入前缀或后缀")
                    return

                selected_columns = [col for col, var in column_vars.items() if var.get()]

                if not selected_columns:
                    messagebox.showwarning("警告", "请至少选择一列")
                    return

                items = tree.get_children()
                if not items:
                    messagebox.showwarning("警告", "没有可修改的数据")
                    return

                for item in items:
                    values = list(tree.item(item)['values'])
                    for col in selected_columns:
                        col_idx = tree['columns'].index(col)
                        current_value = str(values[col_idx])
                        new_value = f"{prefix}{current_value}{suffix}"
                        values[col_idx] = new_value
                    tree.item(item, values=values)

                messagebox.showinfo("成功", "已应用前后缀")

            ttk.Button(button_frame, text="应用前后缀", command=apply_prefix_suffix).pack(side=tk.LEFT, padx=5)

            # 添加保存按钮
            save_button = ttk.Button(button_frame, text="保存", command=lambda: self.save_data(tree, file_path))
            save_button.pack(side=tk.LEFT, padx=5)

            # 添加右键菜单
            def create_context_menu(tree):
                menu = tk.Menu(tree, tearoff=0)
                menu.add_command(label="删除行", command=lambda: self.delete_selected_row(tree))
                menu.add_command(label="添加新行", command=lambda: self.add_new_row(tree))
                menu.add_command(label="编辑行", command=lambda: self.edit_selected_row(tree))

                def show_context_menu(event):
                    try:
                        menu.tk_popup(event.x_root, event.y_root)
                    finally:
                        menu.grab_release()

                tree.bind("<Button-3>", show_context_menu)

            create_context_menu(tree)

        except Exception as e:
            logging.error(f"打开数据编辑器时出错: {str(e)}")
            messagebox.showerror("错误", f"打开数据编辑器时出错: {str(e)}")

    def save_data(self, tree, file_path):
        """保存数据到Excel文件"""
        try:
            # 获取所有数据
            items = tree.get_children()
            if not items:
                messagebox.showerror("错误", "没有可保存的数据")
                return

            # 加载工作簿
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active

            # 清空现有数据
            for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row, max_col=sheet.max_column):
                for cell in row:
                    cell.value = None

            # 写入新数据
            for i, item in enumerate(items, start=2):  # 从第2行开始写入（跳过表头）
                values = tree.item(item)['values']
                for j, value in enumerate(values, start=1):
                    sheet.cell(row=i, column=j, value=value)

            # 保存文件
            wb.save(file_path)
            wb.close()

            messagebox.showinfo("成功", "数据已保存")
            logging.info(f"数据已保存到文件: {file_path}")

        except Exception as e:
            error_msg = f"保存数据失败: {str(e)}"
            logging.error(error_msg)
            messagebox.showerror("错误", error_msg)

    def delete_selected_row(self, tree):
        """删除选中的行"""
        selected_item = tree.selection()
        if not selected_item:
            messagebox.showwarning("警告", "请先选择要删除的行")
            return
        tree.delete(selected_item)

    def add_new_row(self, tree):
        """添加新行"""
        new_window = tk.Toplevel()
        new_window.title("添加新行")
        new_window.geometry("400x300")

        entries = []
        for col in tree['columns']:
            frame = ttk.Frame(new_window)
            frame.pack(fill=tk.X, pady=5)

            ttk.Label(frame, text=col).pack(side=tk.LEFT)
            entry = ttk.Entry(frame, width=30)
            entry.pack(side=tk.LEFT, padx=5)
            entries.append(entry)

        def add_row():
            values = [entry.get() for entry in entries]
            tree.insert('', 'end', values=values)
            new_window.destroy()

        ttk.Button(new_window, text="添加", command=add_row).pack(pady=10)

    def edit_selected_row(self, tree):
        """编辑选中的行"""
        selected_item = tree.selection()
        if not selected_item:
            messagebox.showwarning("警告", "请先选择要编辑的行")
            return

        values = tree.item(selected_item)['values']

        edit_window = tk.Toplevel()
        edit_window.title("编辑行")
        edit_window.geometry("350x220")

        entries = []
        for i, col in enumerate(tree['columns']):
            frame = ttk.Frame(edit_window)
            frame.pack(fill=tk.X, pady=5)

            ttk.Label(frame, text=col).pack(side=tk.LEFT)
            entry = ttk.Entry(frame, width=30)
            entry.insert(0, values[i])
            entry.pack(side=tk.LEFT, padx=5)
            entries.append(entry)

        def save_changes():
            new_values = [entry.get() for entry in entries]
            tree.item(selected_item, values=new_values)
            edit_window.destroy()

        ttk.Button(edit_window, text="保存", command=save_changes).pack(pady=10)
