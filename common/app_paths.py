"""User-data directory independent of the executable/working directory."""
import os
import platform
from pathlib import Path


def app_data_dir():
    if platform.system() == 'Darwin':
        return Path.home() / 'Library/Application Support/DDAS PLUS'
    if platform.system() == 'Windows':
        return Path(os.environ.get('APPDATA', str(Path.home()/'AppData/Roaming'))) / 'DDAS PLUS'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'ddas-plus'
