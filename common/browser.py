
import logging
import time
import platform
import os
import subprocess
import webbrowser
from DrissionPage import ChromiumPage, ChromiumOptions
from threading import Thread


def create_browser(chrome_path=None, *, mute=True, auto_port=False, load_timeout=30):
    """统一创建 DrissionPage 浏览器实例，供深绘和 PIM 共用。"""
    options = ChromiumOptions()
    if chrome_path:
        options.set_browser_path(chrome_path)
    if mute:
        options.mute(True)
    options.set_pref('credentials_enable_service', False)
    if auto_port:
        options.auto_port(True)
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
        self.options.set_pref('credentials_enable_service', False)  # 禁用保存密码提示

    def get_default_chrome_path(self):
        """获取系统默认的Chrome浏览器路径"""
        if platform.system() == "Windows":
            return "C:/Program Files/Google/Chrome/Application/chrome.exe"
        elif platform.system() == "Darwin":  # macOS
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        else:  # Linux
            return "/usr/bin/google-chrome"

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
