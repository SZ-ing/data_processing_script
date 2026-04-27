"""
主窗口 —— 无边框 PyDracula 风格，自定义标题栏 + 侧边栏导航 + 脚本页面堆叠
"""

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLabel, QStackedWidget,
    QGraphicsDropShadowEffect, QScrollArea, QSizeGrip, QSystemTrayIcon,
    QMenu, QApplication,
)
from PySide6.QtCore import Qt, Slot, QPoint, QSize, QRect
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QAction, QCloseEvent

from config.settings import APP_NAME, APP_VERSION, RESOURCES_DIR
from scripts._registry import SCRIPT_REGISTRY, get_groups
from views.script_page import ScriptPage
from core.script_runner import ScriptWorker
from core.logger import get_logger
logger = get_logger(__name__)

MENU_WIDTH = 236
GRIP_SIZE = 8
CHROME_ICON_SIZE = QSize(16, 16)

MENU_SELECTED_STYLE = (
    "border-left: 22px solid qlineargradient("
    "spread:pad, x1:0.034, y1:0, x2:0.216, y2:0, "
    "stop:0.499 rgba(255, 121, 198, 255), stop:0.5 rgba(85, 170, 255, 0));"
    "background-color: rgb(40, 44, 52);"
)


class _EdgeGrip(QWidget):
    """无边框窗口四边拉伸手柄。"""

    def __init__(self, parent: QMainWindow, edge: str):
        super().__init__(parent)
        self._window = parent
        self._edge = edge
        self._dragging = False
        self._start_global = QPoint()
        self._start_geo = parent.geometry()
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)
        if edge in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeVerCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self._window._is_maximized:
            self._dragging = True
            self._start_global = event.globalPosition().toPoint()
            self._start_geo = self._window.geometry()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._dragging:
            super().mouseMoveEvent(event)
            return

        delta = event.globalPosition().toPoint() - self._start_global
        # 每次移动都从按下时的几何副本计算，避免累计改写导致跳动。
        geo = QRect(self._start_geo)
        min_w = self._window.minimumWidth()
        min_h = self._window.minimumHeight()

        if self._edge == "left":
            new_left = min(geo.right() - min_w + 1, geo.x() + delta.x())
            geo.setLeft(new_left)
        elif self._edge == "right":
            geo.setWidth(max(min_w, geo.width() + delta.x()))
        elif self._edge == "top":
            new_top = min(geo.bottom() - min_h + 1, geo.y() + delta.y())
            geo.setTop(new_top)
        elif self._edge == "bottom":
            geo.setHeight(max(min_h, geo.height() + delta.y()))

        self._window.setGeometry(geo)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 780)
        self.setMinimumSize(920, 580)

        self._is_maximized = False
        self._drag_pos: QPoint | None = None
        self._pages: dict[str, ScriptPage] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._worker: ScriptWorker | None = None
        self._running_page: ScriptPage | None = None
        self._running_task_name: str = ""
        self._force_quit = False
        self._tray_icon: QSystemTrayIcon | None = None

        self._setup_frameless()
        self._build_ui()
        self._setup_resize_grips()
        self._setup_tray()
        self._apply_theme()
        self._connect_signals()

        first_entry = next((e for e in SCRIPT_REGISTRY if not e.get("hidden")), None)
        if first_entry:
            self._switch_page(first_entry["id"])

    # ══════════════════════════════════════════════════
    #  无边框配置
    # ══════════════════════════════════════════════════

    def _setup_frameless(self):
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def _chrome_icon(self, filename: str) -> QIcon:
        path = os.path.join(RESOURCES_DIR, "icons", "window", filename)
        return QIcon(path) if os.path.isfile(path) else QIcon()

    def _app_icon(self) -> QIcon:
        for candidate in (
            os.path.join(RESOURCES_DIR, "icons", "app.ico"),
            os.path.join(RESOURCES_DIR, "icons", "app.svg"),
        ):
            if os.path.isfile(candidate):
                return QIcon(candidate)
        return self.windowIcon()

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        tray = QSystemTrayIcon(self)
        tray.setIcon(self._app_icon())
        tray.setToolTip(APP_NAME)

        menu = QMenu(self)
        action_show = QAction("显示主窗口", self)
        action_quit = QAction("退出", self)
        action_show.triggered.connect(lambda *_: self._restore_from_tray())
        action_quit.triggered.connect(lambda *_: self._quit_from_tray())
        menu.addAction(action_show)
        menu.addSeparator()
        menu.addAction(action_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray
        self._update_tray_tooltip()

    def _setup_resize_grips(self):
        """四角/四边缩放手柄"""
        self._grips = []
        for _ in range(4):
            grip = QSizeGrip(self)
            grip.setFixedSize(GRIP_SIZE, GRIP_SIZE)
            grip.setStyleSheet("background: transparent;")
            self._grips.append(grip)
        self._edge_grips = {
            "left": _EdgeGrip(self, "left"),
            "right": _EdgeGrip(self, "right"),
            "top": _EdgeGrip(self, "top"),
            "bottom": _EdgeGrip(self, "bottom"),
        }
        self._update_grip_positions()

    def _update_grip_positions(self):
        s = GRIP_SIZE
        self._grips[0].move(0, 0)                                     # top-left
        self._grips[1].move(self.width() - s, 0)                      # top-right
        self._grips[2].move(0, self.height() - s)                     # bottom-left
        self._grips[3].move(self.width() - s, self.height() - s)      # bottom-right
        self._edge_grips["top"].setGeometry(s, 0, max(0, self.width() - 2 * s), s)
        self._edge_grips["bottom"].setGeometry(
            s, self.height() - s, max(0, self.width() - 2 * s), s
        )
        self._edge_grips["left"].setGeometry(0, s, s, max(0, self.height() - 2 * s))
        self._edge_grips["right"].setGeometry(
            self.width() - s, s, s, max(0, self.height() - 2 * s)
        )

    # ══════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("styleSheet")
        self.setCentralWidget(central)

        self.app_margins = QVBoxLayout(central)
        self.app_margins.setContentsMargins(10, 10, 10, 10)
        self.app_margins.setSpacing(0)

        self.bg_app = QFrame()
        self.bg_app.setObjectName("bgApp")
        self.app_margins.addWidget(self.bg_app)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(17)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.bg_app.setGraphicsEffect(shadow)

        app_layout = QHBoxLayout(self.bg_app)
        app_layout.setContentsMargins(0, 0, 0, 0)
        app_layout.setSpacing(0)

        # ── 左侧栏（固定宽度） ──
        self.left_menu = QFrame()
        self.left_menu.setObjectName("leftMenuBg")
        self.left_menu.setFixedWidth(MENU_WIDTH)
        app_layout.addWidget(self.left_menu)

        left_layout = QVBoxLayout(self.left_menu)
        left_layout.setContentsMargins(0, 0, 0, 8)
        left_layout.setSpacing(0)

        top_logo = QFrame()
        top_logo.setObjectName("topLogoInfo")
        top_logo.setMinimumHeight(50)
        top_logo.setMaximumHeight(50)
        logo_layout = QHBoxLayout(top_logo)
        logo_layout.setContentsMargins(16, 0, 0, 0)
        self.title_label = QLabel("DataProc")
        self.title_label.setObjectName("titleLeftApp")
        self.title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        logo_layout.addWidget(self.title_label)
        sub_title = QLabel(f"{APP_NAME} v{APP_VERSION}")
        sub_title.setObjectName("titleLeftDescription")
        sub_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        logo_layout.addWidget(sub_title)
        logo_layout.addStretch()
        left_layout.addWidget(top_logo)

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.nav_container = QWidget()
        self.nav_container.setObjectName("topMenu")
        self.nav_container.setStyleSheet("background: transparent;")
        self.nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(0, 8, 0, 8)
        self.nav_layout.setSpacing(0)

        self._populate_nav()
        self.nav_layout.addStretch()

        nav_scroll.setWidget(self.nav_container)
        left_layout.addWidget(nav_scroll, 1)

        # ── 右侧内容区 ──
        content_box = QFrame()
        content_box.setObjectName("contentBox")
        app_layout.addWidget(content_box)

        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ── 自定义标题栏 ──
        self.title_bar = QFrame()
        self.title_bar.setObjectName("contentTopBg")
        self.title_bar.setMinimumHeight(45)
        self.title_bar.setMaximumHeight(45)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(15, 0, 8, 0)
        title_bar_layout.setSpacing(0)

        self.top_title = QLabel(APP_NAME)
        self.top_title.setObjectName("titleRightInfo")
        title_font = QFont("Segoe UI", 10)
        self.top_title.setFont(title_font)
        title_bar_layout.addWidget(self.top_title)
        title_bar_layout.addStretch()

        btn_box = QFrame()
        btn_box.setObjectName("rightButtons")
        btn_box.setMaximumWidth(150)
        btn_box_layout = QHBoxLayout(btn_box)
        btn_box_layout.setContentsMargins(0, 0, 0, 0)
        btn_box_layout.setSpacing(2)

        self.btn_minimize = QPushButton()
        self.btn_minimize.setObjectName("minimizeAppBtn")
        self.btn_minimize.setFixedSize(44, 32)
        self.btn_minimize.setCursor(Qt.PointingHandCursor)
        self.btn_minimize.setToolTip("最小化")
        self.btn_minimize.setIcon(self._chrome_icon("win_minimize.svg"))
        self.btn_minimize.setIconSize(CHROME_ICON_SIZE)

        self.btn_maximize = QPushButton()
        self.btn_maximize.setObjectName("maximizeRestoreAppBtn")
        self.btn_maximize.setFixedSize(44, 32)
        self.btn_maximize.setCursor(Qt.PointingHandCursor)
        self.btn_maximize.setToolTip("最大化")
        self._ico_maximize = self._chrome_icon("win_maximize.svg")
        self._ico_restore = self._chrome_icon("win_restore.svg")
        self.btn_maximize.setIcon(self._ico_maximize)
        self.btn_maximize.setIconSize(CHROME_ICON_SIZE)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("closeAppBtn")
        self.btn_close.setFixedSize(44, 32)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setToolTip("关闭")
        self.btn_close.setIcon(self._chrome_icon("win_close.svg"))
        self.btn_close.setIconSize(CHROME_ICON_SIZE)

        btn_box_layout.addWidget(self.btn_minimize)
        btn_box_layout.addWidget(self.btn_maximize)
        btn_box_layout.addWidget(self.btn_close)
        title_bar_layout.addWidget(btn_box)

        content_layout.addWidget(self.title_bar)

        # ── 标题栏拖拽 / 双击最大化 ──
        self.title_bar.mousePressEvent = self._title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self._title_bar_mouse_move
        self.title_bar.mouseDoubleClickEvent = lambda e: self._toggle_maximize()

        # Pages stack
        self.pages = QStackedWidget()
        self.pages.setObjectName("pagesContainer")
        content_layout.addWidget(self.pages)

        self._create_pages()

        # Bottom bar
        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        bottom_bar.setMinimumHeight(26)
        bottom_bar.setMaximumHeight(26)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 0, 10, 0)
        credits_label = QLabel(
            f"{APP_NAME} v{APP_VERSION} 本软件为个人学习、研究使用软件，不得用于商业及非法用途。"
        )
        credits_label.setStyleSheet("color: rgb(113, 126, 149); font-size: 11px;")
        bottom_layout.addWidget(credits_label)
        bottom_layout.addStretch()

        self.size_grip_frame = QFrame()
        self.size_grip_frame.setObjectName("frameSizeGrip")
        self.size_grip_frame.setFixedSize(20, 20)
        self.bottom_size_grip = QSizeGrip(self.size_grip_frame)
        self.bottom_size_grip.setStyleSheet(
            "width: 20px; height: 20px; margin: 0px; padding: 0px;"
        )
        bottom_layout.addWidget(self.size_grip_frame)

        content_layout.addWidget(bottom_bar)

    # ── 侧边栏导航按钮 ──

    def _populate_nav(self):
        groups = get_groups()
        for group_name, entries in groups.items():
            header = QLabel(f"  {group_name}")
            header.setObjectName("navGroupHeader")
            header.setMinimumHeight(32)
            header.setStyleSheet(
                "color: rgb(140, 150, 170); "
                "font: 63 9pt 'Inter', 'Segoe UI Variable Display', 'Segoe UI'; "
                "padding-left: 16px; padding-top: 10px;"
            )
            self.nav_layout.addWidget(header)

            for entry in entries:
                btn = QPushButton(entry["name"])
                btn.setObjectName(f"nav_{entry['id']}")
                btn.setMinimumHeight(42)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setProperty("script_id", entry["id"])
                icon_path = os.path.join(
                    RESOURCES_DIR, "icons", "nav", f"{entry['id']}.svg"
                )
                if os.path.isfile(icon_path):
                    btn.setIcon(QIcon(icon_path))
                    btn.setIconSize(QSize(22, 22))
                btn.clicked.connect(lambda *_, sid=entry["id"]: self._switch_page(sid))
                self.nav_layout.addWidget(btn)
                self._nav_buttons[entry["id"]] = btn

    # ── 脚本页面 ──

    def _create_pages(self):
        for entry in SCRIPT_REGISTRY:
            if entry.get("hidden"):
                continue
            page = ScriptPage(entry)
            page.btn_run.clicked.connect(
                lambda *_, e=entry, p=page: self._on_run(e, p)
            )
            self.pages.addWidget(page)
            self._pages[entry["id"]] = page

    # ══════════════════════════════════════════════════
    #  主题
    # ══════════════════════════════════════════════════

    def _apply_theme(self):
        from config.settings import THEMES_DIR, RESOURCES_DIR
        qss_path = os.path.join(THEMES_DIR, "dracula_dark.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
            icons_dir = os.path.join(RESOURCES_DIR, "icons").replace("\\", "/")
            qss = qss.replace("url(\"resources/icons/", f"url(\"{icons_dir}/")
            self.centralWidget().setStyleSheet(qss)
        else:
            logger.warning(f"主题文件不存在: {qss_path}")

    # ══════════════════════════════════════════════════
    #  信号绑定
    # ══════════════════════════════════════════════════

    def _connect_signals(self):
        # clicked 会携带 checked(bool) 参数，打包环境下用 lambda 吸收参数更稳。
        self.btn_minimize.clicked.connect(lambda *_: self.showMinimized())
        self.btn_maximize.clicked.connect(lambda *_: self._toggle_maximize())
        self.btn_close.clicked.connect(lambda *_: self.close())

    def _update_tray_tooltip(self):
        if self._tray_icon is None:
            return
        if self._running_task_name:
            self._tray_icon.setToolTip(f"{APP_NAME}\n正在执行：{self._running_task_name}")
        else:
            self._tray_icon.setToolTip(APP_NAME)

    @Slot()
    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def _quit_from_tray(self):
        self._force_quit = True
        if self._tray_icon is not None:
            self._tray_icon.hide()
        QApplication.quit()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    # ══════════════════════════════════════════════════
    #  窗口拖拽 & 最大化 / 还原
    # ══════════════════════════════════════════════════

    def _title_bar_mouse_press(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _title_bar_mouse_move(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            if self._is_maximized:
                self._toggle_maximize()
                self._drag_pos = QPoint(self.width() // 2, 22)
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    @Slot()
    def _toggle_maximize(self):
        if self._is_maximized:
            self.showNormal()
            self._is_maximized = False
            self.app_margins.setContentsMargins(10, 10, 10, 10)
            self.btn_maximize.setIcon(self._ico_maximize)
            self.btn_maximize.setToolTip("最大化")
            self.size_grip_frame.show()
            for g in self._grips:
                g.show()
            for g in self._edge_grips.values():
                g.show()
        else:
            self.showMaximized()
            self._is_maximized = True
            self.app_margins.setContentsMargins(0, 0, 0, 0)
            self.btn_maximize.setIcon(self._ico_restore)
            self.btn_maximize.setToolTip("还原")
            self.size_grip_frame.hide()
            for g in self._grips:
                g.hide()
            for g in self._edge_grips.values():
                g.hide()

    # ── 页面导航 ──

    def _switch_page(self, script_id: str):
        page = self._pages.get(script_id)
        if page:
            self.pages.setCurrentWidget(page)
            self._reset_nav_styles(script_id)

            entry = next((e for e in SCRIPT_REGISTRY if e["id"] == script_id), None)
            if entry:
                self.top_title.setText(f"{APP_NAME}  ·  {entry['name']}")

    def _reset_nav_styles(self, active_id: str):
        for sid, btn in self._nav_buttons.items():
            if sid == active_id:
                btn.setStyleSheet(btn.styleSheet() + MENU_SELECTED_STYLE)
            else:
                btn.setStyleSheet(
                    btn.styleSheet().replace(MENU_SELECTED_STYLE, "")
                )

    # ══════════════════════════════════════════════════
    #  运行脚本
    # ══════════════════════════════════════════════════

    @Slot()
    def _on_run(self, entry: dict, page: ScriptPage):
        # 如果当前页正在运行 → 终止
        if self._worker and self._worker.isRunning():
            if self._running_page is page:
                self._worker.request_stop()
                page.btn_run.setEnabled(False)
                page.append_log("\n⏹ 正在终止…")
                return
            page.append_log("[提示] 有脚本正在运行，请等待完成或在对应页面终止...")
            return

        params = page.get_params()
        page.clear_log()
        page.append_log(f"▶ 正在执行: {entry['name']} ...\n")
        self._running_page = page
        self._running_task_name = entry["name"]
        self._update_tray_tooltip()
        self._set_btn_stop_mode(page, True)

        func_name = entry.get("wrapper", entry["function"])

        try:
            self._worker = ScriptWorker(
                module_path=entry["module"],
                func_name=func_name,
                kwargs=params,
            )
            try:
                self._worker.log_signal.connect(lambda *args: self._on_worker_log(str(args[0]) if args else ""))
            except Exception as e:
                raise RuntimeError(f"log_signal.connect 失败: {e}") from e

            try:
                self._worker.log_overwrite_signal.connect(
                    lambda *args: self._on_worker_overwrite(str(args[0]) if args else "")
                )
            except Exception as e:
                raise RuntimeError(f"log_overwrite_signal.connect 失败: {e}") from e

            try:
                self._worker.finished_signal.connect(
                    lambda *args: self._on_worker_finished(
                        bool(args[0]) if len(args) > 0 else False,
                        str(args[1]) if len(args) > 1 else "",
                    )
                )
            except Exception as e:
                raise RuntimeError(f"finished_signal.connect 失败: {e}") from e

            try:
                self._worker.start()
            except Exception as e:
                raise RuntimeError(f"worker.start 失败: {e}") from e
        except Exception as e:
            page.append_log(f"\n✘ 连接运行信号失败: {e}")
            self._running_page = None
            self._running_task_name = ""
            self._update_tray_tooltip()
            self._set_btn_stop_mode(page, False)

    def _on_worker_log(self, text: str):
        if self._running_page is not None:
            self._running_page.log_output.insertPlainText(text)

    def _on_worker_overwrite(self, text: str):
        if self._running_page is not None:
            self._running_page.overwrite_last_line(text)

    def _on_worker_finished(self, success: bool, msg: str):
        page = self._running_page
        if page is None:
            return
        self._on_finished(success, msg, page)

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str, page: ScriptPage):
        tag = "✔ 成功" if success else "✘ 失败"
        page.append_log(f"\n{'='*50}\n{tag}: {msg}")
        task_name = self._running_task_name or page.entry.get("name", "任务")
        self._set_btn_stop_mode(page, False)
        self._running_page = None
        self._running_task_name = ""
        self._update_tray_tooltip()
        if self._tray_icon is not None and self._tray_icon.isVisible():
            title = f"{task_name} 已完成" if success else f"{task_name} 执行失败"
            icon = QSystemTrayIcon.Information if success else QSystemTrayIcon.Warning
            self._tray_icon.showMessage(title, msg, icon, 4000)

    def _set_btn_stop_mode(self, page: ScriptPage, running: bool):
        """切换按钮在「运行」与「停止」两种状态之间"""
        page._is_running = running
        btn = page.btn_run
        if running:
            btn.setText("■  停止")
            btn.setObjectName("btnStop")
        else:
            btn.setText("▶  运行")
            btn.setObjectName("btnRun")
        btn.setEnabled(True)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        if not running:
            page._validate_params()

    # ══════════════════════════════════════════════════
    #  事件重写
    # ══════════════════════════════════════════════════

    def resizeEvent(self, event):
        self._update_grip_positions()
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent):
        if self._force_quit:
            event.accept()
            return
        if self._tray_icon is not None and self._tray_icon.isVisible():
            self.hide()
            event.ignore()
            return
        event.accept()
