"""
牛牛待办 - 单元测试
测试 TodoService 核心业务逻辑
"""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))

from services.todo_service import (
    TodoService, Task, Category, PomodoroRecord, Settings, Subtask,
    VALID_STATUSES, VALID_PRIORITIES, VALID_QUADRANTS
)


class TestTodoService(unittest.TestCase):
    """测试 TodoService"""

    def setUp(self):
        """每个测试前创建临时数据目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.service = TodoService(data_dir=self.temp_dir)

    def tearDown(self):
        """清理临时文件"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestTaskCRUD(TestTodoService):
    """测试任务 CRUD"""

    def test_add_task_basic(self):
        """测试基本任务创建"""
        task = self.service.add_task(title="测试任务")
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "测试任务")
        self.assertEqual(task.status, "not_started")
        self.assertEqual(task.priority, "medium")

    def test_add_task_with_all_fields(self):
        """测试带完整字段的任务创建"""
        task = self.service.add_task(
            title="完整任务",
            description="这是描述",
            priority="urgent",
            category_id="cat_123",
            due_date="2024-12-31",
            tags=["重要", "工作"],
            quadrant="q1"
        )
        self.assertEqual(task.title, "完整任务")
        self.assertEqual(task.description, "这是描述")
        self.assertEqual(task.priority, "urgent")
        self.assertEqual(task.quadrant, "q1")
        self.assertEqual(task.due_date, "2024-12-31")

    def test_add_task_empty_title_raises(self):
        """测试空标题抛出异常"""
        with self.assertRaises(ValueError):
            self.service.add_task(title="")
        with self.assertRaises(ValueError):
            self.service.add_task(title="   ")

    def test_add_task_invalid_priority_defaults(self):
        """测试无效优先级默认为 medium"""
        task = self.service.add_task(title="任务", priority="invalid")
        self.assertEqual(task.priority, "medium")

    def test_get_task(self):
        """测试获取单个任务"""
        task = self.service.add_task(title="待获取")
        found = self.service.get_task(task.id)
        self.assertEqual(found.title, "待获取")

    def test_get_task_not_found(self):
        """测试获取不存在的任务"""
        found = self.service.get_task("nonexistent")
        self.assertIsNone(found)

    def test_update_task(self):
        """测试更新任务"""
        task = self.service.add_task(title="原标题")
        updated = self.service.update_task(task.id, title="新标题", priority="high")
        self.assertEqual(updated.title, "新标题")
        self.assertEqual(updated.priority, "high")

    def test_update_task_status_sets_completed_at(self):
        """测试完成状态自动设置完成时间"""
        task = self.service.add_task(title="任务")
        self.assertEqual(task.completed_at, "")

        updated = self.service.update_task(task.id, status="completed")
        self.assertNotEqual(updated.completed_at, "")

        # 恢复未完成
        restored = self.service.update_task(task.id, status="not_started")
        self.assertEqual(restored.completed_at, "")

    def test_delete_task(self):
        """测试删除任务"""
        task = self.service.add_task(title="待删除")
        self.assertTrue(self.service.delete_task(task.id))
        self.assertIsNone(self.service.get_task(task.id))

    def test_delete_task_not_found(self):
        """测试删除不存在的任务"""
        self.assertFalse(self.service.delete_task("nonexistent"))

    def test_get_tasks_filtering(self):
        """测试任务筛选"""
        self.service.add_task(title="工作1", priority="high")
        t2 = self.service.add_task(title="工作2", priority="low")
        self.service.update_task(t2.id, status="completed")
        t3 = self.service.add_task(title="生活", priority="high")
        self.service.update_task(t3.id, status="in_progress")

        # 按状态筛选
        completed = self.service.get_tasks(status="completed")
        self.assertEqual(len(completed), 1)

        # 按优先级筛选
        high = self.service.get_tasks(priority="high")
        self.assertEqual(len(high), 2)

        # 搜索
        results = self.service.get_tasks(search="工作")
        self.assertEqual(len(results), 2)


class TestTags(TestTodoService):
    """测试标签相关能力"""

    def test_get_all_tags_dedup_and_sorted(self):
        """测试获取所有标签：去重、过滤空白、排序"""
        self.service.add_task(title="任务1", tags=[" 工作 ", "重要", "", None])
        self.service.add_task(title="任务2", tags=["生活", "工作"])

        tags = self.service.get_all_tags()

        self.assertEqual(tags, sorted({"工作", "重要", "生活"}))

    def test_get_tasks_by_tag_and_get_tasks_tag_filter(self):
        """测试按标签筛选任务（包含 get_tasks(tag=...) 的兼容过滤）"""
        t1 = self.service.add_task(title="A", tags=["工作"])
        self.service.add_task(title="B", tags=["生活"])
        t3 = self.service.add_task(title="C", tags=["工作", "重要"])

        by_tag = self.service.get_tasks_by_tag(" 工作 ")
        self.assertEqual([t.id for t in by_tag], [t1.id, t3.id])

        by_get_tasks = self.service.get_tasks(tag="工作")
        self.assertEqual([t.id for t in by_get_tasks], [t1.id, t3.id])

        self.assertEqual(self.service.get_tasks_by_tag(""), [])
        self.assertEqual(len(self.service.get_tasks(tag="")), 3)


class TestSubtasks(TestTodoService):
    """测试子任务功能"""

    def test_add_subtask(self):
        """测试添加子任务"""
        task = self.service.add_task(title="主任务")
        subtask = self.service.add_subtask(task.id, "子任务1")

        self.assertIsNotNone(subtask)
        self.assertEqual(subtask.title, "子任务1")
        self.assertFalse(subtask.completed)
        self.assertEqual(subtask.order, 0)

        # 验证子任务已添加到任务中
        updated_task = self.service.get_task(task.id)
        self.assertEqual(len(updated_task.subtasks), 1)

    def test_add_subtask_empty_title_raises(self):
        """测试空标题抛出异常"""
        task = self.service.add_task(title="主任务")
        with self.assertRaises(ValueError):
            self.service.add_subtask(task.id, "")
        with self.assertRaises(ValueError):
            self.service.add_subtask(task.id, "   ")

    def test_add_subtask_invalid_task_raises(self):
        """测试无效任务ID抛出异常"""
        with self.assertRaises(ValueError):
            self.service.add_subtask("nonexistent", "子任务")

    def test_toggle_subtask(self):
        """测试切换子任务状态"""
        task = self.service.add_task(title="主任务")
        subtask = self.service.add_subtask(task.id, "子任务")

        # 切换为已完成
        toggled = self.service.toggle_subtask(task.id, subtask.id)
        self.assertTrue(toggled.completed)

        # 再次切换为未完成
        toggled = self.service.toggle_subtask(task.id, subtask.id)
        self.assertFalse(toggled.completed)

    def test_delete_subtask(self):
        """测试删除子任务"""
        task = self.service.add_task(title="主任务")
        subtask = self.service.add_subtask(task.id, "子任务")

        result = self.service.delete_subtask(task.id, subtask.id)
        self.assertTrue(result)

        updated_task = self.service.get_task(task.id)
        self.assertEqual(len(updated_task.subtasks), 0)

    def test_delete_subtask_not_found(self):
        """测试删除不存在的子任务"""
        task = self.service.add_task(title="主任务")
        result = self.service.delete_subtask(task.id, "nonexistent")
        self.assertFalse(result)

    def test_get_subtask_progress(self):
        """测试获取子任务进度"""
        task = self.service.add_task(title="主任务")
        self.service.add_subtask(task.id, "子任务1")
        sub2 = self.service.add_subtask(task.id, "子任务2")
        self.service.add_subtask(task.id, "子任务3")

        # 完成一个子任务
        self.service.toggle_subtask(task.id, sub2.id)

        progress = self.service.get_subtask_progress(task.id)
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["total"], 3)

    def test_reorder_subtasks(self):
        """测试重排序子任务"""
        task = self.service.add_task(title="主任务")
        s1 = self.service.add_subtask(task.id, "子任务1")
        s2 = self.service.add_subtask(task.id, "子任务2")
        s3 = self.service.add_subtask(task.id, "子任务3")

        # 重新排序: 3, 1, 2
        self.service.reorder_subtasks(task.id, [s3.id, s1.id, s2.id])

        updated_task = self.service.get_task(task.id)
        self.assertEqual(updated_task.subtasks[0].id, s3.id)
        self.assertEqual(updated_task.subtasks[1].id, s1.id)
        self.assertEqual(updated_task.subtasks[2].id, s2.id)

    def test_subtask_persistence(self):
        """测试子任务持久化"""
        task = self.service.add_task(title="主任务")
        self.service.add_subtask(task.id, "子任务1")
        self.service.add_subtask(task.id, "子任务2")

        # 重新加载服务
        new_service = TodoService(data_dir=self.temp_dir)
        loaded_task = new_service.get_task(task.id)

        self.assertEqual(len(loaded_task.subtasks), 2)
        self.assertEqual(loaded_task.subtasks[0].title, "子任务1")


class TestCategoryCRUD(TestTodoService):
    """测试分类 CRUD"""

    def test_default_categories(self):
        """测试默认分类"""
        categories = self.service.get_categories()
        self.assertEqual(len(categories), 4)
        names = [c.name for c in categories]
        self.assertIn("工作", names)
        self.assertIn("学习", names)

    def test_add_category(self):
        """测试添加分类"""
        cat = self.service.add_category(name="自定义", icon="🎯", color="#FF0000")
        self.assertEqual(cat.name, "自定义")
        self.assertEqual(cat.icon, "🎯")

    def test_add_category_empty_name_raises(self):
        """测试空分类名抛出异常"""
        with self.assertRaises(ValueError):
            self.service.add_category(name="")

    def test_delete_category_clears_task_association(self):
        """测试删除分类清除任务关联"""
        cat = self.service.add_category(name="待删除")
        task = self.service.add_task(title="任务", category_id=cat.id)

        self.service.delete_category(cat.id)

        # 任务的分类应被清空
        updated_task = self.service.get_task(task.id)
        self.assertEqual(updated_task.category_id, "")


class TestPomodoro(TestTodoService):
    """测试番茄钟"""

    def test_start_pomodoro(self):
        """测试开始番茄钟"""
        task = self.service.add_task(title="番茄任务")
        record = self.service.start_pomodoro(task.id)

        self.assertEqual(record.task_id, task.id)
        self.assertEqual(record.duration, 25)
        self.assertFalse(record.completed)

    def test_start_pomodoro_invalid_task(self):
        """测试对不存在任务启动番茄钟"""
        with self.assertRaises(ValueError):
            self.service.start_pomodoro("nonexistent")

    def test_complete_pomodoro(self):
        """测试完成番茄钟"""
        task = self.service.add_task(title="番茄任务")
        record = self.service.start_pomodoro(task.id)

        completed = self.service.complete_pomodoro(record.id)
        self.assertTrue(completed.completed)
        self.assertNotEqual(completed.ended_at, "")

        # 任务番茄计数应增加
        updated_task = self.service.get_task(task.id)
        self.assertEqual(updated_task.pomodoro_count, 1)

    def test_cancel_pomodoro(self):
        """测试取消番茄钟"""
        task = self.service.add_task(title="番茄任务")
        record = self.service.start_pomodoro(task.id)

        self.assertTrue(self.service.cancel_pomodoro(record.id))

        # 任务番茄计数不应增加
        updated_task = self.service.get_task(task.id)
        self.assertEqual(updated_task.pomodoro_count, 0)


class TestSettings(TestTodoService):
    """测试设置"""

    def test_default_settings(self):
        """测试默认设置"""
        settings = self.service.get_settings()
        self.assertEqual(settings.pomodoro_work, 25)
        self.assertEqual(settings.pomodoro_break, 5)
        self.assertEqual(settings.theme, "cute")

    def test_update_settings(self):
        """测试更新设置"""
        updated = self.service.update_settings(
            pomodoro_work=30,
            theme="dark"
        )
        self.assertEqual(updated.pomodoro_work, 30)
        self.assertEqual(updated.theme, "dark")

    def test_settings_persistence(self):
        """测试设置持久化"""
        self.service.update_settings(theme="neon")

        # 重新加载服务
        new_service = TodoService(data_dir=self.temp_dir)
        settings = new_service.get_settings()
        self.assertEqual(settings.theme, "neon")


class TestDataExportImport(TestTodoService):
    """测试数据导出导入"""

    def test_export_data(self):
        """测试数据导出"""
        self.service.add_task(title="导出任务")
        self.service.add_category(name="导出分类")

        data = self.service.export_data()

        self.assertIn("version", data)
        self.assertIn("data", data)
        self.assertEqual(len(data["data"]["tasks"]), 1)
        self.assertEqual(len(data["data"]["categories"]), 5)  # 4 默认 + 1 自定义

    def test_import_data(self):
        """测试数据导入"""
        # 准备导入数据
        import_data = {
            "version": "1.0",
            "data": {
                "tasks": [
                    {"id": "task_1", "title": "导入任务", "description": "",
                     "status": "not_started", "priority": "medium", "quadrant": "",
                     "category_id": "", "due_date": "", "tags": [],
                     "created_at": "", "completed_at": "", "pomodoro_count": 0, "order": 0}
                ],
                "categories": [
                    {"id": "cat_1", "name": "导入分类", "icon": "📦", "color": "#000", "order": 0}
                ],
                "pomodoros": [],
                "settings": {"pomodoro_work": 30, "pomodoro_break": 10,
                            "pomodoro_long_break": 20, "theme": "dark",
                            "default_view": "kanban", "sticky_visible": False,
                            "sticky_opacity": 1.0, "sticky_position_x": 30,
                            "sticky_position_y": 30}
            }
        }

        result = self.service.import_data(import_data)

        self.assertTrue(result["success"])
        self.assertEqual(len(self.service.tasks), 1)
        self.assertEqual(self.service.tasks[0].title, "导入任务")
        self.assertEqual(self.service.settings.pomodoro_work, 30)


class TestStats(TestTodoService):
    """测试统计"""

    def test_get_stats(self):
        """测试获取统计"""
        t1 = self.service.add_task(title="任务1")
        self.service.update_task(t1.id, status="completed")
        t2 = self.service.add_task(title="任务2")
        self.service.update_task(t2.id, status="in_progress")
        self.service.add_task(title="任务3")

        stats = self.service.get_stats()

        self.assertEqual(stats["total_tasks"], 3)
        self.assertEqual(stats["completed_tasks"], 1)
        self.assertEqual(stats["in_progress_tasks"], 1)
        self.assertEqual(stats["not_started_tasks"], 1)

    def test_get_data_stats(self):
        """测试数据统计"""
        self.service.add_task(title="任务")
        task = self.service.add_task(title="番茄任务")
        self.service.start_pomodoro(task.id)

        stats = self.service.get_data_stats()

        self.assertEqual(stats["tasks"], 2)
        self.assertEqual(stats["categories"], 4)
        self.assertEqual(stats["pomodoros"], 1)


class TestTaskOrdering(TestTodoService):
    """测试任务排序"""

    def test_task_order_increments(self):
        """测试任务顺序自动递增"""
        t1 = self.service.add_task(title="任务1")
        t2 = self.service.add_task(title="任务2")
        t3 = self.service.add_task(title="任务3")

        self.assertEqual(t1.order, 0)
        self.assertEqual(t2.order, 1)
        self.assertEqual(t3.order, 2)

    def test_reorder_tasks(self):
        """测试重新排序任务"""
        t1 = self.service.add_task(title="任务1")
        t2 = self.service.add_task(title="任务2")
        t3 = self.service.add_task(title="任务3")

        # 重新排序: 3, 1, 2
        self.service.reorder_tasks([t3.id, t1.id, t2.id])

        tasks = self.service.get_tasks()
        self.assertEqual(tasks[0].id, t3.id)
        self.assertEqual(tasks[1].id, t1.id)
        self.assertEqual(tasks[2].id, t2.id)


class TestRecurringTasks(TestTodoService):
    """测试重复任务"""

    def test_set_recurrence_daily(self):
        """测试设置每日重复"""
        task = self.service.add_task(title="每日任务", due_date="2024-01-01")
        result = self.service.set_recurrence(task.id, {
            "type": "daily",
            "interval": 1,
            "end_type": "never"
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.recurrence["type"], "daily")
        self.assertEqual(result.recurrence["interval"], 1)

    def test_set_recurrence_weekly(self):
        """测试设置每周重复"""
        task = self.service.add_task(title="每周任务", due_date="2024-01-01")
        result = self.service.set_recurrence(task.id, {
            "type": "weekly",
            "interval": 1,
            "weekdays": [0, 2, 4]  # 周一、周三、周五
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.recurrence["type"], "weekly")
        self.assertEqual(result.recurrence["weekdays"], [0, 2, 4])

    def test_set_recurrence_monthly(self):
        """测试设置每月重复"""
        task = self.service.add_task(title="每月任务", due_date="2024-01-15")
        result = self.service.set_recurrence(task.id, {
            "type": "monthly",
            "interval": 1,
            "month_day": 15
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.recurrence["type"], "monthly")
        self.assertEqual(result.recurrence["month_day"], 15)

    def test_clear_recurrence(self):
        """测试清除重复规则"""
        task = self.service.add_task(title="重复任务", due_date="2024-01-01")
        self.service.set_recurrence(task.id, {"type": "daily"})
        result = self.service.clear_recurrence(task.id)
        self.assertIsNone(result.recurrence)

    def test_normalize_recurrence_rule(self):
        """测试重复规则规范化"""
        normalized = self.service._normalize_recurrence_rule({
            "type": "weekly",
            "interval": 0,  # 无效值，应变为1
        })
        self.assertEqual(normalized["interval"], 1)
        self.assertEqual(normalized["end_type"], "never")
        self.assertEqual(normalized["weekdays"], [])

    def test_get_next_occurrence_daily(self):
        """测试每日重复的下一次日期计算"""
        task = self.service.add_task(title="每日任务", due_date="2024-01-01")
        self.service.set_recurrence(task.id, {"type": "daily", "interval": 2})
        from datetime import date
        next_date = self.service._get_next_occurrence(task, date(2024, 1, 1))
        self.assertEqual(next_date, "2024-01-03")

    def test_get_next_occurrence_monthly(self):
        """测试每月重复的下一次日期计算"""
        task = self.service.add_task(title="每月任务", due_date="2024-01-31")
        self.service.set_recurrence(task.id, {"type": "monthly", "interval": 1})
        from datetime import date
        next_date = self.service._get_next_occurrence(task, date(2024, 1, 31))
        # 2月没有31日，应为2月29日（2024是闰年）
        self.assertEqual(next_date, "2024-02-29")

    def test_should_not_generate_when_count_limit_reached(self):
        """测试达到次数限制后不再生成"""
        task = self.service.add_task(title="有限任务", due_date="2024-01-01")
        self.service.set_recurrence(task.id, {
            "type": "daily",
            "end_type": "count",
            "end_count": 3
        })
        # 手动设置 generated_count 模拟已生成 3 次（因为 set_recurrence 会重置为 0）
        task.recurrence["generated_count"] = 3
        from datetime import date
        should = self.service._should_generate_occurrence(task, date(2024, 1, 2))
        self.assertFalse(should)

    def test_set_recurrence_without_due_date_raises(self):
        """测试没有截止日期时设置重复规则抛出异常"""
        task = self.service.add_task(title="无截止日期任务")
        with self.assertRaises(ValueError):
            self.service.set_recurrence(task.id, {"type": "daily"})

    def test_normalize_recurrence_rule_invalid_input(self):
        """测试非法输入的规范化处理"""
        # 非法的 interval
        normalized = self.service._normalize_recurrence_rule({
            "type": "daily",
            "interval": "abc"
        })
        self.assertEqual(normalized["interval"], 1)

        # 非法的 weekdays
        normalized = self.service._normalize_recurrence_rule({
            "type": "weekly",
            "weekdays": ["a", 1, 10, -1, 3]  # 只有 1 和 3 是有效的
        })
        self.assertEqual(normalized["weekdays"], [1, 3])

        # 非法的 type
        normalized = self.service._normalize_recurrence_rule({
            "type": "invalid_type"
        })
        self.assertEqual(normalized["type"], "")

    def test_get_next_occurrence_yearly_leap_year(self):
        """测试每年重复处理闰年 2/29"""
        task = self.service.add_task(title="闰年任务", due_date="2024-02-29")
        self.service.set_recurrence(task.id, {"type": "yearly", "interval": 1})
        from datetime import date
        # 2025 不是闰年，应回退到 2/28
        next_date = self.service._get_next_occurrence(task, date(2024, 2, 29))
        self.assertEqual(next_date, "2025-02-28")


if __name__ == "__main__":
    unittest.main(verbosity=2)
