"""
Todo Service - 待办任务核心业务逻辑
"""
import json
import uuid
from dataclasses import dataclass, asdict, field
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any


def generate_unique_id(prefix: str = "") -> str:
    """生成唯一ID（使用UUID避免碰撞）"""
    uid = uuid.uuid4().hex[:16]
    return f"{prefix}_{uid}" if prefix else uid


@dataclass
class Subtask:
    id: str
    title: str
    completed: bool = False
    order: int = 0


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    status: str = "not_started"  # not_started | in_progress | completed
    priority: str = "medium"     # urgent | high | medium | low
    quadrant: str = ""           # q1 | q2 | q3 | q4 (四象限)
    category_id: str = ""
    due_date: str = ""           # YYYY-MM-DD
    tags: List[str] = field(default_factory=list)
    subtasks: List[Subtask] = field(default_factory=list)
    recurrence: Optional[dict] = None  # 重复规则
    parent_task_id: str = ""           # 生成此任务的父任务ID
    created_at: str = ""
    completed_at: str = ""
    pomodoro_count: int = 0
    order: int = 0


@dataclass
class Category:
    id: str
    name: str
    icon: str = "📁"
    color: str = "#C7CEEA"
    order: int = 0


@dataclass
class PomodoroRecord:
    id: str
    task_id: str
    started_at: str
    ended_at: str = ""
    duration: int = 25
    completed: bool = False


@dataclass
class RecurrenceRule:
    """重复任务规则"""
    type: str = ""           # daily | weekly | monthly | yearly
    interval: int = 1        # 间隔（每 N 天/周/月/年）
    weekdays: List[int] = field(default_factory=list)  # 周几重复 [0-6]，0=周一
    month_day: int = 0       # 每月第几天
    end_type: str = "never"  # never | count | date
    end_count: int = 0       # 重复次数限制
    end_date: str = ""       # 结束日期
    generated_count: int = 0 # 已生成次数


@dataclass
class Settings:
    pomodoro_work: int = 25
    pomodoro_break: int = 5
    pomodoro_long_break: int = 15
    theme: str = "cute"
    default_view: str = "list"  # list | kanban | calendar | quadrant
    # 便签设置
    sticky_visible: bool = False
    sticky_opacity: float = 1.0
    sticky_position_x: int = 30
    sticky_position_y: int = 30


# 常量
VALID_STATUSES = {"not_started", "in_progress", "completed"}
VALID_PRIORITIES = {"urgent", "high", "medium", "low"}
VALID_QUADRANTS = {"", "q1", "q2", "q3", "q4"}
PRIORITY_COLORS = {
    "urgent": "#E07A5F",  # 红色
    "high": "#3B82F6",    # 蓝色
    "medium": "#F59E0B",  # 橙色
    "low": "#9CA3AF"      # 灰色
}


class TodoService:
    def __init__(self, data_dir: str = ""):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / ".todo_app"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.tasks_file = self.data_dir / "tasks.json"
        self.categories_file = self.data_dir / "categories.json"
        self.pomodoros_file = self.data_dir / "pomodoros.json"
        self.settings_file = self.data_dir / "settings.json"

        self.tasks: List[Task] = []
        self.categories: List[Category] = []
        self.pomodoros: List[PomodoroRecord] = []
        self.settings: Settings = Settings()

        self._load_all()

    # ===== 文件操作 =====
    def _load_json(self, file: Path) -> List[Dict]:
        if not file.exists():
            return []
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return []

    def _save_json(self, file: Path, data: List):
        payload = json.dumps(
            [asdict(d) if hasattr(d, '__dataclass_fields__') else d for d in data],
            ensure_ascii=False, indent=2
        )
        tmp_file = file.with_suffix(file.suffix + ".tmp")
        tmp_file.write_text(payload, encoding="utf-8")
        tmp_file.replace(file)

    def _load_all(self):
        # 加载任务（处理子任务嵌套）
        tasks_data = self._load_json(self.tasks_file)
        self.tasks = []
        for t in tasks_data:
            subtasks_data = t.pop('subtasks', [])
            task = Task(**t)
            task.subtasks = [Subtask(**s) for s in subtasks_data] if subtasks_data else []
            self.tasks.append(task)

        # 加载分类
        categories_data = self._load_json(self.categories_file)
        if categories_data:
            self.categories = [Category(**c) for c in categories_data]
        else:
            self._init_default_categories()

        # 加载番茄记录
        pomodoros_data = self._load_json(self.pomodoros_file)
        self.pomodoros = [PomodoroRecord(**p) for p in pomodoros_data]

        # 加载设置
        if self.settings_file.exists():
            try:
                settings_data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                self.settings = Settings(**settings_data)
            except (json.JSONDecodeError, IOError):
                self.settings = Settings()

    def _init_default_categories(self):
        defaults = [
            Category(id=generate_unique_id("cat"), name="工作", icon="💼", color="#3B82F6", order=0),
            Category(id=generate_unique_id("cat"), name="学习", icon="📚", color="#8B5CF6", order=1),
            Category(id=generate_unique_id("cat"), name="生活", icon="🏠", color="#10B981", order=2),
            Category(id=generate_unique_id("cat"), name="其他", icon="📌", color="#6B7280", order=3),
        ]
        self.categories = defaults
        self._save_json(self.categories_file, self.categories)

    def _save_tasks(self):
        self._save_json(self.tasks_file, self.tasks)

    def _save_categories(self):
        self._save_json(self.categories_file, self.categories)

    def _save_pomodoros(self):
        self._save_json(self.pomodoros_file, self.pomodoros)

    def _save_settings(self):
        payload = json.dumps(asdict(self.settings), ensure_ascii=False, indent=2)
        self.settings_file.write_text(payload, encoding="utf-8")

    # ===== Task CRUD =====
    def add_task(self, title: str, description: str = "", priority: str = "medium",
                 category_id: str = "", due_date: str = "", tags: List[str] = None,
                 quadrant: str = "") -> Task:
        if not title or not title.strip():
            raise ValueError("任务标题不能为空")
        if priority not in VALID_PRIORITIES:
            priority = "medium"
        if quadrant not in VALID_QUADRANTS:
            quadrant = ""

        max_order = max((t.order for t in self.tasks), default=-1)
        task = Task(
            id=generate_unique_id("task"),
            title=title.strip(),
            description=description.strip(),
            status="not_started",
            priority=priority,
            quadrant=quadrant,
            category_id=category_id,
            due_date=due_date,
            tags=tags or [],
            created_at=datetime.now().isoformat(),
            completed_at="",
            pomodoro_count=0,
            order=max_order + 1
        )
        self.tasks.append(task)
        self._save_tasks()
        return task

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self.get_task(task_id)
        if not task:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key):
                if key == "status" and value not in VALID_STATUSES:
                    continue
                if key == "priority" and value not in VALID_PRIORITIES:
                    continue
                if key == "quadrant" and value not in VALID_QUADRANTS:
                    continue
                if key == "title" and (not value or not str(value).strip()):
                    continue
                setattr(task, key, value)

        # 自动设置完成时间
        if task.status == "completed" and not task.completed_at:
            task.completed_at = datetime.now().isoformat()
        elif task.status != "completed":
            task.completed_at = ""

        self._save_tasks()
        return task

    def delete_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        self.tasks.remove(task)
        # 删除关联的番茄记录
        self.pomodoros = [p for p in self.pomodoros if p.task_id != task_id]
        self._save_tasks()
        self._save_pomodoros()
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def _task_has_tag(self, task: Task, tag: str) -> bool:
        """判断任务是否包含指定标签（做 strip 归一化，避免空白标签干扰）"""
        normalized = (tag or "").strip()
        if not normalized:
            return False
        if not task.tags or not isinstance(task.tags, list):
            return False
        for item in task.tags:
            if not item:
                continue
            if str(item).strip() == normalized:
                return True
        return False

    def get_all_tags(self) -> List[str]:
        """获取所有任务的标签（去重后按字母序排序）"""
        tag_set = set()
        for task in self.tasks:
            if not task.tags or not isinstance(task.tags, list):
                continue
            for tag in task.tags:
                if not tag:
                    continue
                normalized = str(tag).strip()
                if normalized:
                    tag_set.add(normalized)
        return sorted(tag_set)

    def get_tasks_by_tag(self, tag: str) -> List[Task]:
        """按标签获取任务（保持与 get_tasks 一致的 order 排序）"""
        normalized = (tag or "").strip()
        if not normalized:
            return []
        result = [t for t in self.tasks if self._task_has_tag(t, normalized)]
        return sorted(result, key=lambda t: t.order)

    def get_tasks(self, status: str = "", category_id: str = "",
                  priority: str = "", quadrant: str = "",
                  due_date: str = "", search: str = "", tag: str = "") -> List[Task]:
        result = self.tasks.copy()

        if status:
            result = [t for t in result if t.status == status]
        if category_id:
            result = [t for t in result if t.category_id == category_id]
        if priority:
            result = [t for t in result if t.priority == priority]
        if quadrant:
            result = [t for t in result if t.quadrant == quadrant]
        if due_date:
            result = [t for t in result if t.due_date == due_date]
        if tag:
            normalized = str(tag).strip()
            if normalized:
                result = [t for t in result if self._task_has_tag(t, normalized)]
        if search:
            search_lower = search.lower()
            result = [t for t in result if search_lower in t.title.lower()
                      or search_lower in t.description.lower()]

        return sorted(result, key=lambda t: t.order)

    def get_tasks_by_date_range(self, start_date: str, end_date: str) -> List[Task]:
        return [t for t in self.tasks
                if t.due_date and start_date <= t.due_date <= end_date]

    def get_today_tasks(self) -> List[Task]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_tasks(due_date=today)

    def reorder_tasks(self, task_ids: List[str]) -> bool:
        task_map = {t.id: t for t in self.tasks}
        for i, tid in enumerate(task_ids):
            if tid in task_map:
                task_map[tid].order = i
        self._save_tasks()
        return True

    def update_task_status(self, task_id: str, status: str) -> Optional[Task]:
        if status not in VALID_STATUSES:
            return None
        return self.update_task(task_id, status=status)

    def update_task_priority(self, task_id: str, priority: str) -> Optional[Task]:
        if priority not in VALID_PRIORITIES:
            return None
        return self.update_task(task_id, priority=priority)

    def update_task_quadrant(self, task_id: str, quadrant: str) -> Optional[Task]:
        if quadrant not in VALID_QUADRANTS:
            return None
        return self.update_task(task_id, quadrant=quadrant)

    # ===== Subtask CRUD =====
    def add_subtask(self, task_id: str, title: str) -> Subtask:
        task = self.get_task(task_id)
        if not task:
            raise ValueError("任务不存在")
        if not title or not title.strip():
            raise ValueError("子任务标题不能为空")

        max_order = max((s.order for s in task.subtasks), default=-1)
        subtask = Subtask(
            id=generate_unique_id("sub"),
            title=title.strip(),
            completed=False,
            order=max_order + 1
        )
        task.subtasks.append(subtask)
        self._save_tasks()
        return subtask

    def update_subtask(self, task_id: str, subtask_id: str, **kwargs) -> Optional[Subtask]:
        task = self.get_task(task_id)
        if not task:
            return None
        subtask = next((s for s in task.subtasks if s.id == subtask_id), None)
        if not subtask:
            return None

        for key, value in kwargs.items():
            if hasattr(subtask, key):
                if key == "title" and (not value or not str(value).strip()):
                    continue
                setattr(subtask, key, value)
        self._save_tasks()
        return subtask

    def delete_subtask(self, task_id: str, subtask_id: str) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        subtask = next((s for s in task.subtasks if s.id == subtask_id), None)
        if not subtask:
            return False
        task.subtasks.remove(subtask)
        self._save_tasks()
        return True

    def toggle_subtask(self, task_id: str, subtask_id: str) -> Optional[Subtask]:
        task = self.get_task(task_id)
        if not task:
            return None
        subtask = next((s for s in task.subtasks if s.id == subtask_id), None)
        if not subtask:
            return None
        subtask.completed = not subtask.completed
        self._save_tasks()
        return subtask

    def reorder_subtasks(self, task_id: str, subtask_ids: List[str]) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        subtask_map = {s.id: s for s in task.subtasks}
        for i, sid in enumerate(subtask_ids):
            if sid in subtask_map:
                subtask_map[sid].order = i
        task.subtasks.sort(key=lambda s: s.order)
        self._save_tasks()
        return True

    def get_subtask_progress(self, task_id: str) -> Dict[str, int]:
        task = self.get_task(task_id)
        if not task:
            return {"completed": 0, "total": 0}
        total = len(task.subtasks)
        completed = sum(1 for s in task.subtasks if s.completed)
        return {"completed": completed, "total": total}

    # ===== Recurring Tasks 重复任务 =====
    def set_recurrence(self, task_id: str, rule: dict) -> Optional[Task]:
        """设置任务的重复规则（要求任务必须有 due_date）"""
        task = self.get_task(task_id)
        if not task:
            return None
        if not task.due_date:
            raise ValueError("设置重复规则前必须先设置截止日期")
        task.recurrence = self._normalize_recurrence_rule(rule)
        self._save_tasks()
        return task

    def clear_recurrence(self, task_id: str) -> Optional[Task]:
        """清除任务的重复规则"""
        task = self.get_task(task_id)
        if not task:
            return None
        task.recurrence = None
        self._save_tasks()
        return task

    def _normalize_recurrence_rule(self, rule: dict) -> dict:
        """规范化重复规则，填充默认值并确保类型安全"""
        def safe_int(val, default=None):
            """安全转换为整数，失败返回 None"""
            if val is None:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        # 规范化 weekdays - 确保为有效整数列表并去重排序
        raw_weekdays = rule.get("weekdays", [])
        weekdays = []
        for w in raw_weekdays:
            v = safe_int(w)
            if v is not None and 0 <= v <= 6:
                weekdays.append(v)
        weekdays = sorted(set(weekdays))

        # 规范化 month_day - 钳制到 0-31（0 表示使用原任务日期）
        month_day_raw = safe_int(rule.get("month_day", 0), 0)
        month_day = max(0, min(31, month_day_raw))

        return {
            "type": rule.get("type", "") if rule.get("type") in ("daily", "weekly", "monthly", "yearly", "") else "",
            "interval": max(1, safe_int(rule.get("interval", 1), 1)),
            "weekdays": weekdays,
            "month_day": month_day,
            "end_type": rule.get("end_type", "never") if rule.get("end_type") in ("never", "count", "date") else "never",
            "end_count": max(1, safe_int(rule.get("end_count", 0), 0)) if rule.get("end_type") == "count" else 0,
            "end_date": rule.get("end_date", ""),
            "generated_count": 0  # 设置新规则时总是重置
        }

    def generate_recurring_tasks(self) -> List[Task]:
        """生成到期的重复任务（应在启动时调用，会追平所有逾期周期）"""
        generated = []
        today = date.today()

        # 使用索引遍历，避免迭代时修改列表的问题
        task_ids = [t.id for t in self.tasks if t.recurrence and t.due_date]

        for task_id in task_ids:
            task = self.get_task(task_id)
            if not task or not task.recurrence:
                continue

            # 循环生成直到追平 today 或触发结束条件
            max_iterations = 100  # 防止无限循环
            for _ in range(max_iterations):
                if not self._should_generate_occurrence(task, today):
                    break

                next_date = self._get_next_occurrence(task, today)
                if not next_date:
                    break

                # 检查 next_date 是否超过 end_date
                rule = task.recurrence
                if rule.get("end_type") == "date" and rule.get("end_date"):
                    try:
                        end_date = date.fromisoformat(rule["end_date"])
                        next_dt = date.fromisoformat(next_date)
                        if next_dt > end_date:
                            break
                    except ValueError:
                        pass

                new_task = self._create_next_recurring_task(task, next_date)
                if new_task:
                    generated.append(new_task)
                else:
                    break  # 已存在相同任务，停止生成

        if generated:
            self._save_tasks()
        return generated

    def _should_generate_occurrence(self, task: Task, today: date) -> bool:
        """判断是否应生成新的重复实例"""
        rule = task.recurrence
        if not rule or not rule.get("type"):
            return False

        # 检查结束条件
        end_type = rule.get("end_type", "never")
        if end_type == "count":
            if rule.get("generated_count", 0) >= rule.get("end_count", 0):
                return False
        elif end_type == "date":
            end_date_str = rule.get("end_date", "")
            if end_date_str:
                try:
                    end_date = date.fromisoformat(end_date_str)
                    if today > end_date:
                        return False
                except ValueError:
                    pass

        # 检查是否已存在该日期的子任务
        try:
            task_due = date.fromisoformat(task.due_date)
        except ValueError:
            return False

        # 只有当任务到期或已过期时才生成下一个
        return task_due <= today

    def _get_next_occurrence(self, task: Task, today: date) -> Optional[str]:
        """计算下一次重复的日期（安全处理边界情况）"""
        rule = task.recurrence
        if not rule:
            return None

        try:
            current_due = date.fromisoformat(task.due_date)
        except ValueError:
            return None

        rec_type = rule.get("type", "")
        interval = max(1, rule.get("interval", 1))

        try:
            if rec_type == "daily":
                next_date = current_due + timedelta(days=interval)

            elif rec_type == "weekly":
                weekdays = rule.get("weekdays", [])
                if weekdays:
                    # 找到下一个符合的周几，考虑 interval
                    next_date = current_due + timedelta(days=1)
                    weeks_passed = 0
                    for _ in range(interval * 7 + 7):  # 最多找 interval+1 周
                        if next_date.weekday() in weekdays:
                            # 检查是否满足 interval 周的要求
                            week_diff = (next_date - current_due).days // 7
                            if week_diff >= interval - 1:
                                break
                        next_date += timedelta(days=1)
                else:
                    next_date = current_due + timedelta(weeks=interval)

            elif rec_type == "monthly":
                month_day = rule.get("month_day", 0) or current_due.day
                month_day = max(1, min(31, month_day))  # 钳制到 1-31
                year = current_due.year
                month = current_due.month + interval
                while month > 12:
                    month -= 12
                    year += 1
                # 处理月末边界
                max_day = calendar.monthrange(year, month)[1]
                day = min(month_day, max_day)
                next_date = date(year, month, day)

            elif rec_type == "yearly":
                next_year = current_due.year + interval
                # 处理 2/29 闰年问题
                if current_due.month == 2 and current_due.day == 29:
                    if not calendar.isleap(next_year):
                        next_date = date(next_year, 2, 28)
                    else:
                        next_date = date(next_year, 2, 29)
                else:
                    next_date = date(next_year, current_due.month, current_due.day)
            else:
                return None

            return next_date.isoformat()

        except (ValueError, OverflowError):
            # 日期计算异常，跳过此任务
            return None

    def _create_next_recurring_task(self, parent: Task, next_due: str) -> Optional[Task]:
        """基于父任务创建下一个重复实例"""
        # 检查是否已存在相同父任务和日期的任务
        for t in self.tasks:
            if t.parent_task_id == parent.id and t.due_date == next_due:
                return None

        max_order = max((t.order for t in self.tasks), default=-1)
        new_task = Task(
            id=generate_unique_id("task"),
            title=parent.title,
            description=parent.description,
            status="not_started",
            priority=parent.priority,
            quadrant=parent.quadrant,
            category_id=parent.category_id,
            due_date=next_due,
            tags=parent.tags.copy() if parent.tags else [],
            subtasks=[],  # 子任务不复制
            recurrence=None,  # 生成的任务不继承重复规则
            parent_task_id=parent.id,
            created_at=datetime.now().isoformat(),
            completed_at="",
            pomodoro_count=0,
            order=max_order + 1
        )
        self.tasks.append(new_task)

        # 更新父任务的生成计数和截止日期
        if parent.recurrence:
            parent.recurrence["generated_count"] = parent.recurrence.get("generated_count", 0) + 1
            parent.due_date = next_due

        return new_task

    # ===== Category CRUD =====
    def add_category(self, name: str, icon: str = "📁", color: str = "#C7CEEA") -> Category:
        if not name or not name.strip():
            raise ValueError("分类名称不能为空")
        max_order = max((c.order for c in self.categories), default=-1)
        category = Category(
            id=generate_unique_id("cat"),
            name=name.strip(),
            icon=icon,
            color=color,
            order=max_order + 1
        )
        self.categories.append(category)
        self._save_categories()
        return category

    def update_category(self, category_id: str, **kwargs) -> Optional[Category]:
        category = self.get_category(category_id)
        if not category:
            return None
        for key, value in kwargs.items():
            if hasattr(category, key):
                setattr(category, key, value)
        self._save_categories()
        return category

    def delete_category(self, category_id: str) -> bool:
        category = self.get_category(category_id)
        if not category:
            return False
        self.categories.remove(category)
        # 清除任务的分类关联
        for task in self.tasks:
            if task.category_id == category_id:
                task.category_id = ""
        self._save_categories()
        self._save_tasks()
        return True

    def get_category(self, category_id: str) -> Optional[Category]:
        for cat in self.categories:
            if cat.id == category_id:
                return cat
        return None

    def get_categories(self) -> List[Category]:
        return sorted(self.categories, key=lambda c: c.order)

    # ===== Pomodoro 番茄钟 =====
    def start_pomodoro(self, task_id: str, duration: int = 25) -> PomodoroRecord:
        task = self.get_task(task_id)
        if not task:
            raise ValueError("任务不存在")

        record = PomodoroRecord(
            id=generate_unique_id("pomo"),
            task_id=task_id,
            started_at=datetime.now().isoformat(),
            duration=duration,
            completed=False
        )
        self.pomodoros.append(record)
        self._save_pomodoros()
        return record

    def complete_pomodoro(self, pomodoro_id: str) -> Optional[PomodoroRecord]:
        for record in self.pomodoros:
            if record.id == pomodoro_id:
                record.ended_at = datetime.now().isoformat()
                record.completed = True
                # 更新任务的番茄计数
                task = self.get_task(record.task_id)
                if task:
                    task.pomodoro_count += 1
                    self._save_tasks()
                self._save_pomodoros()
                return record
        return None

    def cancel_pomodoro(self, pomodoro_id: str) -> bool:
        for record in self.pomodoros:
            if record.id == pomodoro_id:
                record.ended_at = datetime.now().isoformat()
                record.completed = False
                self._save_pomodoros()
                return True
        return False

    def get_pomodoros_by_task(self, task_id: str) -> List[PomodoroRecord]:
        return [p for p in self.pomodoros if p.task_id == task_id]

    def get_pomodoros_by_date(self, date: str) -> List[PomodoroRecord]:
        return [p for p in self.pomodoros if p.started_at.startswith(date)]

    def get_today_pomodoro_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        return sum(1 for p in self.pomodoros
                   if p.started_at.startswith(today) and p.completed)

    # ===== 番茄统计图表数据 =====
    def get_pomodoro_daily_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """获取最近 N 天的每日番茄统计"""
        from datetime import timedelta
        result = []
        today = datetime.now().date()

        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            count = sum(1 for p in self.pomodoros
                       if p.started_at.startswith(date_str) and p.completed)
            minutes = sum(p.duration for p in self.pomodoros
                         if p.started_at.startswith(date_str) and p.completed)
            result.append({
                "date": date_str,
                "count": count,
                "minutes": minutes
            })
        return result

    def get_pomodoro_weekly_stats(self, weeks: int = 12) -> List[Dict[str, Any]]:
        """获取最近 N 周的每周番茄统计"""
        from datetime import timedelta
        result = []
        today = datetime.now().date()
        # 计算本周一
        start_of_week = today - timedelta(days=today.weekday())

        for i in range(weeks - 1, -1, -1):
            week_start = start_of_week - timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            week_str = week_start.strftime("%Y-%m-%d")

            count = 0
            minutes = 0
            for p in self.pomodoros:
                if not p.completed:
                    continue
                p_date = p.started_at[:10]
                if week_start.strftime("%Y-%m-%d") <= p_date <= week_end.strftime("%Y-%m-%d"):
                    count += 1
                    minutes += p.duration

            result.append({
                "week_start": week_str,
                "week_num": week_start.isocalendar()[1],
                "count": count,
                "minutes": minutes
            })
        return result

    def get_pomodoro_heatmap(self, year: int = 0) -> Dict[str, int]:
        """获取指定年份的热力图数据 (日期 -> 番茄数)"""
        if year == 0:
            year = datetime.now().year

        heatmap = {}
        for p in self.pomodoros:
            if not p.completed:
                continue
            p_date = p.started_at[:10]
            if p_date.startswith(str(year)):
                heatmap[p_date] = heatmap.get(p_date, 0) + 1
        return heatmap

    def get_category_pomodoro_stats(self) -> List[Dict[str, Any]]:
        """按分类统计番茄数"""
        # 收集每个任务的番茄数
        task_pomodoros = {}
        for p in self.pomodoros:
            if p.completed:
                task_pomodoros[p.task_id] = task_pomodoros.get(p.task_id, 0) + 1

        # 按分类汇总
        category_stats = {}
        for task in self.tasks:
            cat_id = task.category_id or "uncategorized"
            if task.id in task_pomodoros:
                category_stats[cat_id] = category_stats.get(cat_id, 0) + task_pomodoros[task.id]

        # 转换为列表格式
        result = []
        for cat_id, count in category_stats.items():
            if cat_id == "uncategorized":
                result.append({"category_id": "", "name": "未分类", "icon": "📋", "count": count})
            else:
                cat = self.get_category(cat_id)
                if cat:
                    result.append({
                        "category_id": cat_id,
                        "name": cat.name,
                        "icon": cat.icon,
                        "color": cat.color,
                        "count": count
                    })

        return sorted(result, key=lambda x: x["count"], reverse=True)

    # ===== 统计 =====
    def get_stats(self, start_date: str = "", end_date: str = "") -> Dict[str, Any]:
        tasks = self.tasks
        if start_date and end_date:
            tasks = [t for t in tasks if start_date <= t.created_at[:10] <= end_date]

        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == "completed")
        in_progress = sum(1 for t in tasks if t.status == "in_progress")
        not_started = sum(1 for t in tasks if t.status == "not_started")

        pomodoros = self.pomodoros
        if start_date and end_date:
            pomodoros = [p for p in pomodoros
                        if start_date <= p.started_at[:10] <= end_date]
        pomodoro_completed = sum(1 for p in pomodoros if p.completed)
        pomodoro_minutes = sum(p.duration for p in pomodoros if p.completed)

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "not_started_tasks": not_started,
            "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
            "pomodoro_count": pomodoro_completed,
            "pomodoro_minutes": pomodoro_minutes,
            "pomodoro_hours": round(pomodoro_minutes / 60, 1)
        }

    def get_daily_stats(self, date: str) -> Dict[str, Any]:
        tasks_created = sum(1 for t in self.tasks if t.created_at.startswith(date))
        tasks_completed = sum(1 for t in self.tasks
                             if t.completed_at and t.completed_at.startswith(date))
        pomodoros = sum(1 for p in self.pomodoros
                       if p.started_at.startswith(date) and p.completed)
        return {
            "date": date,
            "tasks_created": tasks_created,
            "tasks_completed": tasks_completed,
            "pomodoros": pomodoros
        }

    # ===== 设置 =====
    def get_settings(self) -> Settings:
        return self.settings

    def update_settings(self, **kwargs) -> Settings:
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self._save_settings()
        return self.settings

    def get_theme(self) -> str:
        return self.settings.theme

    def save_theme(self, theme: str):
        self.settings.theme = theme
        self._save_settings()

    # ===== 数据导出/导入 =====
    def export_data(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "data": {
                "tasks": [asdict(t) for t in self.tasks],
                "categories": [asdict(c) for c in self.categories],
                "pomodoros": [asdict(p) for p in self.pomodoros],
                "settings": asdict(self.settings)
            }
        }

    def import_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            imported = {"tasks": 0, "categories": 0, "pomodoros": 0}

            if "data" in data:
                inner = data["data"]
                if "tasks" in inner:
                    self.tasks = []
                    for t in inner["tasks"]:
                        subtasks_data = t.pop('subtasks', [])
                        task = Task(**t)
                        task.subtasks = [Subtask(**s) for s in subtasks_data] if subtasks_data else []
                        self.tasks.append(task)
                    imported["tasks"] = len(self.tasks)
                if "categories" in inner:
                    self.categories = [Category(**c) for c in inner["categories"]]
                    imported["categories"] = len(self.categories)
                if "pomodoros" in inner:
                    self.pomodoros = [PomodoroRecord(**p) for p in inner["pomodoros"]]
                    imported["pomodoros"] = len(self.pomodoros)
                if "settings" in inner:
                    self.settings = Settings(**inner["settings"])

            self._save_tasks()
            self._save_categories()
            self._save_pomodoros()
            self._save_settings()

            return {"success": True, "imported": imported}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_data_stats(self) -> Dict[str, int]:
        return {
            "tasks": len(self.tasks),
            "categories": len(self.categories),
            "pomodoros": len(self.pomodoros)
        }

    # ========== 成就系统 ==========

    ACHIEVEMENTS = {
        # 任务达人系列
        "task_10": {"id": "task_10", "name": "初出茅庐", "desc": "完成10个任务", "icon": "🌱", "tier": "bronze", "category": "task", "target": 10},
        "task_50": {"id": "task_50", "name": "小有成就", "desc": "完成50个任务", "icon": "🌿", "tier": "silver", "category": "task", "target": 50},
        "task_100": {"id": "task_100", "name": "任务达人", "desc": "完成100个任务", "icon": "🌳", "tier": "gold", "category": "task", "target": 100},
        "task_500": {"id": "task_500", "name": "效率之王", "desc": "完成500个任务", "icon": "👑", "tier": "diamond", "category": "task", "target": 500},
        # 专注大师系列
        "pomo_10": {"id": "pomo_10", "name": "专注新手", "desc": "完成10个番茄钟", "icon": "🍅", "tier": "bronze", "category": "pomodoro", "target": 10},
        "pomo_50": {"id": "pomo_50", "name": "专注达人", "desc": "完成50个番茄钟", "icon": "🍅", "tier": "silver", "category": "pomodoro", "target": 50},
        "pomo_100": {"id": "pomo_100", "name": "专注大师", "desc": "完成100个番茄钟", "icon": "🔥", "tier": "gold", "category": "pomodoro", "target": 100},
        "pomo_500": {"id": "pomo_500", "name": "时间掌控者", "desc": "完成500个番茄钟", "icon": "⏰", "tier": "diamond", "category": "pomodoro", "target": 500},
        # 连续打卡系列
        "streak_3": {"id": "streak_3", "name": "三日坚持", "desc": "连续3天完成任务", "icon": "📅", "tier": "bronze", "category": "streak", "target": 3},
        "streak_7": {"id": "streak_7", "name": "一周达人", "desc": "连续7天完成任务", "icon": "🗓️", "tier": "silver", "category": "streak", "target": 7},
        "streak_14": {"id": "streak_14", "name": "两周坚持", "desc": "连续14天完成任务", "icon": "💪", "tier": "gold", "category": "streak", "target": 14},
        "streak_30": {"id": "streak_30", "name": "月度冠军", "desc": "连续30天完成任务", "icon": "🏆", "tier": "diamond", "category": "streak", "target": 30},
        # 早起鸟儿系列
        "early_5": {"id": "early_5", "name": "早起新秀", "desc": "9点前完成5个任务", "icon": "🌅", "tier": "bronze", "category": "early", "target": 5},
        "early_20": {"id": "early_20", "name": "晨光达人", "desc": "9点前完成20个任务", "icon": "☀️", "tier": "silver", "category": "early", "target": 20},
        "early_50": {"id": "early_50", "name": "早起鸟儿", "desc": "9点前完成50个任务", "icon": "🐦", "tier": "gold", "category": "early", "target": 50},
        # 夜猫子系列
        "night_5": {"id": "night_5", "name": "夜行新手", "desc": "22点后完成5个任务", "icon": "🌙", "tier": "bronze", "category": "night", "target": 5},
        "night_20": {"id": "night_20", "name": "夜间达人", "desc": "22点后完成20个任务", "icon": "🦉", "tier": "silver", "category": "night", "target": 20},
        "night_50": {"id": "night_50", "name": "夜猫子", "desc": "22点后完成50个任务", "icon": "🌃", "tier": "gold", "category": "night", "target": 50},
    }

    TIER_COLORS = {
        "bronze": "#CD7F32",
        "silver": "#C0C0C0",
        "gold": "#FFD700",
        "diamond": "#B9F2FF"
    }

    def _load_achievements(self) -> Dict[str, Any]:
        """加载成就数据"""
        path = self.data_dir / "achievements.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"unlocked": {}, "progress": {}, "streak_data": {"current": 0, "last_date": ""}}

    def _save_achievements(self, data: Dict[str, Any]):
        """保存成就数据"""
        path = self.data_dir / "achievements.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_achievements(self) -> Dict[str, Any]:
        """获取所有成就及进度"""
        data = self._load_achievements()
        progress = self._calculate_progress()

        achievements = []
        for aid, info in self.ACHIEVEMENTS.items():
            current = progress.get(info["category"], 0)
            unlocked = aid in data["unlocked"]
            achievements.append({
                **info,
                "current": current,
                "unlocked": unlocked,
                "unlocked_at": data["unlocked"].get(aid, ""),
                "tier_color": self.TIER_COLORS.get(info["tier"], "#888")
            })

        return {
            "achievements": achievements,
            "stats": {
                "total": len(self.ACHIEVEMENTS),
                "unlocked": len(data["unlocked"]),
                "streak": progress.get("streak", 0)
            }
        }

    def _calculate_progress(self) -> Dict[str, int]:
        """计算各类成就的当前进度"""
        completed_tasks = [t for t in self.tasks if t.status == "completed"]
        completed_pomos = [p for p in self.pomodoros if p.completed]

        # 早起/夜猫子统计
        early_count = 0
        night_count = 0
        for t in completed_tasks:
            if t.completed_at:
                try:
                    hour = int(t.completed_at[11:13])
                    if hour < 9:
                        early_count += 1
                    elif hour >= 22:
                        night_count += 1
                except:
                    pass

        # 连续打卡
        streak = self._calculate_streak()

        return {
            "task": len(completed_tasks),
            "pomodoro": len(completed_pomos),
            "streak": streak,
            "early": early_count,
            "night": night_count
        }

    def _calculate_streak(self) -> int:
        """计算连续打卡天数"""
        completed_dates = set()
        for t in self.tasks:
            if t.status == "completed" and t.completed_at:
                try:
                    d = t.completed_at[:10]
                    completed_dates.add(d)
                except:
                    pass

        if not completed_dates:
            return 0

        today = date.today()
        streak = 0
        check_date = today

        while True:
            date_str = check_date.isoformat()
            if date_str in completed_dates:
                streak += 1
                check_date -= timedelta(days=1)
            elif check_date == today:
                # 今天还没完成任务，检查昨天
                check_date -= timedelta(days=1)
            else:
                break

        return streak

    def check_achievements(self) -> List[Dict[str, Any]]:
        """检查并解锁新成就，返回新解锁的成就列表"""
        data = self._load_achievements()
        progress = self._calculate_progress()
        newly_unlocked = []

        for aid, info in self.ACHIEVEMENTS.items():
            if aid in data["unlocked"]:
                continue

            current = progress.get(info["category"], 0)
            if current >= info["target"]:
                now = datetime.now().isoformat()
                data["unlocked"][aid] = now
                newly_unlocked.append({
                    **info,
                    "unlocked_at": now,
                    "tier_color": self.TIER_COLORS.get(info["tier"], "#888")
                })

        if newly_unlocked:
            self._save_achievements(data)

        return newly_unlocked
