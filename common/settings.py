import os
import json
import logging
import platform
from common.browser import BrowserInitializer

class Settings:
    def __init__(self):
        # 使用系统用户数据目录，避免设置和结果依赖程序启动位置
        if platform.system() == "Darwin":
            self.base_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'DDAS PLUS')
        elif platform.system() == "Windows":
            app_data = os.environ.get('APPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming'))
            self.base_dir = os.path.join(app_data, 'DDAS PLUS')
        else:
            data_home = os.environ.get('XDG_DATA_HOME', os.path.join(os.path.expanduser('~'), '.local', 'share'))
            self.base_dir = os.path.join(data_home, 'ddas-plus')

        # 创建必要的子目录
        self.logs_dir = os.path.join(self.base_dir, 'logs')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.configs_dir = os.path.join(self.base_dir, 'configs')

        # 确保所有目录存在
        for directory in [self.base_dir, self.logs_dir, self.results_dir, self.configs_dir]:
            os.makedirs(directory, exist_ok=True)

        # 创建 BrowserInitializer 实例来获取默认浏览器路径
        browser_init = BrowserInitializer()
        default_chrome_path = browser_init.get_default_chrome_path()

        self.settings = {
            'log_export_path': self.logs_dir,      # 日志导出路径
            'task_result_path': self.results_dir,  # 任务结果导出路径
            'config_path': self.configs_dir,       # 配置文件路径
            'chrome_path': default_chrome_path,    # 使用系统默认的Chrome路径
            'pim_settings': {
                'pixel_size': '750',               # PIM 默认像素大小
            },
            'browser_settings': {
                'auto_close': False,               # 任务完成后是否自动关闭浏览器
            }
        }

        # 设置文件路径
        self.settings_file = os.path.join(self.base_dir, 'settings.json')
        self.legacy_settings_file = os.path.join(os.path.expanduser('~'), 'DDAS', 'settings.json')

    def save_settings(self):
        """保存设置到 settings.json 文件"""
        try:
            # 确保设置文件所在目录存在
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"保存设置失败: {str(e)}")

    def load_settings(self):
        """从 settings.json 文件加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                    # 更新设置，保留默认值
                    self.settings.update(saved_settings)
            elif os.path.exists(self.legacy_settings_file):
                with open(self.legacy_settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                # 迁移浏览器和业务设置，但采用新的统一默认目录
                for key in ('log_export_path', 'task_result_path', 'config_path'):
                    saved_settings.pop(key, None)
                self.settings.update(saved_settings)
                self.save_settings()
            else:
                # 如果设置文件不存在，创建默认目录
                for path in ['log_export_path', 'task_result_path', 'config_path']:
                    os.makedirs(self.settings[path], exist_ok=True)
                # 保存默认设置
                self.save_settings()
        except Exception as e:
            logging.error(f"加载设置失败: {str(e)}")
