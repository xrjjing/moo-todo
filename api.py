"""
Todo API - pywebview 前端接口层
"""
from dataclasses import asdict
from functools import wraps
from services.todo_service import TodoService, Subtask


def api_error_handler(func):
    """API 错误处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"操作失败: {str(e)}"}
    return wrapper


class Api:
    def __init__(self):
        self.service = TodoService()

    # ===== Task API =====
    @api_error_handler
    def add_task(self, title: str, description: str = "", priority: str = "medium",
                 category_id: str = "", due_date: str = "", tags: list = None,
                 quadrant: str = ""):
        task = self.service.add_task(
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
        task = self.service.update_task(task_id, **kwargs)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def delete_task(self, task_id: str):
        success = self.service.delete_task(task_id)
        return {"success": success}

    @api_error_handler
    def get_task(self, task_id: str):
        task = self.service.get_task(task_id)
        return asdict(task) if task else None

    @api_error_handler
    def get_tasks(self, status: str = "", category_id: str = "",
                  priority: str = "", quadrant: str = "",
                  due_date: str = "", search: str = "", tag: str = ""):
        tasks = self.service.get_tasks(
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
        return self.service.get_all_tags()

    @api_error_handler
    def get_tasks_by_tag(self, tag: str):
        tasks = self.service.get_tasks_by_tag(tag)
        return [asdict(t) for t in tasks]

    @api_error_handler
    def get_tasks_by_date_range(self, start_date: str, end_date: str):
        tasks = self.service.get_tasks_by_date_range(start_date, end_date)
        return [asdict(t) for t in tasks]

    @api_error_handler
    def get_today_tasks(self):
        tasks = self.service.get_today_tasks()
        return [asdict(t) for t in tasks]

    @api_error_handler
    def reorder_tasks(self, task_ids: list):
        success = self.service.reorder_tasks(task_ids)
        return {"success": success}

    @api_error_handler
    def update_task_status(self, task_id: str, status: str):
        task = self.service.update_task_status(task_id, status)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    @api_error_handler
    def update_task_priority(self, task_id: str, priority: str):
        task = self.service.update_task_priority(task_id, priority)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    @api_error_handler
    def update_task_quadrant(self, task_id: str, quadrant: str):
        task = self.service.update_task_quadrant(task_id, quadrant)
        return asdict(task) if task else {"success": False, "error": "更新失败"}

    # ===== Subtask API =====
    @api_error_handler
    def add_subtask(self, task_id: str, title: str):
        subtask = self.service.add_subtask(task_id, title)
        return asdict(subtask)

    @api_error_handler
    def update_subtask(self, task_id: str, subtask_id: str, **kwargs):
        subtask = self.service.update_subtask(task_id, subtask_id, **kwargs)
        return asdict(subtask) if subtask else {"success": False, "error": "子任务不存在"}

    @api_error_handler
    def delete_subtask(self, task_id: str, subtask_id: str):
        success = self.service.delete_subtask(task_id, subtask_id)
        return {"success": success}

    @api_error_handler
    def toggle_subtask(self, task_id: str, subtask_id: str):
        subtask = self.service.toggle_subtask(task_id, subtask_id)
        return asdict(subtask) if subtask else {"success": False, "error": "子任务不存在"}

    @api_error_handler
    def reorder_subtasks(self, task_id: str, subtask_ids: list):
        success = self.service.reorder_subtasks(task_id, subtask_ids)
        return {"success": success}

    @api_error_handler
    def get_subtask_progress(self, task_id: str):
        return self.service.get_subtask_progress(task_id)

    # ===== Recurring Tasks API =====
    @api_error_handler
    def set_recurrence(self, task_id: str, rule: dict):
        """设置任务的重复规则"""
        task = self.service.set_recurrence(task_id, rule)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def clear_recurrence(self, task_id: str):
        """清除任务的重复规则"""
        task = self.service.clear_recurrence(task_id)
        return asdict(task) if task else {"success": False, "error": "任务不存在"}

    @api_error_handler
    def generate_recurring_tasks(self):
        """生成到期的重复任务"""
        tasks = self.service.generate_recurring_tasks()
        return [asdict(t) for t in tasks]

    # ===== Category API =====
    @api_error_handler
    def add_category(self, name: str, icon: str = "📁", color: str = "#C7CEEA"):
        category = self.service.add_category(name, icon, color)
        return asdict(category)

    @api_error_handler
    def update_category(self, category_id: str, **kwargs):
        category = self.service.update_category(category_id, **kwargs)
        return asdict(category) if category else {"success": False, "error": "分类不存在"}

    @api_error_handler
    def delete_category(self, category_id: str):
        success = self.service.delete_category(category_id)
        return {"success": success}

    @api_error_handler
    def get_categories(self):
        categories = self.service.get_categories()
        return [asdict(c) for c in categories]

    # ===== Pomodoro API =====
    @api_error_handler
    def start_pomodoro(self, task_id: str, duration: int = 25):
        record = self.service.start_pomodoro(task_id, duration)
        return asdict(record)

    @api_error_handler
    def complete_pomodoro(self, pomodoro_id: str):
        record = self.service.complete_pomodoro(pomodoro_id)
        return asdict(record) if record else {"success": False, "error": "番茄记录不存在"}

    @api_error_handler
    def cancel_pomodoro(self, pomodoro_id: str):
        success = self.service.cancel_pomodoro(pomodoro_id)
        return {"success": success}

    @api_error_handler
    def get_pomodoros_by_task(self, task_id: str):
        records = self.service.get_pomodoros_by_task(task_id)
        return [asdict(r) for r in records]

    @api_error_handler
    def get_today_pomodoro_count(self):
        return self.service.get_today_pomodoro_count()

    # ===== Stats API =====
    @api_error_handler
    def get_stats(self, start_date: str = "", end_date: str = ""):
        return self.service.get_stats(start_date, end_date)

    @api_error_handler
    def get_daily_stats(self, date: str):
        return self.service.get_daily_stats(date)

    # ===== Pomodoro Chart API =====
    @api_error_handler
    def get_pomodoro_daily_stats(self, days: int = 30):
        return self.service.get_pomodoro_daily_stats(days)

    @api_error_handler
    def get_pomodoro_weekly_stats(self, weeks: int = 12):
        return self.service.get_pomodoro_weekly_stats(weeks)

    @api_error_handler
    def get_pomodoro_heatmap(self, year: int = 0):
        return self.service.get_pomodoro_heatmap(year)

    @api_error_handler
    def get_category_pomodoro_stats(self):
        return self.service.get_category_pomodoro_stats()

    # ===== Settings API =====
    @api_error_handler
    def get_settings(self):
        return asdict(self.service.get_settings())

    @api_error_handler
    def update_settings(self, **kwargs):
        settings = self.service.update_settings(**kwargs)
        return asdict(settings)

    @api_error_handler
    def get_theme(self):
        return self.service.get_theme()

    @api_error_handler
    def save_theme(self, theme: str):
        self.service.save_theme(theme)
        return {"success": True}

    # ===== Data API =====
    @api_error_handler
    def export_data(self):
        return self.service.export_data()

    @api_error_handler
    def import_data(self, data: dict):
        return self.service.import_data(data)

    @api_error_handler
    def get_data_stats(self):
        return self.service.get_data_stats()

    # ===== Achievement API =====
    @api_error_handler
    def get_achievements(self):
        return self.service.get_achievements()

    @api_error_handler
    def check_achievements(self):
        return self.service.check_achievements()
