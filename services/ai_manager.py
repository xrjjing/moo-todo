# -*- coding: utf-8 -*-
"""
AI Manager 统一管理器
负责 Provider 管理、聊天会话、模型获取

模块定位：
- 上游：`api.py` 的 AI Provider / AI Chat 相关接口
- 下游：`DatabaseManager` 持久化配置与聊天历史，`ai_providers.py` 发起真实模型请求

它把“配置层”“会话层”“请求层”统一收口，避免前端直接感知不同服务商的差异。
"""

import json
import logging
import os
import time
import uuid
import httpx
from typing import Dict, List, Any, Optional
from pathlib import Path

from .ai_providers import create_provider
from .db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class AIManager:
    """统一的 AI 管理器。

    主要职责：
    1. 维护已配置 Provider 的内存态与当前活跃 Provider。
    2. 负责临时连通性测试与模型列表拉取。
    3. 管理 AI 聊天会话与消息历史。
    4. 统计 Provider 调用次数、失败次数、平均时延。

    排查建议：
    - “AI 设置页看不到服务商”：先看 `_load_config()` / `get_available_providers()`
    - “模型列表拉取失败”：看 `fetch_models()`
    - “聊天消息没保存” 或 “会话错乱”：看 `create_session()` / `add_message()`
    """

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._providers = {}
        self._active_provider_id = None
        self._stats_cache = {}
        self._load_config()

    def _load_config(self):
        """从数据库加载 AI Provider 配置并重建运行态缓存。

        这是 AI 子系统的核心初始化入口：
        - 从 `ai_providers` 读取配置
        - 构建每个启用 Provider 的实例
        - 恢复当前活跃 Provider 指针
        - 重建统计缓存
        """
        try:
            providers_config = self._db.get_all('ai_providers', order_by="updated_at DESC")

            self._providers = {}
            self._stats_cache = {}

            for provider_config in providers_config:
                provider_id = provider_config.get('id')
                if not provider_id:
                    continue

                self._stats_cache[provider_id] = provider_config.get('stats', {
                    'total_requests': 0,
                    'failed_requests': 0,
                    'total_latency': 0,
                    'avg_latency': 0
                })

                if not provider_config.get('enabled', True):
                    continue

                try:
                    self._providers[provider_id] = create_provider(provider_config)
                    logger.info(f"加载 Provider: {provider_id}")
                except Exception as e:
                    logger.error(f"加载 Provider 失败: {e}")

            active_record = self._db.get_active_config('active_ai_provider')
            if active_record and active_record in self._providers:
                self._active_provider_id = active_record
            elif self._providers:
                self._active_provider_id = next(iter(self._providers))
                self._db.set_active_config('active_ai_provider', self._active_provider_id)
                logger.info(f"自动选择 Provider: {self._active_provider_id}")
            else:
                self._active_provider_id = None

            logger.info(f"AI Manager 初始化完成，活跃 Provider: {self._active_provider_id}")

        except Exception as e:
            logger.error(f"从数据库加载配置失败: {e}")

    def get_provider(self, provider_id: Optional[str] = None):
        """获取指定或当前活跃的 Provider 实例。"""
        pid = provider_id or self._active_provider_id

        if not pid:
            raise ValueError("未配置活跃的 AI Provider")

        if pid not in self._providers:
            raise ValueError(f"Provider {pid} 不存在或未启用")

        return self._providers[pid]

    async def chat(self, prompt: str, system_prompt: Optional[str] = None,
                   provider_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """无历史对话入口。

        适用于快速测试或不需要会话持久化的场景；真正的聊天窗口通常走 `chat_with_history()`。
        """
        pid = provider_id or self._active_provider_id
        provider = self.get_provider(pid)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        request_id = str(uuid.uuid4())

        try:
            result = await provider.chat(messages, **kwargs)
            latency = time.time() - start_time

            self._update_stats(pid, success=True, latency=latency)

            return {
                'success': True,
                'response': result,
                'request_id': request_id,
                'provider_id': pid,
                'latency': latency
            }

        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(pid, success=False, latency=latency)
            error_msg = str(e) or type(e).__name__
            logger.error(f"AI 请求失败: {error_msg}")
            raise

    async def chat_with_history(self, messages: List[Dict], provider_id: Optional[str] = None,
                                **kwargs) -> Dict[str, Any]:
        """带历史记录的对话接口。

        上游通常来自 `Api.send_chat_message()`。
        它只负责把已经整理好的完整消息列表交给 Provider，不负责拼装历史。
        """
        pid = provider_id or self._active_provider_id
        provider = self.get_provider(pid)

        start_time = time.time()
        request_id = str(uuid.uuid4())

        try:
            result = await provider.chat(messages, **kwargs)
            latency = time.time() - start_time

            self._update_stats(pid, success=True, latency=latency)

            return {
                'success': True,
                'response': result,
                'request_id': request_id,
                'provider_id': pid,
                'latency': latency
            }

        except Exception as e:
            latency = time.time() - start_time
            self._update_stats(pid, success=False, latency=latency)
            raise

    def switch_provider(self, provider_id: str):
        """切换当前活跃 Provider，并同步写入 active_config。"""
        if provider_id not in self._providers:
            raise ValueError(f"Provider {provider_id} 不存在或未启用")

        old_provider_id = self._active_provider_id
        self._active_provider_id = provider_id

        if not self._db.set_active_config('active_ai_provider', provider_id):
            self._active_provider_id = old_provider_id
            raise RuntimeError("保存活跃 Provider 失败")

        logger.info(f"切换到 Provider: {provider_id}")

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """获取前端可直接展示的 Provider 列表。

        这里会隐藏敏感字段，只暴露安全摘要，比如是否存在 API Key、默认模型、统计数据等。
        """
        result = []

        try:
            providers_config = self._db.get_all('ai_providers', where="enabled = 1", order_by="updated_at DESC")

            for provider_config in providers_config:
                if not provider_config.get('enabled', True):
                    continue

                provider_id = provider_config['id']
                stats = self._stats_cache.get(provider_id, provider_config.get('stats', {}))

                config = provider_config.get('config', {})
                safe_config = {
                    'base_url': config.get('base_url', ''),
                    'default_model': config.get('default_model', ''),
                    'has_api_key': bool(config.get('api_key'))
                }

                result.append({
                    'id': provider_id,
                    'name': provider_config.get('name', provider_id),
                    'type': provider_config.get('type'),
                    'active': provider_id == self._active_provider_id,
                    'capabilities': provider_config.get('capabilities', {}),
                    'config': safe_config,
                    'stats': stats
                })

        except Exception as e:
            logger.error(f"获取 Provider 列表失败: {e}")

        return result

    async def fetch_models(self, temp_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """动态获取可用模型列表。

        设计思路：
        - 优先使用当前用户填写的临时配置直接请求远端；
        - 如果官方 Provider 缺少 API Key，则退回本地固定模型列表，保证设置页也能有候选项。

        排查建议：
        - OpenAI/Claude 返回 401/403：优先检查 temp_config 与环境变量中的 API Key。
        - 兼容接口拿不到模型：继续看 `_fetch_openai_models()` 的 URL 拼接与响应格式。
        """
        provider_type = temp_config.get('type')
        inner_config = temp_config.get('config', {})
        api_key = temp_config.get('api_key') or inner_config.get('api_key')
        base_url = temp_config.get('base_url') or inner_config.get('base_url')

        flat_config = {
            'api_key': api_key,
            'base_url': base_url,
            'api_version': temp_config.get('api_version') or inner_config.get('api_version')
        }

        try:
            if provider_type == 'openai':
                if not api_key:
                    api_key = os.environ.get("OPENAI_API_KEY")
                    flat_config['api_key'] = api_key
                if api_key:
                    return await self._fetch_openai_models(flat_config)
                else:
                    return self._get_openai_models()
            elif provider_type == 'openai-compatible':
                return await self._fetch_openai_models(flat_config)
            elif provider_type == 'claude':
                if not api_key:
                    api_key = os.environ.get("ANTHROPIC_API_KEY")
                    flat_config['api_key'] = api_key
                if api_key:
                    try:
                        return await self._fetch_claude_models(flat_config)
                    except Exception:
                        return self._get_claude_models()
                else:
                    return self._get_claude_models()
            else:
                return []

        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            raise

    async def _fetch_openai_models(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 OpenAI 兼容 `/models` 接口获取模型列表。"""
        base_url = config.get('base_url', 'https://api.openai.com/v1')
        url = f"{base_url.rstrip('/')}/models"

        api_key = config.get('api_key')
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("未找到 OpenAI API Key")

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get('data', []):
                models.append({
                    'id': model['id'],
                    'name': model.get('id'),
                    'created': model.get('created'),
                    'owned_by': model.get('owned_by', 'unknown')
                })

            chat_models = [m for m in models if any(
                keyword in m['id'].lower() for keyword in ['gpt', 'chat', 'turbo']
            )]
            other_models = [m for m in models if m not in chat_models]

            return chat_models + other_models

    def _get_openai_models(self) -> List[Dict[str, Any]]:
        """返回内置的 OpenAI 模型兜底列表。"""
        return [
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'description': '最新多模态模型'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'description': '高性能模型'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'description': '快速响应模型'}
        ]

    async def _fetch_claude_models(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Claude API 获取模型列表。"""
        base_url = config.get('base_url', 'https://api.anthropic.com')
        base = base_url.rstrip('/')
        if base.endswith('/v1/models') or base.endswith('/models'):
            url = base
        elif base.endswith('/v1'):
            url = f"{base}/models"
        else:
            url = f"{base}/v1/models"

        api_key = config.get('api_key')
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError("未找到 Claude API Key")

        api_version = config.get('api_version', '2023-06-01')

        headers = {
            'x-api-key': api_key,
            'Authorization': f'Bearer {api_key}',
            'anthropic-version': api_version,
            'Content-Type': 'application/json'
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get('data', []):
                model_id = model.get('id')
                if not model_id or 'claude' not in model_id.lower():
                    continue
                models.append({
                    'id': model_id,
                    'name': model_id,
                    'created': model.get('created_at') or model.get('created'),
                    'owned_by': model.get('owned_by', 'anthropic')
                })

            return models

    def _get_claude_models(self) -> List[Dict[str, Any]]:
        """返回内置的 Claude 模型兜底列表。"""
        return [
            {'id': 'claude-3-5-sonnet-20241022', 'name': 'Claude 3.5 Sonnet', 'description': '平衡性能与速度'},
            {'id': 'claude-3-opus-20240229', 'name': 'Claude 3 Opus', 'description': '最强推理能力'},
            {'id': 'claude-3-haiku-20240307', 'name': 'Claude 3 Haiku', 'description': '最快响应速度'}
        ]

    async def test_connection(self, temp_config: Dict[str, Any]) -> Dict[str, Any]:
        """测试 Provider 连接。

        前端 AI 设置弹窗点击“测试连接”时会走到这里。
        返回结构同时包含成功标志、简单响应文本与延迟，便于页面直接展示结果。
        """
        try:
            provider = create_provider(temp_config)
            test_prompt = "Say 'Hello' in one word."
            messages = [{"role": "user", "content": test_prompt}]

            start_time = time.time()
            response = await provider.chat(messages, max_tokens=10)
            latency = time.time() - start_time

            return {
                'success': True,
                'response': response,
                'latency': round(latency, 2)
            }

        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def save_provider(self, provider_config: Dict[str, Any]) -> Dict[str, Any]:
        """保存 Provider 配置。

        处理两种场景：
        - 已存在：更新配置
        - 不存在：新增配置；如果这是首个 Provider，会自动设为活跃 Provider
        """
        try:
            provider_id = provider_config['id']
            from datetime import datetime

            data = {
                'id': provider_id,
                'type': provider_config.get('type', ''),
                'name': provider_config.get('name', provider_id),
                'enabled': 1 if provider_config.get('enabled', True) else 0,
                'config': provider_config.get('config', {}),
                'capabilities': provider_config.get('capabilities', {}),
                'stats': provider_config.get('stats', {}),
                'updated_at': datetime.now().isoformat()
            }

            existing = self._db.get_by_id('ai_providers', provider_id)
            if existing:
                success = self._db.update('ai_providers', data, 'id = ?', (provider_id,))
            else:
                success = self._db.insert('ai_providers', data)
                if success:
                    all_providers = self._db.get_all('ai_providers', order_by="")
                    if len(all_providers) == 1:
                        self._db.set_active_config('active_ai_provider', provider_id)

            if not success:
                return {'success': False, 'error': '数据库写入失败'}

            self._load_config()
            return {'success': True}

        except Exception as e:
            logger.error(f"保存 Provider 失败: {e}")
            return {'success': False, 'error': str(e)}

    def delete_provider(self, provider_id: str) -> Dict[str, Any]:
        """删除 Provider。

        如果删掉的是当前活跃 Provider，还会顺带清理 `active_ai_provider` 指针，避免悬空引用。
        """
        try:
            if not self._db.get_by_id('ai_providers', provider_id):
                return {'success': False, 'error': 'Provider 不存在'}

            success = self._db.delete('ai_providers', 'id = ?', (provider_id,))
            if not success:
                return {'success': False, 'error': '删除失败'}

            active = self._db.get_active_config('active_ai_provider')
            if active == provider_id:
                self._db.delete('active_config', 'key = ?', ('active_ai_provider',))

            self._load_config()
            return {'success': True}

        except Exception as e:
            logger.error(f"删除 Provider 失败: {e}")
            return {'success': False, 'error': str(e)}

    def _update_stats(self, provider_id: str, success: bool, latency: float):
        """更新 Provider 调用统计。

        为减少数据库写频率，当前采用“内存累计 + 每 5 次请求落库一次”的策略。
        """
        if provider_id not in self._stats_cache:
            self._stats_cache[provider_id] = {
                'total_requests': 0,
                'failed_requests': 0,
                'total_latency': 0,
                'avg_latency': 0
            }

        stats = self._stats_cache[provider_id]
        stats['total_requests'] += 1

        if not success:
            stats['failed_requests'] += 1

        stats['total_latency'] += latency
        stats['avg_latency'] = round(stats['total_latency'] / stats['total_requests'], 2)

        if stats['total_requests'] % 5 == 0:
            self._save_stats(provider_id, stats)

    def _save_stats(self, provider_id: str, stats: Dict[str, Any]):
        """把 Provider 统计写回数据库。"""
        try:
            self._db.update('ai_providers', {'stats': stats}, 'id = ?', (provider_id,))
        except Exception as e:
            logger.error(f"保存统计失败: {e}")

    # ========== 聊天会话管理 ==========

    def create_session(self, title: str = "", provider_id: str = "", system_prompt: str = "") -> Dict[str, Any]:
        """创建新的聊天会话。

        会话本身只记录元数据；真正的对话内容在 `chat_messages` 表中单独管理。
        """
        session_id = str(uuid.uuid4())
        self._db.insert('chat_sessions', {
            'id': session_id,
            'title': title or "新对话",
            'provider_id': provider_id or self._active_provider_id or "",
            'system_prompt': system_prompt,
            'message_count': 0,
            'pinned': 0,
            'archived': 0
        })
        return {'id': session_id, 'title': title or "新对话"}

    def get_sessions(self, archived: bool = False) -> List[Dict[str, Any]]:
        """获取聊天会话列表，按最近消息时间倒序返回。"""
        return self._db.get_all(
            'chat_sessions',
            where="archived = ?",
            params=(1 if archived else 0,),
            order_by="last_message_at DESC"
        )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话元数据。"""
        return self._db.get_by_id('chat_sessions', session_id)

    def update_session(self, session_id: str, **kwargs) -> bool:
        """更新会话元数据，如标题、置顶、归档状态等。"""
        return self._db.update('chat_sessions', kwargs, 'id = ?', (session_id,))

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其全部消息。"""
        self._db.delete('chat_messages', 'session_id = ?', (session_id,))
        return self._db.delete('chat_sessions', 'id = ?', (session_id,))

    def add_message(self, session_id: str, role: str, content: str, provider_id: str = "") -> Dict[str, Any]:
        """添加消息到会话，并同步更新会话的消息计数与最近活跃时间。

        这是聊天历史持久化的关键写入口；若消息顺序错乱或列表不刷新，优先看这里。
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError("会话不存在")

        message_id = str(uuid.uuid4())
        sequence = session.get('message_count', 0) + 1

        self._db.insert('chat_messages', {
            'id': message_id,
            'session_id': session_id,
            'role': role,
            'content': content,
            'sequence': sequence,
            'provider_id': provider_id
        })

        from datetime import datetime
        self._db.update('chat_sessions', {
            'message_count': sequence,
            'last_message_at': datetime.now().isoformat()
        }, 'id = ?', (session_id,))

        return {'id': message_id, 'sequence': sequence}

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的全部消息，按 sequence 正序返回。"""
        return self._db.get_all('chat_messages', where='session_id = ?', params=(session_id,), order_by='sequence ASC')

    def clear_messages(self, session_id: str) -> bool:
        """清空会话消息，并把会话计数重置为 0。"""
        self._db.delete('chat_messages', 'session_id = ?', (session_id,))
        return self._db.update('chat_sessions', {'message_count': 0, 'last_message_at': None}, 'id = ?', (session_id,))
