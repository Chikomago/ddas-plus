import os
import json
import logging
import platform

class CredentialsManager:
    def __init__(self):
        # 根据系统设置不同的保存路径
        if platform.system() == "Darwin":  # macOS
            self.base_dir = os.path.join(os.path.expanduser('~'), 'DDAS')
        else:  # Windows 和其他系统
            self.base_dir = os.getcwd()

        # 确保目录存在
        os.makedirs(self.base_dir, exist_ok=True)

        # 设置文件路径
        self.credentials_file = os.path.join(self.base_dir, 'user.txt')

    def save_credentials(self, username, password):
        """保存账号和密码到 user.txt 文件"""
        try:
            # 读取现有的用户文件内容
            existing_data = []
            if os.path.exists(self.credentials_file):
                with open(self.credentials_file, "r") as f:
                    existing_data = f.readlines()

            # 添加新的账号和密码（使用--分隔符）
            existing_data.append(f"{username}--{password}\n")

            # 写回用户文件
            with open(self.credentials_file, "w") as f:
                f.writelines(existing_data)

            logging.info(f"账号密码已保存到: {self.credentials_file}")
            return True, "账号和密码已保存"
        except Exception as e:
            logging.error(f"保存账号密码失败: {str(e)}")
            return False, f"保存账号密码失败: {str(e)}"

    def load_credentials(self):
        """从 user.txt 文件加载账号和密码"""
        try:
            credentials = []
            if os.path.exists(self.credentials_file):
                with open(self.credentials_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if '--' in line:
                            username, password = line.split('--', 1)
                            credentials.append((username, password))
            else:
                logging.warning("未找到有保存的账号")
            return credentials
        except Exception as e:
            logging.error(f"读取账号密码失败: {str(e)}")
            return []
