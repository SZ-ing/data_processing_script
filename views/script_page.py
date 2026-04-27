"""
通用脚本页面 —— 根据 _registry.py 中的参数元数据动态生成 UI 控件。
每个脚本对应一个 ScriptPage 实例，嵌入主窗口的 QStackedWidget。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog, QFrame, QScrollArea, QComboBox, QListView, QSizePolicy,
)
from PySide6.QtCore import Qt, Slot, QDir
from PySide6.QtGui import QFont, QFontMetrics


class ScriptPage(QWidget):
    """一个脚本的配置 + 运行 + 日志页面"""

    FIELD_H = 36
    LABEL_W = 200
    ROW_SPACING = 8
    FORM_SPACING = 10
    INLINE_GAP = 6
    FORM_RIGHT_SAFE_GAP = 18

    @staticmethod
    def _calc_width_by_text(sample_text: str, factor: float = 1.5, min_w: int = 80, max_w: int = 260) -> int:
        text = str(sample_text or "")
        fm = QFontMetrics(QFont("Segoe UI", 10))
        text_w = fm.horizontalAdvance(text)
        # 预留左右内边距、下拉箭头/微调按钮空间
        width = int(text_w * factor) + 44
        if width < min_w:
            return min_w
        if width > max_w:
            return max_w
        return width

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._inputs: dict[str, QWidget] = {}
        self._param_rows: dict[str, QWidget] = {}
        self._param_row_layouts: dict[str, QHBoxLayout] = {}
        self._show_when_rules: list[dict] = []
        self._required_keys: list[str] = []
        self._radio_keys: set[str] = set()
        self._inline_parent_keys: set[str] = set()
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
        self._inline_parent_keys = {
            str(p.get("inline_with"))
            for p in params
            if p.get("inline_with")
        }
        form_layout = QVBoxLayout(form_container)
        # 右侧预留安全间距，避免内容与滚动条区域视觉重叠。
        form_layout.setContentsMargins(0, 8, self.FORM_RIGHT_SAFE_GAP, 0)
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
        default_value = self._resolve_default(default)
        optional = param.get("optional", False)
        checkbox_first = bool(param.get("checkbox_first", False))
        reserve_label_space_when_checkbox_first = bool(param.get("reserve_label_space_when_checkbox_first", False))
        content_only_row = bool(param.get("content_only_row", False))
        width_by_text_factor = param.get("width_by_text_factor")

        is_required = (
            not optional
            and ptype in ("folder", "file_or_folder", "text", "select")
        )

        inline_with = param.get("inline_with")
        is_inline = bool(inline_with and inline_with in self._param_row_layouts)

        if is_inline:
            row_widget = QWidget()
            row_widget.setVisible(False)
            row_widget.setFixedHeight(0)
            row = self._param_row_layouts[inline_with]
            self._param_rows[key] = self._param_rows[inline_with]
            row.addSpacing(self.INLINE_GAP)
        else:
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(self.ROW_SPACING)
            row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._param_rows[key] = row_widget
            self._param_row_layouts[key] = row

        show_when = param.get("show_when")
        if isinstance(show_when, dict) and show_when.get("key"):
            values = show_when.get("values", [])
            if not isinstance(values, list):
                values = [values]
            self._show_when_rules.append(
                {"target": key, "source": show_when["key"], "values": values}
            )

        use_left_main_label = not (ptype == "bool" and checkbox_first) and not (content_only_row and not is_inline)

        if use_left_main_label:
            display_label = label_text
            if is_required:
                display_label += "  *"

            label = QLabel(display_label)
            if is_inline:
                # 行内 bool 标签（如“类别统一映射为0”）需要更宽，避免被强制换行。
                inline_max_w = 220 if ptype == "bool" else 92
                inline_label_w = self._calc_width_by_text(
                    label_text, factor=0.85, min_w=40, max_w=inline_max_w
                )
                label.setFixedWidth(inline_label_w)
            else:
                label.setFixedWidth(self.LABEL_W)
            label.setMinimumHeight(self.FIELD_H)
            label.setWordWrap(not is_inline)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            color = "rgb(200, 205, 215)" if is_required else "rgb(160, 168, 182)"
            label.setStyleSheet(
                f"color: {color}; line-height: 1.3;"
            )
            row.addWidget(label)
        elif content_only_row and not is_inline:
            # 组内内容行：左侧保留主标签列空位，不再显示独立主标签。
            spacer = QWidget()
            spacer.setFixedWidth(self.LABEL_W)
            spacer.setFixedHeight(self.FIELD_H)
            row.addWidget(spacer)
            display_label = label_text
            if is_required:
                display_label += "  *"
            mini_label = QLabel(display_label)
            mini_label.setMinimumHeight(self.FIELD_H)
            mini_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            mini_label.setStyleSheet("color: rgb(160, 168, 182);")
            mini_w = self._calc_width_by_text(label_text, factor=0.9, min_w=56, max_w=110)
            mini_label.setFixedWidth(mini_w)
            row.addWidget(mini_label)

        if ptype in ("folder", "file_or_folder"):
            edit = QLineEdit()
            edit.setPlaceholderText("点击右侧按钮选择路径...")
            edit.setText(str(default_value) if default_value else "")
            edit.setFixedHeight(self.FIELD_H)
            edit.textChanged.connect(lambda *_: self._on_param_changed())
            row.addWidget(edit, 1)
            btn = QPushButton("浏览")
            btn.setFixedHeight(self.FIELD_H)
            btn.setFixedWidth(70)
            btn.setCursor(Qt.PointingHandCursor)
            if ptype == "folder":
                btn.clicked.connect(lambda *_, e=edit: self._browse_folder(e))
            else:
                btn.clicked.connect(lambda *_, e=edit: self._browse_file_or_folder(e))
            row.addWidget(btn)
            self._inputs[key] = edit
            if is_required:
                self._required_keys.append(key)

        elif ptype == "text":
            edit = QLineEdit()
            edit.setText(str(default_value) if default_value else "")
            edit.setFixedHeight(self.FIELD_H)
            edit.textChanged.connect(lambda *_: self._on_param_changed())
            row.addWidget(edit, 1)
            self._inputs[key] = edit
            if is_required:
                self._required_keys.append(key)

        elif ptype == "int":
            spin = QSpinBox()
            spin.setMinimum(param.get("min", 0))
            spin.setMaximum(param.get("max", 999999))
            spin.setValue(int(default_value) if default_value != "" else 0)
            spin.setFixedHeight(self.FIELD_H)
            spin.setMinimumWidth(120)
            row.addWidget(spin)
            if (not is_inline) and (key not in self._inline_parent_keys):
                row.addStretch()
            self._inputs[key] = spin

        elif ptype == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(int(param.get("decimals", 1)))
            spin.setSingleStep(float(param.get("step", 0.1)))
            spin.setMinimum(param.get("min", 0.0))
            spin.setMaximum(param.get("max", 999999.0))
            spin.setValue(float(default_value) if default_value != "" else 0.0)
            spin.setFixedHeight(self.FIELD_H)
            special_value = param.get("special_value")
            min_positive = param.get("min_positive")
            if special_value is not None and min_positive is not None:
                spin.valueChanged.connect(
                    lambda *_,
                    s=spin,
                    sv=float(special_value),
                    mp=float(min_positive): self._enforce_special_float_range(s, sv, mp)
                )
            if isinstance(width_by_text_factor, (int, float)):
                width = self._calc_width_by_text(str(default_value), float(width_by_text_factor))
                spin.setFixedWidth(width)
            else:
                spin.setMinimumWidth(120)
            row.addWidget(spin)
            if (not is_inline) and (key not in self._inline_parent_keys):
                row.addStretch()
            self._inputs[key] = spin

        elif ptype == "bool":
            if checkbox_first:
                # 使用“带文本的 QCheckBox”以获得更紧凑的“框+文字”布局效果。
                cb = QCheckBox(label_text)
            else:
                cb = QCheckBox()
            cb.setChecked(bool(default_value))
            cb.toggled.connect(lambda *_: self._on_param_changed())
            cb.setCursor(Qt.PointingHandCursor)
            cb.setFixedHeight(self.FIELD_H)
            cb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if checkbox_first:
                if reserve_label_space_when_checkbox_first:
                    spacer = QWidget()
                    spacer.setFixedWidth(140 if is_inline else self.LABEL_W)
                    spacer.setFixedHeight(self.FIELD_H)
                    row.addWidget(spacer)
                row.addWidget(cb)
            else:
                row.addWidget(cb)
            if (not is_inline) and (key not in self._inline_parent_keys):
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
            choices = self._resolve_choices(param.get("choices"))
            default_str = str(default_value) if default_value is not None else ""
            first_rb = None
            for item in choices:
                if isinstance(item, dict):
                    val, text = item.get("value"), item.get("label", str(item.get("value", "")))
                else:
                    val, text = item[0], item[1]
                rb = QRadioButton(text)
                rb.setCursor(Qt.PointingHandCursor)
                rb.setProperty("param_value", val)
                rb.toggled.connect(lambda *_: self._on_param_changed())
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

        elif ptype == "select":
            combo = QComboBox()
            combo.setCursor(Qt.PointingHandCursor)
            combo.setFixedHeight(self.FIELD_H)
            # Windows 下部分样式可能不透传到下拉弹层，给 popup 视图单独设样式保证深色一致。
            popup_view = QListView(combo)
            popup_view.setCursor(Qt.PointingHandCursor)
            popup_view.viewport().setCursor(Qt.PointingHandCursor)
            popup_view.setStyleSheet(
                "QListView {"
                " background-color: rgb(33, 37, 43);"
                " color: rgb(200, 205, 215);"
                " border: 1px solid rgb(52, 59, 72);"
                " outline: 0;"
                "}"
                "QListView::item {"
                " padding: 6px 10px;"
                "}"
                "QListView::item:selected {"
                " background-color: rgb(60, 66, 79);"
                " color: rgb(255, 255, 255);"
                "}"
                "QListView::item:hover {"
                " background-color: rgb(52, 59, 72);"
                "}"
            )
            combo.setView(popup_view)
            combo.currentIndexChanged.connect(lambda *_: self._on_param_changed())
            choices = self._resolve_choices(param.get("choices"))
            default_str = str(default_value) if default_value is not None else ""
            default_idx = 0
            longest_text = ""
            for idx, item in enumerate(choices):
                if isinstance(item, dict):
                    val = item.get("value")
                    text = item.get("label", str(val))
                else:
                    val, text = item[0], item[1]
                combo.addItem(str(text), val)
                if len(str(text)) > len(longest_text):
                    longest_text = str(text)
                if str(val) == default_str:
                    default_idx = idx
            if combo.count() > 0:
                combo.setCurrentIndex(default_idx)
            if isinstance(width_by_text_factor, (int, float)):
                sample = longest_text or combo.currentText() or str(default_value)
                width = self._calc_width_by_text(sample, float(width_by_text_factor))
                combo.setFixedWidth(width)
            else:
                combo.setMinimumWidth(180)
            row.addWidget(combo)
            if (not is_inline) and (key not in self._inline_parent_keys):
                row.addStretch()
            self._inputs[key] = combo

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
            elif isinstance(source_widget, QComboBox):
                val = source_widget.currentData()
                if val is None:
                    val = source_widget.currentText()
                current = str(val)

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
            row_widget = self._param_rows.get(key)
            # 被 show_when 隐藏的字段不参与必填校验。
            if row_widget is not None and row_widget.isHidden():
                continue
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
        dlg = QFileDialog(self, "选择文件或文件夹", line_edit.text())
        # 单个弹窗：同时支持文件与文件夹选择。
        dlg.setFileMode(QFileDialog.AnyFile)
        dlg.setNameFilter("所有文件 (*)")
        # 在 Windows 原生对话框下，AnyFile 模式通常不便直接选目录；
        # 使用 Qt 对话框并套用当前窗口样式，保证功能与风格。
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        dlg.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        win = self.window()
        if win is not None and hasattr(win, "centralWidget") and win.centralWidget() is not None:
            dlg.setStyleSheet(win.centralWidget().styleSheet())
        if dlg.exec():
            selected = dlg.selectedFiles()
            if selected:
                line_edit.setText(selected[0])

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
            elif isinstance(widget, QComboBox):
                val = widget.currentData()
                result[key] = val if val is not None else widget.currentText().strip()
        return result

    @staticmethod
    def _resolve_choices(choices):
        if callable(choices):
            try:
                value = choices()
                if isinstance(value, list):
                    return value
                return []
            except Exception:
                return []
        return choices or []

    @staticmethod
    def _resolve_default(default):
        if callable(default):
            try:
                return default()
            except Exception:
                return ""
        return default

    @staticmethod
    def _enforce_special_float_range(spin: QDoubleSpinBox, special_value: float, min_positive: float):
        """限制浮点输入只能是 special_value 或 >= min_positive。"""
        value = float(spin.value())
        if abs(value - special_value) < 1e-9 or value >= min_positive:
            return

        new_value = special_value if value < 0 else min_positive
        spin.blockSignals(True)
        spin.setValue(new_value)
        spin.blockSignals(False)

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
