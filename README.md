# 数据处理工具（DataProc）

基于 **Python + PySide6** 的桌面小工具：把日常数据标注与处理脚本统一收进一个图形界面，按侧栏分类选择脚本、填好参数、点一下运行，日志实时回显在窗口里。适合在本地批量处理数据集（标注格式转换、可视化、清洗、拆分与视频抽帧等）。

> 定位：**个人自用工具**，不作为正式产品对外分发；功能与稳定性按作者自身流程裁剪。

---

## 使用须知

- **先备份再操作**：多数脚本会**移动**文件（例如把模糊图、重复图、未匹配文件移入「回收子目录」），一般不做物理删除；但批量处理仍然建议先备份，或先用小样本试跑。
- **AI 辅助编写**：项目代码主要由 AI 辅助生成（人机协作完成需求、联调与小幅修改），不排除存在边界情况未覆盖或与你的环境不完全兼容。**重要数据请务必备份。**
- **运行环境偏 Windows**：无边框窗口、系统托盘、`os.add_dll_directory` 等逻辑按 Windows 编写；其他平台未验证。

---

## 功能一览

侧栏里的每一项对应 `scripts/` 下的一个脚本，参数表单由 `scripts/_registry.py` 中的元数据自动生成。

| 分类 | 功能 | 脚本文件 | 说明 |
|------|------|----------|------|
| **格式转换** | LabelMe → YOLO | `scripts/labelme2yolo.py` | 统一入口，含两种模式：「仅 JSON 转 TXT」与「图片 + JSON 混合目录打包到 `images/labels`」。可手动强制仅检测 / 仅分割；自动模式下若同时存在检测与分割，会分别输出到 `det/` 与 `seg/` |
| | YOLO → LabelMe | `scripts/yolo2labelme.py` | 自动识别：5 列 → 检测（`rectangle`）；≥7 列 → 分割（`polygon`）。支持类别统一映射为 0，可选写入 `imageData` |
| **数据可视化** | YOLO 标签可视化 | `scripts/yolo_show.py` | 支持 TXT / JSON 标签，在图片上绘制检测框或叠加分割掩膜；自动模式混合时拆分输出 `det/` 与 `seg/`。分割模式且不填输出目录时逐张预览（任意键下一张，`q` 退出） |
| **数据清洗** | 模糊图片去除（多方法） | `scripts/remove_blurring.py` | 方法：Laplacian 方差（通用初筛）/ Tenengrad 梯度（运动模糊更稳）/ 无人机融合策略（推荐）。分数低于阈值移入回收子目录 |
| | 重复图片去除（多方法） | `scripts/remove_duplication_hanming.py` | 方法：dHash（快速初筛）/ pHash（抗亮度变化）/ 无人机联合策略（dHash + pHash 双重判定）。阈值建议 3–8 |
| | 文件名对齐（主名同步） | `scripts/sync_by_stem_move_unmatched.py` | 按文件主名对齐两个文件夹，缺少匹配项的文件移入各自回收子目录 |
| **数据处理** | 视频抽帧 | `scripts/extract_frames_from_mp4.py` | 按时间间隔抽帧（支持浮点秒，`-1` 表示每一帧）。检测到 FFmpeg 时优先使用（更快），否则回退 OpenCV。支持单个视频或整个文件夹（可递归） |
| | 替换标签类别 | `scripts/replace_txt_label_class.py` | 支持 TXT / JSON：按「原类别 → 新类别」替换，或一键把所有类别改为 0 |
| | 标签统计 | `scripts/count_quantity.py` | 统计各类别的实例数，以及包含该类别的文件数（TXT / JSON） |
| | 数据集拆分 | `scripts/split_dataset.py` | 图片 + 标签按比例随机拆分为 train / val / test，并生成 `dataset.yaml` |
| | 生成空白标签 | `scripts/get_empty_labels.py` | 为图片生成空白 YOLO TXT（负样本）；可输出到图片同目录或指定标签目录 |
| | 按类别拆分到文件夹 | `scripts/split_classes_to_folders.py` | 按类别值创建同名目录，每个目录内含 `images/labels`；同图多类别会复制到多个目录，且各目录的 labels 只保留该类别；可选重映射为 0 |
| | 按尺寸裁剪图片 | `scripts/crop_images_by_size.py` | 按指定高宽与重叠度滑窗裁剪；支持递归子文件夹，同名文件自动加后缀避免覆盖 |
| | M3U8 合并为 MP4 | `scripts/merge_m3u8_to_mp4.py` | 解析 m3u8、校验 TS 分片并合并为 MP4；优先 FFmpeg 流拷贝（极快、无色损），否则回退 OpenCV。可跳过最前 N / 最后 M 个 TS；输出名 = m3u8 所在文件夹名 |

---

## 界面说明

- **无边框窗口**：自定义标题栏，可拖拽移动、双击最大化；四边与四角均可拉伸缩放。
- **侧栏导航**：按分类分组，选中项高亮；底部状态栏显示版本与用途声明。
- **运行 / 停止**：点击「▶ 运行」后按钮变成「■ 停止」，再次点击即请求终止当前脚本（脚本循环会尽快退出）。
- **实时日志**：脚本的 `stdout / stderr` 实时回显；进度条类输出（`\r` 刷新）会在最后一行原地更新。
- **系统托盘**：存在托盘图标时，点窗口关闭按钮会最小化到托盘；通过托盘菜单的「显示主窗口 / 退出」控制，任务结束时托盘会弹出完成通知。

---

## 项目结构

```
data_processing_script/
├── main.py                     # 应用入口：环境配置（DLL 路径 / 工作目录 / 高 DPI）、启动主窗口
├── requirements.txt            # Python 依赖
├── README.md
├── .gitignore
│
├── config/
│   └── settings.py             # 应用名、版本、各资源目录路径、日志格式
│
├── core/
│   ├── script_runner.py        # 子线程运行脚本：stdout 重定向到 UI、支持主动终止
│   └── logger.py               # 日志工具
│
├── views/
│   ├── main_window.py          # 主窗口：侧栏导航、页面堆叠、标题栏、缩放、托盘
│   └── script_page.py          # 通用脚本页：按注册表动态生成表单 + 运行按钮 + 日志区
│
├── scripts/
│   ├── _registry.py            # 脚本注册表（名称 / 分组 / 说明 / 参数元数据）
│   └── *.py                    # 14 个数据处理脚本（见上表）
│
├── themes/
│   └── dracula_dark.qss        # 深色主题（QSS）
│
└── resources/
    ├── fonts/                  # 标签可视化使用的中文字体（platech.ttf）
    └── icons/                  # 应用图标、窗口按钮、侧栏导航图标（SVG / ICO）
```

---

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.10+**（代码使用了 `str \| None` 等联合类型语法；开发环境实测 3.13） |
| 操作系统 | Windows（其他平台未验证） |
| 依赖 | 见 `requirements.txt` |
| FFmpeg | **可选**。视频抽帧、M3U8 合并检测到 FFmpeg 时会更快、质量更好；未安装则自动回退 OpenCV 实现 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行程序

```bash
python main.py
```

### 3. 高 DPI（可选）

若在缩放大于 100% 的显示器上字体异常，可在启动前设置环境变量（`main.py` 中已尝试设置 `QT_FONT_DPI=96`，与 PyDracula 文档中的常见做法一致）。

---

## 如何添加新脚本

1. 在 `scripts/` 下新建 `.py` 文件，实现入口函数（形参名与 GUI 表单项的 `key` 对应）。

2. 在 `scripts/_registry.py` 的 `SCRIPT_REGISTRY` 中追加一项，例如：

```python
{
    "id": "my_script",
    "group": "数据处理",
    "name": "我的脚本",
    "description": "脚本功能说明",
    "module": "scripts.my_script",
    "function": "my_function",
    "params": [
        {"key": "input_dir", "label": "输入文件夹", "type": "folder"},
        {"key": "threshold", "label": "阈值", "type": "int", "default": 10},
    ],
}
```

3. （可选）在 `resources/icons/nav/` 放一个与 `id` 同名的 `.svg`，侧栏按钮会自动使用它作为图标。

4. 重启应用，侧栏即出现对应入口。

**参数类型**（完整说明见 `scripts/_registry.py` 顶部注释）：

| `type` | 控件 | 备注 |
|--------|------|------|
| `folder` | 文件夹选择（带浏览按钮） | 必填 |
| `file_or_folder` | 文件或文件夹选择 | 可配 `optional` |
| `text` | 单行文本 | 必填 |
| `int` / `float` | 数值输入框 | 支持 `min` / `max` / `step` / `decimals` |
| `bool` | 复选框 | 支持 `inline_with` 与标签同行显示 |
| `radio` | 互斥单选 | `choices` 为 `[{"value": ..., "label": ...}, ...]` |
| `select` | 下拉选择 | `choices` 同上，也可传 callable 动态返回 |

其他常用字段：`optional`（可留空）、`show_when`（按其他参数取值动态显示）、`inline_with` / `checkbox_first`（紧凑排版）。

---

## 打包（Windows / Nuitka）

在**项目根目录**执行。下列参数组合经本项目验证；若删减关键的 `--include-data-dir` 或 `--nofollow-import-to=...` 选项，可能出现 Nuitka 报错或运行期异常。

**前置条件**：`resources/icons/app.ico` 存在（`--windows-icon-from-ico` 会引用该文件）。

```bash
python -m nuitka --onefile --assume-yes-for-downloads --remove-output --enable-plugin=pyside6 --include-package=scripts --include-data-dir=themes=themes --include-data-dir=resources=resources --nofollow-import-to=PySide6.QtWebEngine,PySide6.QtWebEngineWidgets,PySide6.QtWebEngineCore,PySide6.Qt3DCore,PySide6.Qt3DRender,PySide6.QtQuick,PySide6.QtQml,PySide6.QtMultimedia,PySide6.QtBluetooth,PySide6.QtSensors,PySide6.QtSerialPort,PySide6.QtCharts,PySide6.QtDataVisualization,PySide6.QtPdf,PySide6.QtSql,PySide6.QtTest,PySide6.QtDesigner,PySide6.QtHelp --windows-console-mode=disable --windows-icon-from-ico=resources/icons/app.ico --output-filename=数据处理工具v1.3.exe --output-dir=dist main.py
```

说明：

- 若 `config`、`views`、`core` 目录只包含 `.py` 文件，无需 `--include-data-dir`；只有 `themes/`、`resources/` 这类非代码资源需要显式打包。
- 产物位于 `dist/` 下（文件名以命令行为准），`dist/` 与 `build/` 已在 `.gitignore` 中忽略。
- 若改用 **PyInstaller**，需要自行把 `themes`、`resources`、`config`、`scripts` 等资源一并打入发布目录，并与 `main.py` / `config/settings.py` 中的 `frozen` 路径逻辑保持一致。

---

## 常见问题（FAQ）

**Q：可视化输出的中文标签变成方块 / 乱码？**
脚本优先使用 `resources/fonts/platech.ttf`，其次是系统字体（微软雅黑 `msyh.ttc`、黑体 `simhei.ttf`、宋体 `simsun.ttc`）。运行日志中会打印 `[yolo_show][font]` 开头的字体命中信息，可据此排查字体是否缺失。

**Q：图片路径里有中文，读不到图？**
脚本内部通过 `np.fromfile` + `cv2.imdecode` / `imencode` 处理，已兼容中文路径。

**Q：没装 FFmpeg 会怎样？**
视频抽帧与 M3U8 合并会自动回退到 OpenCV 实现，功能可用但速度更慢；抽帧场景下 FFmpeg 还能更好地保留原图质量。

**Q：怎么提前停止正在跑的脚本？**
再次点击该页面的「■ 停止」按钮；脚本检测到停止标志后会尽快退出，被终止的任务在日志中标记为「已被用户终止」。

**Q：点了关闭按钮，程序没退出？**
系统托盘可用时，关闭按钮会最小化到托盘（避免误关）。请在托盘图标右键菜单里选「退出」。

---

## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.10+ | 运行环境 |
| PySide6 | Qt for Python，界面与多线程信号槽 |
| OpenCV / Pillow / NumPy | 图像与视频处理、标签可视化绘制 |
| imagehash | 图片感知哈希去重（dHash / pHash） |
| tqdm | 脚本内部的命令行进度条 |
| Nuitka / PyInstaller | Windows 下的打包工具（推荐 Nuitka） |

---

## 界面风格与第三方声明

主界面布局与视觉风格（无边框窗口、侧栏导航、Dracula 系深色 QSS 等）参考并化用了开源模板 **[PyDracula — Modern GUI (PySide6 / PyQt6)](https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6)**（MIT License）。本仓库**并非**该项目的直接 fork，主题与交互在实现上有所简化与改写；若希望基于原作者的完整模板开发，请直接查阅上述仓库及其 README。

标签可视化所用的字体位于 `resources/fonts/`，其授权来源请自行确认；若不允许再分发，请从仓库中移除并在本地放置。

---

## 免责声明

本项目仅供个人学习与研究使用，不构成任何法律建议，**不得用于商业及非法用途**。使用本工具处理数据时，请自行确保数据来源合法并遵守相关法律法规；因使用本工具产生的任何直接或间接损失，作者不承担任何责任。

仓库未附带开源许可证，默认保留所有权利。
