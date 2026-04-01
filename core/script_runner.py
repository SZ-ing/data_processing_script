"""
脚本运行器 —— 在子线程中执行注册表定义的脚本函数，
将 stdout/stderr 实时转发给 UI 日志区。
支持用户主动终止正在运行的脚本。
"""

import importlib
import sys
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from core.logger import get_logger

logger = get_logger(__name__)


class StopRequested(Exception):
    """用户请求终止脚本时抛出，由 _StreamRedirector 在 write() 中触发。"""


class _StreamRedirector:
    """将 write() 调用转发为 Qt Signal，识别 \\r 实现进度条原地刷新。
    每次 write 时检查停止标志，实现对脚本循环的快速中断。"""

    def __init__(self, signal_append, signal_overwrite, stop_event: threading.Event):
        self._sig_append = signal_append
        self._sig_overwrite = signal_overwrite
        self._stop = stop_event

    def write(self, text):
        if self._stop.is_set():
            raise StopRequested("用户终止")
        if not text:
            return
        if "\r" in text and "\n" not in text:
            line = text.replace("\r", "")
            if line:
                self._sig_overwrite.emit(line)
        else:
            self._sig_append.emit(text.replace("\r", ""))

    def flush(self):
        pass


class ScriptWorker(QThread):
    """在独立线程中运行脚本函数"""

    log_signal = Signal(str)
    log_overwrite_signal = Signal(str)
    finished_signal = Signal(bool, str)  # (success, message)

    def __init__(self, module_path: str, func_name: str, kwargs: dict,
                 wrapper: str | None = None):
        super().__init__()
        self.module_path = module_path
        self.func_name = func_name
        self.kwargs = kwargs
        self.wrapper_name = wrapper
        self._stop_event = threading.Event()

    def request_stop(self):
        self._stop_event.set()

    def run(self):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        redirector = _StreamRedirector(
            self.log_signal, self.log_overwrite_signal, self._stop_event
        )
        sys.stdout = redirector
        sys.stderr = redirector

        try:
            module = importlib.import_module(self.module_path)
            importlib.reload(module)

            if self.wrapper_name and hasattr(module, self.wrapper_name):
                func = getattr(module, self.wrapper_name)
            else:
                func = getattr(module, self.func_name)

            func(**self.kwargs)
            self.finished_signal.emit(True, "执行完成")
        except StopRequested:
            self.finished_signal.emit(False, "已被用户终止")
        except Exception:
            if self._stop_event.is_set():
                self.finished_signal.emit(False, "已被用户终止")
            else:
                self.log_signal.emit("\n" + traceback.format_exc())
                self.finished_signal.emit(False, "执行出错")
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
