# 数据处理工具

基于 **Python + PySide6** 的桌面小工具，用图形界面统一管理、执行若干数据处理脚本（标注格式转换、可视化、清洗与简单流水线），适合在本地批量处理数据集。

---

## 关于本项目

- **个人自用**：本仓库仅为作者个人学习与工作流程服务，**不作为正式产品或对外分发**；功能与稳定性按个人需求裁剪，使用前请自行评估是否适合你的场景。
- **编写方式**：项目代码主要由 **AI 辅助生成**（人机协作完成需求、联调与小幅修改）。因此不排除存在边界情况未覆盖或与你的环境不完全兼容的情况，**重要数据请务必先备份**。

---

## 免责声明

本项目仅供学习和研究使用，不构成任何法律建议。用户在使用本工具处理数据时，应确保数据来源的合法性，并遵守相关法律法规。因使用本工具而产生的任何直接或间接损失，作者不承担任何责任。

---

## 界面风格说明

主界面布局与视觉风格（无边框窗口、侧栏导航、Dracula 系深色 QSS 等）**参考并化用**了开源模板 **[PyDracula — Modern GUI (PySide6 / PyQt6)](https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6)**（MIT License）。本仓库**并非**该项目的直接 fork，主题与交互在实现上有所简化与改写；若你希望基于原作者完整模板开发，请直接查阅上述仓库及其 README。

---

## 功能一览

| 分类 | 功能 | 说明 |
|------|------|------|
| **格式转换** | LabelMe → YOLO | LabelMe JSON 转 YOLO TXT；支持自动识别检测/分割，也可手动指定模式 |
| | YOLO → LabelMe | YOLO TXT 转 LabelMe JSON；自动识别检测矩形 / 分割多边形，支持类别统一映射为0 |
| **数据可视化** | YOLO 标签可视化 | 支持 TXT / JSON；在图片上绘制检测框或叠加分割结果；auto 混合时拆分输出 det/seg |
| **数据清洗** | 模糊图片去除（多方法） | 支持 Laplacian / Tenengrad / 无人机融合策略，低于阈值移入回收目录 |
| | 重复图片去除（多方法） | 支持 dHash / pHash / 无人机联合策略（双重判定）去除近似重复 |
| | 文件名对齐 | 按主文件名同步两个文件夹，未匹配文件移入回收目录 |
| **数据处理** | 视频抽帧 | 按时间间隔抽帧（优先 FFmpeg，否则 OpenCV） |
| | 替换标签类别 | 支持 TXT / JSON；可按原类别->新类别替换，或一键将所有类别替换为0 |
| | 标签统计 | 统计各类别实例数与图片分布 |
| | 数据集拆分 | 按比例划分 train / val / test 并生成 `dataset.yaml` |
| | 生成空白标签 | 为无标注图片生成空 YOLO TXT（负样本） |
| | 按类别拆分到文件夹 | 支持 TXT / JSON；可选将拆分后类别重映射为0 |
| | M3U8 合并为 MP4 | 解析 m3u8 与 TS 分片合并（优先 FFmpeg 流拷贝） |

---

## 项目结构

```
data_processing_script/
├── main.py                  # 应用入口
├── requirements.txt         # Python 依赖
├── README.md
│
├── themes/
│   └── dracula_dark.qss     # 深色主题（QSS）
│
├── views/
│   ├── main_window.py       # 主窗口（侧栏 + 堆叠页面）
│   └── script_page.py       # 通用脚本页（按注册表生成控件）
│
├── scripts/
│   ├── _registry.py         # 脚本注册表（元数据）
│   └── *.py                 # 各数据处理脚本
│
├── core/
│   ├── script_runner.py     # 子线程运行脚本
│   └── logger.py            # 日志
│
├── config/
│   └── settings.py          # 应用名、版本、路径等
│
└── resources/
    └── icons/               # 导航与窗口按钮图标等
```

Windows 下打包请优先使用下文 **Nuitka** 命令；若改用 PyInstaller，需自行把 `themes`、`resources`、`config`、`scripts` 等资源一并打入发布目录（与 `main.py` 中 `frozen` 路径逻辑一致）。

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

若在缩放大于 100% 的显示器上字体异常，可在启动前设置环境变量（本仓库 `main.py` 中已尝试设置 `QT_FONT_DPI`，与 PyDracula 文档中的常见做法一致）。

---

## 如何添加新脚本

1. 在 `scripts/` 下新建 `.py`，实现入口函数（参数与 GUI 表单项对应）。

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

3. 重启应用，侧栏会出现对应入口。

参数类型说明见 `scripts/_registry.py` 文件顶部注释。

---

## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.10+ | 建议运行环境 |
| PySide6 | Qt for Python |
| OpenCV / Pillow / NumPy | 图像与视频相关处理 |
| imagehash | 图片感知哈希去重 |
| tqdm | 命令行进度条（脚本内） |
| nuitka | 本项目在 Windows 下推荐使用下列命令打包（缺省项易导致构建或运行报错） |

---

## 使用 Nuitka 打包（Windows）

在**项目根目录**执行。下列参数组合经本项目验证；若删减关键 `--include-data-dir` 或 `--nofollow-import-to=...` 选项，可能出现 **Nuitka 报错或运行期异常**。

**前置条件**：`resources/icons/app.ico` 存在（`--windows-icon-from-ico` 会引用该文件）。

**一行命令（便于复制）：**



# --standalone 

```bash
python -m nuitka --onefile --assume-yes-for-downloads --remove-output --enable-plugin=pyside6 --include-package=scripts --include-data-dir=themes=themes --include-data-dir=resources=resources --nofollow-import-to=PySide6.QtWebEngine,PySide6.QtWebEngineWidgets,PySide6.QtWebEngineCore,PySide6.Qt3DCore,PySide6.Qt3DRender,PySide6.QtQuick,PySide6.QtQml,PySide6.QtMultimedia,PySide6.QtBluetooth,PySide6.QtSensors,PySide6.QtSerialPort,PySide6.QtCharts,PySide6.QtDataVisualization,PySide6.QtPdf,PySide6.QtSql,PySide6.QtTest,PySide6.QtDesigner,PySide6.QtHelp --windows-console-mode=disable --windows-icon-from-ico=resources/icons/app.ico --output-filename=数据处理工具v1.3.exe --output-dir=dist main.py

```

说明：若 `config` 目录仅包含 `.py` 文件，不需要 `--include-data-dir=config=config`（否则会有 “No data files in directory 'config'” 警告）。

产物位于 `dist/数据处理工具.exe`（或 Nuitka 实际输出目录，以命令行提示为准）。
