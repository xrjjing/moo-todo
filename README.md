# 牛牛待办 🐮✅

一款可爱的任务管理桌面应用，帮助你高效管理日常任务。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey.svg)

## ✨ 功能特性

### 📝 任务管理
- **任务创建** - 快速创建待办任务
- **子任务** - 支持任务拆分为子任务
- **优先级** - 紧急/高/中/低四级优先级
- **截止日期** - 设置任务截止时间
- **标签系统** - 自定义标签分类任务
- **分类管理** - 自定义分类图标和颜色
- **任务搜索** - 快速搜索任务
- **重复任务** - 支持每日/每周/每月/每年重复

### 📊 多视图模式
- **列表视图** - 经典任务列表
- **看板视图** - 拖拽式状态管理
- **日历视图** - 按日期查看任务
- **四象限视图** - 艾森豪威尔矩阵

### 🍅 番茄钟
- **专注计时** - 25 分钟专注 + 5 分钟休息
- **自定义时长** - 可调整专注和休息时长
- **统计记录** - 记录每日番茄数
- **趋势图表** - 30 天专注趋势
- **热力图** - 年度专注热力图
- **分类统计** - 按分类统计专注时长

### 🏆 成就系统
- **成就徽章** - 完成任务解锁成就（铜/银/金/钻石）
- **连续打卡** - 记录连续完成天数
- **进度统计** - 可视化任务完成进度
- **早起/夜猫子** - 特殊时段成就

### 🤖 AI 助手
- **多服务商支持** - OpenAI / Claude / OpenAI 兼容 API
- **会话管理** - 多会话历史记录
- **任务建议** - AI 辅助任务规划

### ⌨️ 快捷键
- **组合键支持** - Ctrl/Cmd + Alt + Shift 组合
- **自定义配置** - 可自定义所有快捷键
- **冲突检测** - 自动检测快捷键冲突

### 🎨 界面特性
- **9 款主题** - 浅色/深色多种主题
- **便签悬浮窗** - 桌面便签快速查看今日任务
- **界面缩放** - 50%-100% 缩放支持
- **可爱的牛牛吉祥物**

## 📸 截图

<!-- 可以添加应用截图 -->

## 🚀 快速开始

### 方式一：下载预编译版本

前往 [Releases](https://github.com/xrjjing/moo-todo/releases) 下载对应平台的安装包。

### 方式二：从源码运行

```bash
# 克隆项目
git clone https://github.com/xrjjing/moo-todo.git
cd moo-todo

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行应用
python main.py
```

## 📦 打包

```bash
# 安装打包工具
pip install pyinstaller

# 运行打包脚本
python build.py

# 或手动打包
# macOS
pyinstaller --onedir --windowed --name "牛牛待办" --add-data "web:web" --add-data "services:services" main.py

# Windows
pyinstaller --onedir --windowed --name "牛牛待办" --add-data "web;web" --add-data "services;services" main.py
```

打包完成后，可执行文件位于 `dist/牛牛待办/` 目录。

## 🗂️ 项目结构

```
moo-todo/
├── main.py                  # 应用入口
├── api.py                   # PyWebView API 接口
├── build.py                 # 打包脚本
├── services/                # 业务逻辑层
│   ├── todo_service.py      # 待办核心服务
│   ├── db_manager.py        # SQLite 数据库管理
│   ├── ai_manager.py        # AI 会话管理
│   └── ai_providers.py      # AI 服务商适配器
├── web/                     # 前端资源
│   ├── index.html           # 主页面
│   ├── styles.css           # 样式表
│   ├── app.js               # 前端逻辑
│   └── lib/                 # 第三方库 (uPlot)
├── icons/                   # 图标资源
└── tests/                   # 单元测试
```

## 🔧 技术栈

- **后端**: Python 3.10+
- **桌面框架**: [pywebview](https://pywebview.flowrl.com/)
- **数据库**: SQLite
- **前端**: 原生 HTML/CSS/JavaScript
- **图表**: [uPlot](https://github.com/leeoniya/uPlot)
- **打包**: PyInstaller

## 📄 数据存储

应用数据存储在 `~/.todo_app/moo_todo.db` SQLite 数据库中，包括：
- 任务和子任务
- 分类配置
- 番茄钟记录
- 成就数据
- AI 会话历史
- 用户设置（主题、快捷键等）

支持数据库文件导入/导出备份。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📜 许可证

本项目采用 [MIT 许可证](LICENSE)。
