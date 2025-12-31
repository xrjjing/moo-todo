# -*- coding: utf-8 -*-
"""
AI Manager 统一管理器
负责 Provider 管理、聊天会话、模型获取
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
    """统一的 AI 管理器"""

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._providers = {}
        self._active_provider_id = None
        self._stats_cache = {}
        self._load_config()

    def _load_config(self):
        """从数据库加载 AI 提供商"""
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
        """获取指定或当前活跃的 Provider"""
        pid = provider_id or self._active_provider_id

        if not pid:
            raise ValueError("未配置活跃的 AI Provider")

        if pid not in self._providers:
            raise ValueError(f"Provider {pid} 不存在或未启用")

        return self._providers[pid]

    async def chat(self, prompt: str, system_prompt: Optional[str] = None,
                   provider_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """统一的对话接口"""
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
        """带历史记录的对话接口"""
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
        """切换活跃的 Provider"""
        if provider_id not in self._providers:
            raise ValueError(f"Provider {provider_id} 不存在或未启用")

        old_provider_id = self._active_provider_id
        self._active_provider_id = provider_id

        if not self._db.set_active_config('active_ai_provider', provider_id):
            self._active_provider_id = old_provider_id
            raise RuntimeError("保存活跃 Provider 失败")

        logger.info(f"切换到 Provider: {provider_id}")

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """获取可用的 Provider 列表"""
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
        """动态获取可用模型列表"""
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
        """从 OpenAI API 获取模型列表"""
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
        """返回 OpenAI 固定的模型列表"""
        return [
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'description': '最新多模态模型'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'description': '高性能模型'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'description': '快速响应模型'}
        ]

    async def _fetch_claude_models(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Claude API 获取模型列表"""
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
        """返回 Claude 固定的模型列表"""
        return [
            {'id': 'claude-3-5-sonnet-20241022', 'name': 'Claude 3.5 Sonnet', 'description': '平衡性能与速度'},
            {'id': 'claude-3-opus-20240229', 'name': 'Claude 3 Opus', 'description': '最强推理能力'},
            {'id': 'claude-3-haiku-20240307', 'name': 'Claude 3 Haiku', 'description': '最快响应速度'}
        ]

    async def test_connection(self, temp_config: Dict[str, Any]) -> Dict[str, Any]:
        """测试 Provider 连接"""
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
        """保存 Provider 配置"""
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
        """删除 Provider"""
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
        """更新统计信息"""
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
        """保存统计到数据库"""
        try:
            self._db.update('ai_providers', {'stats': stats}, 'id = ?', (provider_id,))
        except Exception as e:
            logger.error(f"保存统计失败: {e}")

    # ========== 聊天会话管理 ==========

    def create_session(self, title: str = "", provider_id: str = "", system_prompt: str = "") -> Dict[str, Any]:
        """创建新的聊天会话"""
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
        """获取聊天会话列表"""
        return self._db.get_all(
            'chat_sessions',
            where="archived = ?",
            params=(1 if archived else 0,),
            order_by="last_message_at DESC"
        )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话"""
        return self._db.get_by_id('chat_sessions', session_id)

    def update_session(self, session_id: str, **kwargs) -> bool:
        """更新会话"""
        return self._db.update('chat_sessions', kwargs, 'id = ?', (session_id,))

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        self._db.delete('chat_messages', 'session_id = ?', (session_id,))
        return self._db.delete('chat_sessions', 'id = ?', (session_id,))

    def add_message(self, session_id: str, role: str, content: str, provider_id: str = "") -> Dict[str, Any]:
        """添加消息到会话"""
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
        """获取会话的所有消息"""
        return self._db.get_all('chat_messages', where='session_id = ?', params=(session_id,), order_by='sequence ASC')

    def clear_messages(self, session_id: str) -> bool:
        """清空会话消息"""
        self._db.delete('chat_messages', 'session_id = ?', (session_id,))
        return self._db.update('chat_sessions', {'message_count': 0, 'last_message_at': None}, 'id = ?', (session_id,))
