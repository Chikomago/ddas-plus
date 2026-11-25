
import logging
import time
import platform
import os
import subprocess
import webbrowser
import shutil
from pathlib import Path
from common.app_paths import app_data_dir
from DrissionPage import ChromiumPage, ChromiumOptions
from threading import Thread


def installed_chrome_path():
    """Locate the regular installed Chrome, never a downloaded testing/headless binary."""
    if platform.system() == 'Darwin':
        candidates = [Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                      Path.home()/'Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    elif platform.system() == 'Windows':
        candidates = [Path(os.environ.get(name, default))/'Google/Chrome/Application/chrome.exe'
                      for name,default in [('PROGRAMFILES','C:/Program Files'),
                          ('PROGRAMFILES(X86)','C:/Program Files (x86)'),
                          ('LOCALAPPDATA',str(Path.home()/'AppData/Local'))]]
    else:
        candidates = [Path(found) for name in ('google-chrome','google-chrome-stable')
                      if (found := shutil.which(name))]
    return str(next((path for path in candidates if path.is_file()), candidates[0] if candidates else Path('/usr/bin/google-chrome')))


def create_browser(chrome_path=None, *, mute=True, auto_port=False, load_timeout=30):
    """Visible installed Chrome with a persistent, plugin-owned profile."""
    path = Path(chrome_path or installed_chrome_path()).expanduser()
    if not path.is_file():
        raise ValueError('未找到已安装的 Chrome，请在设置中选择电脑上的 Google Chrome 浏览器')
    if any(marker in str(path).lower() for marker in ('for testing','chrome-for-testing','chrome-headless-shell')):
        raise ValueError('请选择正常安装的 Google Chrome，不要选择 Chrome for Testing 或无头测试浏览器')
    options = ChromiumOptions()
    options.set_browser_path(str(path))
    options.headless(False)
    options.remove_argument('--enable-automation')
    if mute:
        options.mute(True)
    if auto_port:
        # The explicit browser test uses an isolated profile and cannot close the task browser.
        options.auto_port(True)
    else:
        profile = app_data_dir() / 'browser-profile'
        profile.mkdir(parents=True, exist_ok=True)
        options.set_user_data_path(str(profile))
        options.set_local_port(19333)
    page = ChromiumPage(addr_or_opts=options)
    if load_timeout is not None:
        page.set.load_mode.load_timeout = load_timeout
    return page


def close_browser(page, *, keep_open=False, log=logging.info):
    """统一关闭浏览器；返回清理后的引用。"""
    if page is None:
        return None
    if keep_open:
        log("保留浏览器")
        return page
    try:
        page.quit()
        log("关闭浏览器")
    except Exception as error:
        logging.debug("关闭浏览器时出现异常: %s", error)
    return None


def open_chrome_download():
    """打开 Chrome 官方下载页。浏览器获取、初始化和测试统一由本模块负责。"""
    webbrowser.open("https://www.google.cn/chrome/")


# Windows系统才导入winreg
if platform.system() == "Windows":
    import winreg

class BrowserInitializer:
    def __init__(self):
        self.browser = None
        self.options = ChromiumOptions()

        # 设置一些默认配置
        self.options.mute(True)  # 静音

    def get_default_chrome_path(self):
        return installed_chrome_path()

    def get_chrome_version(self):
        """获取当前安装的 Chrome 版本"""
        try:
            if platform.system() == "Windows":
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                    version = winreg.QueryValueEx(key, "version")[0]
                    winreg.CloseKey(key)
                    return version
                except WindowsError:
                    try:
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome")
                        version = winreg.QueryValueEx(key, "Version")[0]
                        winreg.CloseKey(key)
                        return version
                    except WindowsError:
                        return None
            elif platform.system() == "Darwin":  # macOS
                try:
                    process = subprocess.Popen(
                        ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    output, _ = process.communicate()
                    version = output.decode('utf-8').strip().split()[-1]
                    return version
                except:
                    return None
            else:  # Linux
                try:
                    process = subprocess.Popen(['google-chrome', '--version'],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    output, _ = process.communicate()
                    version = output.decode('utf-8').strip().split()[-1]
                    return version
                except:
                    return None
        except Exception as e:
            logging.error(f"获取 Chrome 版本失败: {str(e)}")
            return None

    def initialize_browser(self, chrome_path=None):
        """初始化浏览器"""
        try:
            if not chrome_path:
                chrome_path = self.get_default_chrome_path()
            self.browser = create_browser(chrome_path, mute=True, auto_port=True, load_timeout=30)
            return True
        except Exception as e:
            logging.error(f"初始化浏览器失败: {str(e)}")
            return False

    def close_browser(self):
        """关闭浏览器"""
        self.browser = close_browser(self.browser)

    def test_browser(self, chrome_path, progress_callback=None):
        """测试Chrome浏览器"""
        try:
            if not chrome_path or not os.path.exists(chrome_path):
                return False, "请先选择正确的Chrome浏览器路径"

            # 初始化浏览器
            if not self.initialize_browser(chrome_path):
                logging.error("浏览器初始化失败")
                return False, "浏览器初始化失败"

            try:
                # 访问测试页面
                logging.info("浏览器初始化成功")
                logging.info("正在访问测试页面...")
                if progress_callback:
                    progress_callback("正在访问测试页面...")
                self.browser.get('https://www.baidu.com')

                # 等待几秒
                if progress_callback:
                    logging.info("测试成功，即将关闭...")
                    progress_callback("测试成功，即将关闭...")
                time.sleep(3)

                # 关闭浏览器
                self.close_browser()
                logging.info("Chrome浏览器调用正常，可以正常任务")
                return True, "Chrome浏览器调用正常，可以正常任务"
            except Exception as e:
                self.close_browser()  # 确保出错时也关闭浏览器
                error_msg = f"测试过程中出错: {str(e)}"
                logging.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"测试Chrome浏览器失败: {str(e)}"
            logging.error(error_msg)
            return False, error_msg

    def start_test_thread(self, chrome_path, progress_callback=None, complete_callback=None):
        """在新线程中开始测试"""
        def test_thread():
            success, message = self.test_browser(chrome_path, progress_callback)
            if complete_callback:
                complete_callback(success, message)

        Thread(target=test_thread, daemon=True).start()
