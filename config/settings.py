"""
全局配置
"""

import os
import sys

APP_NAME = "数据处理工具"
APP_VERSION = "1.2"


def get_base_path() -> str:
    """获取应用根目录，兼容 PyInstaller 打包"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_path()
UI_DIR = os.path.join(BASE_DIR, "ui")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")
THEMES_DIR = os.path.join(BASE_DIR, "themes")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
