"""
主窗口 —— 无边框 PyDracula 风格，自定义标题栏 + 侧边栏导航 + 脚本页面堆叠
"""

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QLabel, QStackedWidget, QSizePolicy, QSpacerItem,
    QGraphicsDropShadowEffect, QScrollArea, QSizeGrip,
)
from PySide6.QtCore import Qt, Slot, QPoint, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 720)
        self.setMinimumSize(860, 540)

        self._is_maximized = False
        self._drag_pos: QPoint | None = None
        self._pages: dict[str, ScriptPage] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._worker: ScriptWorker | None = None
        self._running_page: ScriptPage | None = None

        self._setup_frameless()
        self._build_ui()
        self._setup_resize_grips()
        self._apply_theme()
        self._connect_signals()

        first_entry = SCRIPT_REGISTRY[0]
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

    def _setup_resize_grips(self):
        """四角/四边缩放手柄"""
        self._grips = []
        for _ in range(4):
            grip = QSizeGrip(self)
            grip.setFixedSize(GRIP_SIZE, GRIP_SIZE)
            grip.setStyleSheet("background: transparent;")
            self._grips.append(grip)
        self._update_grip_positions()

    def _update_grip_positions(self):
        s = GRIP_SIZE
        self._grips[0].move(0, 0)                                     # top-left
        self._grips[1].move(self.width() - s, 0)                      # top-right
        self._grips[2].move(0, self.height() - s)                     # bottom-left
        self._grips[3].move(self.width() - s, self.height() - s)      # bottom-right

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
                btn.clicked.connect(self._on_nav_clicked)
                self.nav_layout.addWidget(btn)
                self._nav_buttons[entry["id"]] = btn

    # ── 脚本页面 ──

    def _create_pages(self):
        for entry in SCRIPT_REGISTRY:
            page = ScriptPage(entry)
            page.btn_run.clicked.connect(
                lambda checked=False, e=entry, p=page: self._on_run(e, p)
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
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_maximize.clicked.connect(self._toggle_maximize)
        self.btn_close.clicked.connect(self.close)

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
        else:
            self.showMaximized()
            self._is_maximized = True
            self.app_margins.setContentsMargins(0, 0, 0, 0)
            self.btn_maximize.setIcon(self._ico_restore)
            self.btn_maximize.setToolTip("还原")
            self.size_grip_frame.hide()
            for g in self._grips:
                g.hide()

    # ── 页面导航 ──

    @Slot()
    def _on_nav_clicked(self):
        btn = self.sender()
        script_id = btn.property("script_id")
        self._switch_page(script_id)

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
        self._set_btn_stop_mode(page, True)

        func_name = entry.get("wrapper", entry["function"])

        self._worker = ScriptWorker(
            module_path=entry["module"],
            func_name=func_name,
            kwargs=params,
        )
        self._worker.log_signal.connect(page.log_output.insertPlainText)
        self._worker.log_overwrite_signal.connect(page.overwrite_last_line)
        self._worker.finished_signal.connect(
            lambda ok, msg, p=page: self._on_finished(ok, msg, p)
        )
        self._worker.start()

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str, page: ScriptPage):
        tag = "✔ 成功" if success else "✘ 失败"
        page.append_log(f"\n{'='*50}\n{tag}: {msg}")
        self._set_btn_stop_mode(page, False)
        self._running_page = None

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
