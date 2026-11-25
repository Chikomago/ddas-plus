import os
import json
import logging
import platform
from common.browser import BrowserInitializer
from common.app_paths import app_data_dir
from pathlib import Path
import uuid
import copy

class Settings:
    def __init__(self):
        self.base_dir = str(app_data_dir())

        # 创建必要的子目录
        self.logs_dir = os.path.join(self.base_dir, 'logs')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self._previous_configs_dir = os.path.join(self.base_dir, 'configs')
        self.configs_dir = (str(Path.home() / 'DDAS' / 'configs')
                            if platform.system() in ('Darwin', 'Windows') else self._previous_configs_dir)

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

            destination = Path(self.settings_file)
            temporary = destination.with_name(f'.settings.{uuid.uuid4().hex}.tmp')
            try:
                temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=4), encoding='utf-8')
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        except Exception:
            logging.exception("保存设置失败")
            raise

    def _merge_settings(self, saved_settings):
        if not isinstance(saved_settings, dict):
            raise ValueError("设置文件格式不正确")
        merged = copy.deepcopy(self.settings)
        for key, value in saved_settings.items():
            if key in ("chrome_path", "log_export_path", "task_result_path", "config_path") and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"设置项 {key} 必须是有效路径")
            if isinstance(merged.get(key), dict):
                if not isinstance(value, dict):
                    raise ValueError(f"设置项 {key} 格式不正确")
                merged[key].update(value)
            else:
                merged[key] = value
        self.settings = merged

    def load_settings(self):
        """从 settings.json 文件加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                self._merge_settings(saved_settings)
                if (self.configs_dir != self._previous_configs_dir and
                        self.settings["config_path"] == self._previous_configs_dir):
                    self.settings["config_path"] = self.configs_dir
                    self.save_settings()
            elif os.path.exists(self.legacy_settings_file):
                with open(self.legacy_settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                # 迁移浏览器和业务设置，但采用新的统一默认目录
                for key in ('log_export_path', 'task_result_path', 'config_path'):
                    saved_settings.pop(key, None)
                self._merge_settings(saved_settings)
                self.save_settings()
            else:
                # 如果设置文件不存在，创建默认目录
                for path in ['log_export_path', 'task_result_path', 'config_path']:
                    os.makedirs(self.settings[path], exist_ok=True)
                # 保存默认设置
                self.save_settings()
        except Exception as e:
            logging.error(f"加载设置失败: {str(e)}")
