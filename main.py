"""
牛牛待办 - Todo 待办应用
基于 pywebview 的桌面应用
"""
import webview
import sys
from pathlib import Path

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent))

from api import Api


def main():
    api = Api()

    # 获取 web 目录
    web_dir = Path(__file__).parent / "web"

    window = webview.create_window(
        title="牛牛待办",
        url=str(web_dir / "index.html"),
        width=1100,
        height=750,
        min_size=(800, 600),
        js_api=api,
        text_select=True
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
