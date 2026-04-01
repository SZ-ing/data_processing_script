"""
数据处理工具 - 主入口
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from views.main_window import MainWindow


def setup_environment():
    """配置运行环境，兼容打包后的路径"""
    if getattr(sys, "frozen", False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

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
        os.path.join("icons", "数据处理.png"),
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
