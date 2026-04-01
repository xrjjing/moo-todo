"""
pywebview 前后端桥接层。

职责定位：
1. 对前端 `window.pywebview.api.*` 暴露稳定的方法入口。
2. 负责把前端参数转交给 `TodoService` / `AIManager`。
3. 统一做异常拦截，把 Python 异常转换成前端可消费的字典结构。

真实调用链：
- `web/index.html` 上的按钮/输入事件
- `web/app.js` 中的页面函数，如 `loadTasks()`、`sendAIMessage()`
- `window.pywebview.api.<method>()`
- `Api` 同名方法
- `TodoService` / `AIManager`
- `DatabaseManager` / 第三方 AI Provider

排查建议：
- 前端报 “pywebview.api.xxx is not a function”：先看这里是否暴露了对应方法。
- 前端拿到的是 `{success: false, error: ...}`：优先看本文件装饰器和下游 Service 抛出的异常。
- AI 相关接口首次访问才初始化管理器，异常要继续追 `AIManager` 和 Provider 配置。
"""
import asyncio
from dataclasses import asdict
from functools import wraps
from services.todo_service import TodoService, Subtask


def api_error_handler(func):
    """同步 API 错误处理装饰器。

    这里的目标不是吞掉问题，而是把异常转成前端可直接判断的结构：
    `{"success": False, "error": "..."}`。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"操作失败: {str(e)}"}
    return wrapper


def async_api_handler(func):
    """异步 API 错误处理装饰器。

    适用于需要 await 下游 AI/网络调用的方法。
    当前实现通过 `asyncio.run(...)` 把异步逻辑包装成 pywebview 可直接调用的同步入口。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return asyncio.run(func(*args, **kwargs))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"操作失败: {str(e)}"}
    return wrapper


class Api:
    """前端唯一可见的 Python API 门面。

    设计意图：
    - 前端只关心 “我要调用什么能力”，不直接接触 `TodoService` / `AIManager`。
    - 本类保持“薄桥接”角色：参数透传 + 错误格式统一，复杂规则尽量下沉到 Service 层。
    """

    def __init__(self):
        # `TodoService` 是绝大多数页面功能的主入口，应用启动时就直接初始化。
        self._service = TodoService()
        # AI 相关能力是懒加载的，避免应用启动时就因 Provider/网络配置问题拖慢主界面。
        self._ai_manager_instance = None

    @property
    def _ai_manager(self):
        """延迟初始化 AI 管理器。

        上游调用者：
        - AI Provider 配置相关接口
        - AI 聊天会话与消息接口

        排查建议：
        - 如果普通待办功能正常、只有 AI 功能异常，优先从这里继续追到 `AIManager`。
        """
        if self._ai_manager_instance is None:
            from services.ai_manager import AIManager
            self._ai_manager_instance = AIManager(self._service.db)
        return self._ai_manager_instance

    # ===== Task API =====
    # 这一组方法主要被 `web/app.js` 的任务列表、任务弹窗、筛选与拖拽逻辑调用。
    @api_error_handler
    def add_task(self, title: str, description: str = "", priority: str = "medium",
                 category_id: str = "", due_date: str = "", tags: list = None,
                 quadrant: str = ""):
        task = self._service.add_task(
            title=title,
            description=description,
            priority=priority,
            category_id=category_id,
            due_date=due_date,
            tags=tags or [],
            quadrant=quadrant
        )
        return asdict(task)

    @api_error_handler
    def update_task(self, task_id: str, **kwargs):
        task = self._service.update_task(task_id, **kwargs)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def delete_task(self, task_id: str):
        success = self._service.delete_task(task_id)
        return {"success": success}

    @api_error_handler
    def get_task(self, task_id: str):
        task = self._service.get_task(task_id)
        return asdict(task) if task else None

    @api_error_handler
    def get_tasks(self, status: str = "", category_id: str = "",
                  priority: str = "", quadrant: str = "",
                  due_date: str = "", search: str = "", tag: str = ""):
        tasks = self._service.get_tasks(
            status=status,
            category_id=category_id,
            priority=priority,
            quadrant=quadrant,
            due_date=due_date,
            search=search,
            tag=tag
        )
        return [asdict(t) for t in tasks]

    @api_error_handler
    def get_all_tags(self):
        return self._service.get_all_tags()

    @api_error_handler
    def get_tasks_by_tag(self, tag: str):
        tasks = self._service.get_tasks_by_tag(tag)
        return [asdict(t) for t in tasks]

    @api_error_handler
    def get_tasks_by_date_range(self, start_date: str, end_date: str):
        tasks = self._service.get_tasks_by_date_range(start_date, end_date)
        return [asdict(t) for t in tasks]

    @api_error_handler
    def get_today_tasks(self):
        tasks = self._service.get_today_tasks()
        return [asdict(t) for t in tasks]

    @api_error_handler
    def reorder_tasks(self, task_ids: list):
        success = self._service.reorder_tasks(task_ids)
        return {"success": success}

    @api_error_handler
    def update_task_status(self, task_id: str, status: str):
        task = self._service.update_task_status(task_id, status)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    @api_error_handler
    def update_task_priority(self, task_id: str, priority: str):
        task = self._service.update_task_priority(task_id, priority)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    @api_error_handler
    def update_task_quadrant(self, task_id: str, quadrant: str):
        task = self._service.update_task_quadrant(task_id, quadrant)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    # ===== Subtask API =====
    # 子任务接口通常由任务编辑弹窗触发，用于维护任务详情中的拆分项。
    @api_error_handler
    def add_subtask(self, task_id: str, title: str):
        subtask = self._service.add_subtask(task_id, title)
        return asdict(subtask)

    @api_error_handler
    def update_subtask(self, task_id: str, subtask_id: str, **kwargs):
        subtask = self._service.update_subtask(task_id, subtask_id, **kwargs)
        return asdict(subtask) if subtask else {"success": False, "error": "子任务不存在"}

    @api_error_handler
    def delete_subtask(self, task_id: str, subtask_id: str):
        success = self._service.delete_subtask(task_id, subtask_id)
        return {"success": success}

    @api_error_handler
    def toggle_subtask(self, task_id: str, subtask_id: str):
        subtask = self._service.toggle_subtask(task_id, subtask_id)
        return asdict(subtask) if subtask else {"success": False, "error": "子任务不存在"}

    @api_error_handler
    def reorder_subtasks(self, task_id: str, subtask_ids: list):
        success = self._service.reorder_subtasks(task_id, subtask_ids)
        return {"success": success}

    @api_error_handler
    def get_subtask_progress(self, task_id: str):
        return self._service.get_subtask_progress(task_id)

    # ===== Recurring Tasks API =====
    # 重复任务规则由前端任务编辑界面配置，但真正的日期计算与补齐逻辑都在 `TodoService`。
    @api_error_handler
    def set_recurrence(self, task_id: str, rule: dict):
        """设置任务的重复规则"""
        task = self._service.set_recurrence(task_id, rule)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def clear_recurrence(self, task_id: str):
        """清除任务的重复规则"""
        task = self._service.clear_recurrence(task_id)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def generate_recurring_tasks(self):
        """生成到期的重复任务"""
        tasks = self._service.generate_recurring_tasks()
        return [asdict(t) for t in tasks]

    # ===== Category API =====
    # 分类接口主要服务于筛选器、任务表单和统计展示。
    @api_error_handler
    def add_category(self, name: str, icon: str = "📁", color: str = "#C7CEEA"):
        category = self._service.add_category(name, icon, color)
        return asdict(category)

    @api_error_handler
    def update_category(self, category_id: str, **kwargs):
        category = self._service.update_category(category_id, **kwargs)
        return asdict(category) if category else {"success": False, "error": "分类不存在"}

    @api_error_handler
    def delete_category(self, category_id: str):
        success = self._service.delete_category(category_id)
        return {"success": success}

    @api_error_handler
    def get_categories(self):
        categories = self._service.get_categories()
        return [asdict(c) for c in categories]

    # ===== Pomodoro API =====
    # 番茄钟小组件会在开始/完成/取消专注时调用这一组接口。
    @api_error_handler
    def start_pomodoro(self, task_id: str, duration: int = 25):
        record = self._service.start_pomodoro(task_id, duration)
        return asdict(record)

    @api_error_handler
    def complete_pomodoro(self, pomodoro_id: str):
        record = self._service.complete_pomodoro(pomodoro_id)
        return asdict(record) if record else {"success": False, "error": "番茄记录不存在"}

    @api_error_handler
    def cancel_pomodoro(self, pomodoro_id: str):
        success = self._service.cancel_pomodoro(pomodoro_id)
        return {"success": success}

    @api_error_handler
    def get_pomodoros_by_task(self, task_id: str):
        records = self._service.get_pomodoros_by_task(task_id)
        return [asdict(r) for r in records]

    @api_error_handler
    def get_today_pomodoro_count(self):
        return self._service.get_today_pomodoro_count()

    # ===== Stats API =====
    # 工作总结弹窗、顶部统计卡片等都依赖这里汇总后的结果。
    @api_error_handler
    def get_stats(self, start_date: str = "", end_date: str = ""):
        return self._service.get_stats(start_date, end_date)

    @api_error_handler
    def get_daily_stats(self, date: str):
        return self._service.get_daily_stats(date)

    # ===== Pomodoro Chart API =====
    # 专注统计弹窗会并行调用这些接口，再在前端渲染图表与热力图。
    @api_error_handler
    def get_pomodoro_daily_stats(self, days: int = 30):
        return self._service.get_pomodoro_daily_stats(days)

    @api_error_handler
    def get_pomodoro_weekly_stats(self, weeks: int = 12):
        return self._service.get_pomodoro_weekly_stats(weeks)

    @api_error_handler
    def get_pomodoro_heatmap(self, year: int = 0):
        return self._service.get_pomodoro_heatmap(year)

    @api_error_handler
    def get_category_pomodoro_stats(self):
        return self._service.get_category_pomodoro_stats()

    # ===== Settings API =====
    # 设置弹窗会经由这一组接口把主题、缩放、默认视图等写回数据库。
    @api_error_handler
    def get_settings(self):
        return asdict(self._service.get_settings())

    @api_error_handler
    def update_settings(self, **kwargs):
        settings = self._service.update_settings(**kwargs)
        return asdict(settings)

    @api_error_handler
    def get_theme(self):
        return self._service.get_theme()

    @api_error_handler
    def save_theme(self, theme: str):
        self._service.save_theme(theme)
        return {"success": True}

    @api_error_handler
    def get_zoom(self):
        return self._service.get_zoom()

    @api_error_handler
    def save_zoom(self, zoom: int):
        self._service.save_zoom(zoom)
        return {"success": True}

    # ===== Shortcuts API =====
    # 快捷键配置属于设置子域，但单独成组，便于前端按动作名读写整套映射。
    @api_error_handler
    def get_shortcuts(self):
        return self._service.get_shortcuts()

    @api_error_handler
    def save_shortcuts(self, shortcuts: dict):
        return self._service.save_shortcuts(shortcuts)

    @api_error_handler
    def reset_shortcuts(self):
        return self._service.reset_shortcuts()

    # ===== Data API =====
    # 数据导入导出属于高影响操作，但真正的备份/回滚逻辑在 `TodoService.import_db/export_db`。
    @api_error_handler
    def get_db_path(self):
        return self._service.get_db_path()

    @api_error_handler
    def export_db(self, export_path: str):
        return self._service.export_db(export_path)

    @api_error_handler
    def import_db(self, import_path: str):
        return self._service.import_db(import_path)

    @api_error_handler
    def get_data_stats(self):
        return self._service.get_data_stats()

    # ===== Achievement API =====
    # 成就接口主要被成就弹窗和番茄钟/任务完成后的即时检查逻辑调用。
    @api_error_handler
    def get_achievements(self):
        return self._service.get_achievements()

    @api_error_handler
    def check_achievements(self):
        return self._service.check_achievements()

    # ===== AI Provider API =====
    # 这一组接口负责“配置层”，处理 AI 服务商的增删改查、连通性测试和模型拉取。
    @api_error_handler
    def get_ai_providers(self):
        """获取可用的 AI Provider 列表"""
        return self._ai_manager.get_available_providers()

    @api_error_handler
    def switch_ai_provider(self, provider_id: str):
        """切换活跃的 AI Provider"""
        self._ai_manager.switch_provider(provider_id)
        return {"success": True}

    @api_error_handler
    def save_ai_provider(self, provider_config: dict):
        """保存 AI Provider 配置"""
        return self._ai_manager.save_provider(provider_config)

    @api_error_handler
    def delete_ai_provider(self, provider_id: str):
        """删除 AI Provider"""
        return self._ai_manager.delete_provider(provider_id)

    @async_api_handler
    async def test_ai_connection(self, temp_config: dict):
        """测试 AI Provider 连接"""
        return await self._ai_manager.test_connection(temp_config)

    @async_api_handler
    async def fetch_ai_models(self, temp_config: dict):
        """获取可用模型列表"""
        return await self._ai_manager.fetch_models(temp_config)

    # ===== AI Chat API =====
    # 这一组接口负责“会话层”和“消息层”，服务 AI 聊天弹窗的左侧会话栏与右侧对话区。
    @api_error_handler
    def create_chat_session(self, title: str = "", provider_id: str = "", system_prompt: str = ""):
        """创建新的聊天会话"""
        return self._ai_manager.create_session(title, provider_id, system_prompt)

    @api_error_handler
    def get_chat_sessions(self, archived: bool = False):
        """获取聊天会话列表"""
        return self._ai_manager.get_sessions(archived)

    @api_error_handler
    def get_chat_session(self, session_id: str):
        """获取单个会话"""
        return self._ai_manager.get_session(session_id)

    @api_error_handler
    def update_chat_session(self, session_id: str, **kwargs):
        """更新会话"""
        success = self._ai_manager.update_session(session_id, **kwargs)
        return {"success": success}

    @api_error_handler
    def delete_chat_session(self, session_id: str):
        """删除会话"""
        success = self._ai_manager.delete_session(session_id)
        return {"success": success}

    @api_error_handler
    def get_chat_messages(self, session_id: str):
        """获取会话的所有消息"""
        return self._ai_manager.get_messages(session_id)

    @api_error_handler
    def clear_chat_messages(self, session_id: str):
        """清空会话消息"""
        success = self._ai_manager.clear_messages(session_id)
        return {"success": success}

    @async_api_handler
    async def send_chat_message(self, session_id: str, content: str):
        """发送聊天消息并获取 AI 回复。

        关键链路：
        1. 校验会话是否存在；
        2. 先把用户消息写入数据库；
        3. 重新拼装 system prompt + 历史消息；
        4. 调用 `AIManager.chat_with_history()` 请求 AI；
        5. 成功后再把 AI 回复写回数据库并返回给前端。

        排查建议：
        - 用户消息没落库：先看 `add_message()`。
        - AI 无回复：继续看 `AIManager.chat_with_history()` 和 Provider 请求。
        - 会话上下文错乱：重点看这里的 `history -> messages` 组装过程。
        """
        session = self._ai_manager.get_session(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        # 先落用户消息，再请求 AI，这样即使下游失败，也能保留用户的原始输入用于排查。
        user_msg = self._ai_manager.add_message(session_id, "user", content)

        # 重新构建完整上下文，确保前端当前会话的 system_prompt 与历史消息都能带给模型。
        messages = []
        if session.get('system_prompt'):
            messages.append({"role": "system", "content": session['system_prompt']})

        history = self._ai_manager.get_messages(session_id)
        for msg in history:
            messages.append({"role": msg['role'], "content": msg['content']})

        # 这里开始真正走网络/Provider 调用；若报错，问题通常不在前端，而在配置或下游服务商。
        try:
            result = await self._ai_manager.chat_with_history(
                messages,
                provider_id=session.get('provider_id')
            )

            if result.get('success'):
                # 只有 AI 请求成功后才写入 assistant 消息，避免数据库里出现“空回复占位消息”。
                ai_msg = self._ai_manager.add_message(
                    session_id, "assistant",
                    result['response'],
                    provider_id=result.get('provider_id', '')
                )
                return {
                    "success": True,
                    "user_message": user_msg,
                    "ai_message": {
                        "id": ai_msg['id'],
                        "role": "assistant",
                        "content": result['response']
                    },
                    "latency": result.get('latency')
                }
            else:
                return {"success": False, "error": result.get('error', '未知错误')}

        except Exception as e:
            return {"success": False, "error": str(e)}

    @async_api_handler
    async def quick_chat(self, prompt: str, system_prompt: str = ""):
        """快速对话（不保存历史）"""
        try:
            result = await self._ai_manager.chat(prompt, system_prompt)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
