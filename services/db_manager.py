"""
SQLite 数据库管理模块
统一管理所有数据的增删改查操作
"""
import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""

    VERSION = "1.0.0"

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 1. 任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'not_started',
                    priority TEXT DEFAULT 'medium',
                    quadrant TEXT DEFAULT '',
                    category_id TEXT DEFAULT '',
                    due_date TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    recurrence TEXT,
                    parent_task_id TEXT DEFAULT '',
                    pomodoro_count INTEGER DEFAULT 0,
                    order_index INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT DEFAULT ''
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_order ON tasks(order_index)")

            # 2. 子任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subtasks (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    completed INTEGER DEFAULT 0,
                    order_index INTEGER DEFAULT 0,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id)")

            # 3. 分类表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    icon TEXT DEFAULT '📁',
                    color TEXT DEFAULT '#C7CEEA',
                    order_index INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_order ON categories(order_index)")

            # 4. 番茄记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pomodoros (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT DEFAULT '',
                    duration INTEGER DEFAULT 25,
                    completed INTEGER DEFAULT 0,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pomodoros_task ON pomodoros(task_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pomodoros_started ON pomodoros(started_at)")

            # 5. 设置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 6. 成就表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id TEXT PRIMARY KEY,
                    unlocked_at TEXT NOT NULL
                )
            """)

            # 7. AI Provider 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_providers (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    config TEXT NOT NULL,
                    capabilities TEXT,
                    stats TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_providers_enabled ON ai_providers(enabled)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_providers_type ON ai_providers(type)")

            # 8. 聊天会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    provider_id TEXT,
                    system_prompt TEXT,
                    message_count INTEGER DEFAULT 0,
                    last_message_at TIMESTAMP,
                    pinned INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message ON chat_sessions(last_message_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_archived ON chat_sessions(archived)")

            # 9. 聊天消息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    provider_id TEXT,
                    token_count INTEGER,
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_seq ON chat_messages(session_id, sequence)")

            # 10. 活跃配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 11. 数据库元信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 设置数据库版本
            cursor.execute("""
                INSERT OR REPLACE INTO db_metadata (key, value, updated_at)
                VALUES ('version', ?, ?)
            """, (self.VERSION, datetime.now().isoformat()))

            conn.commit()
            logger.info(f"数据库初始化成功: {self._db_path}")

        except Exception as e:
            conn.rollback()
            logger.error(f"数据库初始化失败: {e}")
            raise
        finally:
            conn.close()

    def _migrate_add_column(self, cursor, table: str, column: str, col_type: str, default: str = None):
        """安全地为表添加新列"""
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            default_clause = f" DEFAULT {default}" if default else ""
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")
            logger.info(f"迁移：为 {table} 表添加 {column} 列")

    # ========== 通用 CRUD ==========

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行查询"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """执行更新"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            conn.rollback()
            logger.error(f"执行更新失败: {e}")
            raise
        finally:
            conn.close()

    def insert(self, table: str, data: Dict[str, Any]) -> bool:
        """插入数据"""
        data = self._serialize_json_fields(data)
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        try:
            self.execute_update(query, tuple(data.values()))
            return True
        except Exception as e:
            logger.error(f"插入数据失败 (table={table}): {e}")
            return False

    def update(self, table: str, data: Dict[str, Any], where: str, params: tuple = ()) -> bool:
        """更新数据"""
        data = self._serialize_json_fields(data)
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"

        try:
            self.execute_update(query, tuple(data.values()) + params)
            return True
        except Exception as e:
            logger.error(f"更新数据失败 (table={table}): {e}")
            return False

    def delete(self, table: str, where: str, params: tuple = ()) -> bool:
        """删除数据"""
        query = f"DELETE FROM {table} WHERE {where}"
        try:
            self.execute_update(query, params)
            return True
        except Exception as e:
            logger.error(f"删除数据失败 (table={table}): {e}")
            return False

    def get_by_id(self, table: str, id_value: str, id_column: str = 'id') -> Optional[Dict[str, Any]]:
        """根据 ID 获取单条记录"""
        query = f"SELECT * FROM {table} WHERE {id_column} = ?"
        results = self.execute_query(query, (id_value,))
        if results:
            return self._deserialize_json_fields(results[0])
        return None

    def get_all(self, table: str, where: str = "", params: tuple = (), order_by: str = "") -> List[Dict[str, Any]]:
        """获取所有记录"""
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {where}"
        if order_by:
            query += f" ORDER BY {order_by}"
        results = self.execute_query(query, params)
        return [self._deserialize_json_fields(row) for row in results]

    # ========== JSON 序列化 ==========

    def _serialize_json_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """将字典/列表字段序列化为 JSON 字符串"""
        result = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                result[key] = json.dumps(value, ensure_ascii=False)
            else:
                result[key] = value
        return result

    def _deserialize_json_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """将 JSON 字符串字段反序列化"""
        result = dict(data)
        json_fields = ['config', 'capabilities', 'stats', 'tags', 'recurrence', 'meta', 'metadata']

        for field in json_fields:
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    # ========== 设置相关 ==========

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取设置"""
        row = self.get_by_id("settings", key, "key")
        if not row:
            return default
        value = row.get("value")
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def set_setting(self, key: str, value: Any) -> bool:
        """设置配置"""
        try:
            json_value = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.error(f"配置值序列化失败 (key={key}): {e}")
            return False

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, json_value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"配置写入失败 (key={key}): {e}")
            return False

    # ========== 活跃配置 ==========

    def get_active_config(self, key: str, default: Any = None) -> Any:
        """获取活跃配置"""
        row = self.get_by_id("active_config", key, "key")
        if not row:
            return default
        value = row.get("value")
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def set_active_config(self, key: str, value: Any) -> bool:
        """设置活跃配置"""
        try:
            json_value = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return False

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO active_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, json_value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"活跃配置写入失败 (key={key}): {e}")
            return False
