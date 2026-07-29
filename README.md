# WxCleaner macOS - 微信重复文件清理工具

这是 WxCleaner 的 macOS Apple Silicon 适配版本，提供可直接双击运行的
`WxCleaner.app`。

## 来源与致谢

本项目基于 [yqxie1991/WxCleaner](https://github.com/yqxie1991/WxCleaner)。感谢原作者
`yqxie1991` 的项目实现，以及 [Issue #2](https://github.com/yqxie1991/WxCleaner/issues/2)
中提出 macOS 适配方向和参与讨论的贡献者。本仓库的 macOS 适配、构建和测试记录均保留在
当前项目中，原项目的 MIT 许可证继续适用。

WxCleaner 是一款专为清理微信接收文件而设计的轻量级桌面工具。它能够高效扫描指定目录，通过智能算法识别重复文件，并提供可视化的清理界面，帮助用户释放磁盘空间。

## ✨ 核心功能

*   **智能扫描**: 采用 "文件大小 -> 头部哈希 -> 全量哈希" 三级筛选策略，极速识别重复文件，确保 100% 准确率。
*   **可视化预览**: 清晰展示重复文件的路径、大小、修改时间，支持打开文件所在位置。
*   **自动标记**: 扫描完成后自动标记重复项（默认保留路径最短的文件），支持一键全选。
*   **安全清理**: 
    *   文件并非直接永久删除，而是移动至 **系统回收站**，防止误删。
    *   删除前提供二次确认，确保操作安全。
*   **现代化 UI**: 基于 `ttkbootstrap` 构建的现代化界面，简洁美观，支持深色/浅色主题。

## 🛠️ 技术栈

*   **语言**: Python 3.8+
*   **GUI 框架**: [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) (基于 Tkinter)
*   **核心库**: 
    *   `send2trash`: 实现跨平台的安全删除（移至回收站）。
    *   `Pillow`: 图像处理支持。

## 📁 目录结构

```text
app/                 最终可运行的 WxCleaner.app
source/              Python 源码
tests/               自动化测试
assets/              应用图标和打包资源
packaging/           PyInstaller 配置
build/               构建中间产物和历史副本
environment/.venv/   已安装依赖的 Python 虚拟环境
```

## 🚀 快速开始

### macOS Apple Silicon

从本仓库的 [Releases](https://github.com/zzjjuut/WxCleaner-macOS/releases) 下载
`WxCleaner-macOS-arm64.zip`，解压后双击 `WxCleaner.app`。首次运行时，macOS 可能要求授予
应用访问微信文件目录的权限；如果 Gatekeeper 拦截未签名应用，请在 Finder 中右键应用并选择
“打开”。

### 方式一：运行可执行文件 (Windows)
在上游项目的 Releases 页面下载 Windows 版本，双击即可直接运行，无需安装 Python 环境。

### 方式二：源码运行

1.  **环境要求**: 确保已安装 Python 3.8 或更高版本。
2.  **克隆仓库**:
    ```bash
    git clone https://github.com/zzjjuut/WxCleaner-macOS.git
    cd WxCleaner-macOS
    ```
3.  **安装依赖**:
    ```bash
    environment/.venv/bin/pip install -r requirements.txt
    ```
4.  **运行程序**:
    ```bash
    environment/.venv/bin/python source/main.py
    ```

## 📖 使用指南

1.  **选择路径**: 点击 "浏览" 按钮，选择您的微信文件存储目录（通常位于 `Documents/WeChat Files` 下）。
2.  **开始扫描**: 点击 "开始扫描"，程序将自动分析目录下的所有文件。
3.  **查看结果**: 扫描完成后，列表中会显示所有发现的重复文件组。红色高亮表示建议删除的重复项，绿色表示保留项。
4.  **执行清理**: 
    *   您可以手动调整勾选状态。
    *   确认无误后，点击 "移至回收站"。
    *   确认弹窗提示，完成清理。

## 📦 打包构建

如果您想自行打包 macOS 应用：

```bash
environment/.venv/bin/pip install -r requirements.txt pyinstaller
environment/.venv/bin/pyinstaller --noconfirm --clean --windowed --name WxCleaner \
    --distpath build/pyinstaller/dist --workpath build/pyinstaller/work \
    --icon assets/WxCleaner.icns packaging/WxCleaner.spec
```

打包完成后，应用将位于 `build/pyinstaller/dist/WxCleaner.app`；交付用应用位于
`app/WxCleaner.app`。当前发布包针对 Apple Silicon (`arm64`) 构建。

运行测试：

```bash
environment/.venv/bin/python -m pytest tests -v
```

## ⚠️ 免责声明

本工具旨在帮助用户管理文件，虽然提供了安全删除机制（移至回收站），但建议在执行大规模清理前**务必确认文件内容**。作者不对因使用本工具导致的任何数据丢失承担责任。

## 📄 许可证

本项目采用 MIT 许可证。详情请参阅 [LICENSE](LICENSE) 文件。
