"""
数据处理工具 - 主入口
"""

import sys
import os



from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from views.main_window import MainWindow


def setup_environment():
    """配置运行环境，兼容 Nuitka 打包后的路径"""
    # 1. 获取当前程序实际运行的路径（解压后的临时目录或脚本目录）
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        # Nuitka onefile 模式下，__file__ 指向解压后的临时目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

    # 2. 将该目录加入 DLL 搜索路径 (关键步骤)
    if hasattr(os, 'add_dll_directory'):
        # 允许加载该目录下的所有 DLL
        os.add_dll_directory(current_dir)
    
    # 兼容老旧的 DLL 加载方式
    os.environ["PATH"] = current_dir + os.pathsep + os.environ.get("PATH", "")

    # 3. 设置工作目录 (根据你的需要)
    # 如果你的外部配置文件和 exe 在一起，才需要 chdir 到 sys.executable 路径
    # 如果你的资源文件（themes/resources）是打包在内部的，建议 chdir 到 current_dir
    os.chdir(current_dir)

    # 4. 其他配置
    os.environ["QT_FONT_DPI"] = "96"
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dataproc.tool.v1")
    except Exception:
        pass


def main():
    setup_environment()

    app = QApplication(sys.argv)
    app.setApplicationName("数据处理工具")
    app.setStyle("Fusion")

    for candidate in [
        os.path.join("resources", "icons", "app.svg"),
        os.path.join("resources", "icons", "app.ico"),
    ]:
        if os.path.exists(candidate):
            app.setWindowIcon(QIcon(candidate))
            break

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
