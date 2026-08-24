"""Shared native file and directory operations."""

import os
import platform
import subprocess
from tkinter import filedialog


def choose_directory(title="选择目录"):
    return filedialog.askdirectory(title=title) or ""


def choose_excel_file(title="选择Excel文件"):
    return filedialog.askopenfilename(
        title=title,
        filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
    ) or ""


def choose_browser(title="选择Chrome浏览器"):
    system = platform.system()
    if system == "Windows":
        initialdir = "C:/Program Files/Google/Chrome/Application"
        if not os.path.exists(initialdir):
            initialdir = "C:/Program Files (x86)/Google/Chrome/Application"
        filetypes = [("Chrome浏览器", "*.exe")]
    elif system == "Darwin":
        initialdir = "/Applications"
        filetypes = [("浏览器程序", "*.app"), ("所有文件", "*")]
    else:
        initialdir = "/usr/bin"
        filetypes = [("所有文件", "*")]

    path = filedialog.askopenfilename(
        title=title, initialdir=initialdir, filetypes=filetypes,
    ) or ""
    if system == "Darwin" and path.endswith(".app"):
        path = os.path.join(path, "Contents/MacOS/Google Chrome")
    return path


def open_file(path):
    if not path:
        raise ValueError("未选择文件")
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", path], check=False)
    elif system == "Windows":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", path], check=False)


def get_browser_version(path):
    if platform.system() == "Windows":
        import win32api
        info = win32api.GetFileVersionInfo(path, "\\")
        ms, ls = info["FileVersionMS"], info["FileVersionLS"]
        return f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
    output = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT)
    return output.decode("utf-8").strip().split()[-1]
