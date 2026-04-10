"""
通用脚本页面 —— 根据 _registry.py 中的参数元数据动态生成 UI 控件。
每个脚本对应一个 ScriptPage 实例，嵌入主窗口的 QStackedWidget。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont


class ScriptPage(QWidget):
    """一个脚本的配置 + 运行 + 日志页面"""

    FIELD_H = 36
    LABEL_W = 200
    ROW_SPACING = 8
    FORM_SPACING = 10

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._inputs: dict[str, QWidget] = {}
        self._param_rows: dict[str, QWidget] = {}
        self._show_when_rules: list[dict] = []
        self._required_keys: list[str] = []
        self._radio_keys: set[str] = set()
        self._is_running = False
        self._build_ui()
        self._apply_visibility_rules()
        self._validate_params()

    # ── 构建界面 ─────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(25, 20, 25, 15)
        root.setSpacing(10)

        title = QLabel(self.entry["name"])
        title.setObjectName("pageTitle")
        font = QFont("Segoe UI", 16, QFont.Bold)
        title.setFont(font)
        root.addWidget(title)

        desc = QLabel(self.entry.get("description", ""))
        desc.setObjectName("pageDesc")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: rgb(160, 168, 182); margin-bottom: 6px;")
        root.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: rgb(44, 49, 58);")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        form_container = QWidget()
        form_container.setStyleSheet("background: transparent;")

        params = self.entry.get("params", [])
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 8, 0, 0)
        form_layout.setSpacing(self.FORM_SPACING)
        for param in params:
            form_layout.addWidget(self._create_param_row(param))

        scroll.setWidget(form_container)
        root.addWidget(scroll, 3)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_run = QPushButton("▶  运行")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.setMinimumHeight(38)
        self.btn_run.setMinimumWidth(140)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setEnabled(False)
        btn_row.addWidget(self.btn_run)
        btn_row.addStretch()
        root.addLayout(btn_row)

        log_label = QLabel("运行日志")
        log_label.setStyleSheet("color: rgb(160, 168, 182); margin-top: 4px;")
        root.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(100)
        root.addWidget(self.log_output, 2)

    # ── 参数行：标签 + 控件 ───────────────────────────────

    def _create_param_row(self, param: dict) -> QWidget:
        ptype = param.get("type", "text")
        key = param["key"]
        label_text = param.get("label", key)
        default = param.get("default", "")
        optional = param.get("optional", False)

        is_required = (
            not optional
            and ptype in ("folder", "file_or_folder", "text")
        )

        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self.ROW_SPACING)
        self._param_rows[key] = row_widget

        show_when = param.get("show_when")
        if isinstance(show_when, dict) and show_when.get("key"):
            values = show_when.get("values", [])
            if not isinstance(values, list):
                values = [values]
            self._show_when_rules.append(
                {"target": key, "source": show_when["key"], "values": values}
            )

        display_label = label_text
        if is_required:
            display_label += "  *"

        label = QLabel(display_label)
        label.setFixedWidth(self.LABEL_W)
        label.setMinimumHeight(self.FIELD_H)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        color = "rgb(200, 205, 215)" if is_required else "rgb(160, 168, 182)"
        label.setStyleSheet(
            f"color: {color}; line-height: 1.3;"
        )
        row.addWidget(label)

        if ptype in ("folder", "file_or_folder"):
            edit = QLineEdit()
            edit.setPlaceholderText("点击右侧按钮选择路径...")
            edit.setText(str(default) if default else "")
            edit.setFixedHeight(self.FIELD_H)
            edit.textChanged.connect(self._on_param_changed)
            row.addWidget(edit, 1)
            btn = QPushButton("浏览")
            btn.setFixedHeight(self.FIELD_H)
            btn.setFixedWidth(70)
            btn.setCursor(Qt.PointingHandCursor)
            if ptype == "folder":
                btn.clicked.connect(lambda _, e=edit: self._browse_folder(e))
            else:
                btn.clicked.connect(lambda _, e=edit: self._browse_file_or_folder(e))
            row.addWidget(btn)
            self._inputs[key] = edit
            if is_required:
                self._required_keys.append(key)

        elif ptype == "text":
            edit = QLineEdit()
            edit.setText(str(default) if default else "")
            edit.setFixedHeight(self.FIELD_H)
            edit.textChanged.connect(self._on_param_changed)
            row.addWidget(edit, 1)
            self._inputs[key] = edit
            if is_required:
                self._required_keys.append(key)

        elif ptype == "int":
            spin = QSpinBox()
            spin.setMinimum(param.get("min", 0))
            spin.setMaximum(param.get("max", 999999))
            spin.setValue(int(default) if default != "" else 0)
            spin.setFixedHeight(self.FIELD_H)
            spin.setMinimumWidth(120)
            row.addWidget(spin)
            row.addStretch()
            self._inputs[key] = spin

        elif ptype == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(1)
            spin.setMinimum(param.get("min", 0.0))
            spin.setMaximum(param.get("max", 999999.0))
            spin.setValue(float(default) if default != "" else 0.0)
            spin.setFixedHeight(self.FIELD_H)
            spin.setMinimumWidth(120)
            row.addWidget(spin)
            row.addStretch()
            self._inputs[key] = spin

        elif ptype == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(default))
            cb.setFixedHeight(self.FIELD_H)
            row.addWidget(cb)
            row.addStretch()
            self._inputs[key] = cb

        elif ptype == "radio":
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setFixedHeight(self.FIELD_H)
            hl = QHBoxLayout(wrap)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(self.ROW_SPACING)
            group = QButtonGroup(wrap)
            group.setExclusive(True)
            choices = param.get("choices") or []
            default_str = str(default) if default is not None else ""
            first_rb = None
            for item in choices:
                if isinstance(item, dict):
                    val, text = item.get("value"), item.get("label", str(item.get("value", "")))
                else:
                    val, text = item[0], item[1]
                rb = QRadioButton(text)
                rb.setCursor(Qt.PointingHandCursor)
                rb.setProperty("param_value", val)
                rb.toggled.connect(self._on_param_changed)
                group.addButton(rb)
                hl.addWidget(rb)
                if first_rb is None:
                    first_rb = rb
                if str(val) == default_str:
                    rb.setChecked(True)
            if first_rb is not None and group.checkedButton() is None:
                first_rb.setChecked(True)
            hl.addStretch()
            row.addWidget(wrap, 1)
            self._inputs[key] = wrap
            self._radio_keys.add(key)

        return row_widget

    @Slot()
    def _on_param_changed(self):
        # 构建阶段 radio 默认选中会触发此槽，此时 btn_run 可能尚未创建。
        if not hasattr(self, "btn_run"):
            return
        self._apply_visibility_rules()
        self._validate_params()

    def _apply_visibility_rules(self):
        """根据 show_when 规则控制参数行显隐。"""
        if not self._show_when_rules:
            return
        for rule in self._show_when_rules:
            target = rule["target"]
            source = rule["source"]
            values = rule["values"]
            row_widget = self._param_rows.get(target)
            source_widget = self._inputs.get(source)
            if row_widget is None or source_widget is None:
                continue

            current = ""
            if source in self._radio_keys:
                current = str(self._radio_group_value(source_widget))
            elif isinstance(source_widget, QLineEdit):
                current = source_widget.text().strip()
            elif isinstance(source_widget, QCheckBox):
                current = str(source_widget.isChecked())
            elif isinstance(source_widget, (QSpinBox, QDoubleSpinBox)):
                current = str(source_widget.value())

            allow = str(current) in {str(v) for v in values}
            row_widget.setVisible(allow)

    # ── 参数校验 ──────────────────────────────────────

    @Slot()
    def _validate_params(self):
        """检查所有必填参数是否已填写，控制运行按钮状态（运行中不干预）"""
        if not hasattr(self, "btn_run"):
            return
        if self._is_running:
            return
        all_filled = True
        for key in self._required_keys:
            widget = self._inputs.get(key)
            if isinstance(widget, QLineEdit) and not widget.text().strip():
                all_filled = False
                break
        self.btn_run.setEnabled(all_filled)

    # ── 浏览对话框 ────────────────────────────────────

    def _browse_folder(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", line_edit.text())
        if path:
            line_edit.setText(path)

    def _browse_file_or_folder(self, line_edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", line_edit.text())
        if path:
            line_edit.setText(path)
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", line_edit.text())
        if path:
            line_edit.setText(path)

    @staticmethod
    def _radio_group_value(wrap: QWidget):
        grp = wrap.findChild(QButtonGroup)
        if grp is None:
            return ""
        btn = grp.checkedButton()
        if btn is None:
            return ""
        v = btn.property("param_value")
        return v if v is not None else ""

    # ── 读取参数值 ────────────────────────────────────

    def get_params(self) -> dict:
        """读取当前页面上所有参数的值，返回 {key: value}"""
        result = {}
        for key, widget in self._inputs.items():
            if key in self._radio_keys:
                result[key] = self._radio_group_value(widget)
            elif isinstance(widget, QLineEdit):
                result[key] = widget.text().strip()
            elif isinstance(widget, QSpinBox):
                result[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                result[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
        return result

    def append_log(self, text: str):
        self.log_output.append(text)

    def overwrite_last_line(self, text: str):
        """删掉日志区最后一行，写入新内容（用于 tqdm 进度条原地刷新）。"""
        cursor = self.log_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.StartOfBlock, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        self.log_output.setTextCursor(cursor)
        self.log_output.ensureCursorVisible()

    def clear_log(self):
        self.log_output.clear()
