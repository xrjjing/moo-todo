# 牛牛待办 🐮✅

一款可爱的任务管理桌面应用，帮助你高效管理日常任务。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey.svg)

## ✨ 功能特性

### 📝 任务管理
- **任务创建** - 快速创建待办任务
- **子任务** - 支持任务拆分为子任务
- **优先级** - 高/中/低三级优先级
- **截止日期** - 设置任务截止时间
- **标签系统** - 自定义标签分类任务
- **任务搜索** - 快速搜索任务

### 🍅 番茄钟
- **专注计时** - 25 分钟专注 + 5 分钟休息
- **自定义时长** - 可调整专注和休息时长
- **统计记录** - 记录每日番茄数

### 🏆 成就系统
- **成就徽章** - 完成任务解锁成就
- **连续打卡** - 记录连续完成天数
- **进度统计** - 可视化任务完成进度

### 🎨 界面特性
- 多主题支持（亮色/暗色）
- 可爱的牛牛吉祥物
- 响应式布局

## 📸 截图

<!-- 可以添加应用截图 -->

## 🚀 快速开始

### 方式一：下载预编译版本

前往 [Releases](https://github.com/your-username/moo-todo/releases) 下载对应平台的安装包。

### 方式二：从源码运行

```bash
# 克隆项目
git clone https://github.com/your-username/moo-todo.git
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
├── main.py              # 应用入口
├── api.py               # PyWebView API 接口
├── build.py             # 打包脚本
├── services/            # 业务逻辑层
│   └── todo_service.py  # 待办核心服务
├── web/                 # 前端资源
│   ├── index.html       # 主页面
│   ├── styles.css       # 样式表
│   └── app.js           # 前端逻辑
├── icons/               # 图标资源
└── tests/               # 单元测试
```

## 🔧 技术栈

- **后端**: Python 3.10+
- **桌面框架**: [pywebview](https://pywebview.flowrl.com/)
- **前端**: 原生 HTML/CSS/JavaScript
- **打包**: PyInstaller

## 📄 数据存储

应用数据存储在本地 `data/` 目录下，包括：
- `tasks.json` - 任务数据
- `tags.json` - 标签配置
- `pomodoro.json` - 番茄钟记录
- `achievements.json` - 成就数据

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📜 许可证

本项目采用 [MIT 许可证](LICENSE)。
