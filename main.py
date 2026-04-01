"""
牛牛待办桌面端启动入口。

职责定位：
1. 组装 pywebview 窗口，把 `web/index.html` 作为前端页面入口载入。
2. 创建 `Api` 实例，并通过 `js_api` 暴露给前端的 `window.pywebview.api`。
3. 启动桌面事件循环，让前端 HTML/JS 与后端 Python Service 在同一应用中协作。

调用关系：
- 上游：用户双击应用，或命令行执行 `python main.py`
- 下游：`Api` -> `TodoService` / `AIManager` / `DatabaseManager`

排查建议：
- 页面打不开：先看 `web/index.html` 路径是否正确。
- 前端能打开但接口全失效：先看 `Api()` 是否成功创建并传给 `js_api`。
- 打包后资源缺失：再联动检查 `build.py` / PyInstaller 的 `add-data` 配置。
"""
import argparse
import webview
import sys
from pathlib import Path

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent))

from api import Api


def parse_args():
    parser = argparse.ArgumentParser(description="牛牛待办")
    parser.add_argument(
        "-d", "--debug", action="store_true", help="启用调试模式（允许打开开发者工具）"
    )
    parser.add_argument(
        "--watch-web",
        action="store_true",
        help="开发模式：监听 web 目录变化并自动刷新前端页面",
    )
    return parser.parse_args()


def main():
    """应用主启动流程。"""
    args = parse_args()
    debug_mode = args.debug

    # 这里是 Python 侧真正的装配点：先准备桥接对象，再创建窗口。
    web_dir = Path(__file__).parent / "web"
    api = Api(
        debug_mode=debug_mode,
        web_dir=web_dir,
        watch_web=args.watch_web,
    )

    # `js_api=api` 是前后端桥接的关键配置。
    # 页面里的 `window.pywebview.api.xxx()` 最终都会落到 `api.py` 的同名方法上。
    window = webview.create_window(
        title="牛牛待办",
        url=str(web_dir / "index.html"),
        width=1100,
        height=750,
        min_size=(800, 600),
        js_api=api,
        text_select=True
    )
    api.set_window(window)

    # 进入桌面应用事件循环。若要排查启动阶段白屏/崩溃，这里和 create_window 参数是首要入口。
    webview.start(debug=debug_mode)
    sys.exit()


if __name__ == "__main__":
    main()
