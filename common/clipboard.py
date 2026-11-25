"""Text-only system clipboard access for spreadsheet context menus."""
import platform
import shutil
import subprocess


def clipboard_text(value=None):
    system = platform.system()
    if system == 'Windows':
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if value is None:
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT) else ''
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(value, win32clipboard.CF_UNICODETEXT)
            return True
        finally:
            win32clipboard.CloseClipboard()
    if system == 'Darwin':
        command = ['pbpaste'] if value is None else ['pbcopy']
    elif shutil.which('wl-paste' if value is None else 'wl-copy'):
        command = ['wl-paste', '--no-newline'] if value is None else ['wl-copy']
    elif shutil.which('xclip'):
        command = ['xclip', '-selection', 'clipboard'] + (['-o'] if value is None else [])
    else:
        raise RuntimeError('系统剪贴板不可用，请使用键盘快捷键复制粘贴')
    result = subprocess.run(command, input=value, text=True, encoding='utf-8', capture_output=True, timeout=3, check=True)
    return result.stdout if value is None else True
