"""
全局 pytest 配置与共享 fixtures

约定：
- 单元测试：tests/unit/**，标记 @pytest.mark.unit，可独立运行
- 集成测试：tests/integration/**，标记 @pytest.mark.integration
- 共享 fixtures 放本文件，子目录可按需覆盖
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

# 把项目根加入 sys.path，确保 import 路径稳定
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =========================
# 日志 fixture
# =========================
@pytest.fixture(autouse=True)
def _setup_test_logging(caplog) -> Iterator[None]:
    """
    自动为每个测试启用 logging 捕获，level=DEBUG。
    失败时 pytest -s 可见完整日志。
    """
    import logging
    caplog.set_level(logging.DEBUG)
    yield


# =========================
# 临时目录 fixture
# =========================
@pytest.fixture
def tmp_dir() -> Iterator[Path]:
    """提供一个独立的临时目录，测试结束后自动清理。"""
    d = Path(tempfile.mkdtemp(prefix="crg_test_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def project_tmp_dir(tmp_dir: Path) -> Path:
    """提供一个模拟项目目录，内含 main.py 与示例代码。"""
    src = tmp_dir / "project"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text(
        '''# Course: 测试课程第一课
# 知识点示例
import random

# 初始化角色
bird_y = 200

# 模拟重力
gravity = 0.5

print("Game started")
''',
        encoding="utf-8",
    )
    return src


# =========================
# 环境变量 fixture
# =========================
@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理可能影响测试的全局环境变量。"""
    for key in list(os.environ.keys()):
        if key.startswith("CRG_") or key == "LOG_LEVEL":
            monkeypatch.delenv(key, raising=False)


# =========================
# 配置 fixture
# =========================
@pytest.fixture
def sample_llm_config() -> dict[str, Any]:
    """示例 LLM 配置（用于单元测试，不发起真实网络请求）。"""
    return {
        "provider": "deepseek",
        "api_key": "test-fake-key",
        "default_model": "deepseek-chat",
        "timeout": 30,
        "max_retries": 1,
    }


# =========================
# 测试数据库 fixture（异步 SQLAlchemy + 内存 SQLite）
# =========================
@pytest_asyncio.fixture
async def test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """
    为每个测试创建独立的内存 SQLite 数据库。

    使用 monkeypatch 覆盖 CRG_DATABASE__URL 环境变量，
    然后调用 get_settings() 重新加载。
    """
    # 1. 强制重置 settings 缓存
    from backend.config import reset_settings_cache
    reset_settings_cache()

    # 2. 设置测试用数据库 URL（内存 SQLite）
    test_url = "sqlite+aiosqlite:///:memory:"
    monkeypatch.setenv("CRG_DATABASE__URL", test_url)

    # 3. 重置 settings 缓存让 env 生效
    reset_settings_cache()

    # 4. 重置 engine 和 session factory
    from backend import db
    if db._engine is not None:
        try:
            await db._engine.dispose()
        except Exception:
            pass
    db._engine = None
    db._session_factory = None

    # 5. 初始化数据库表
    from backend.db import init_db
    await init_db()

    yield

    # 清理
    if db._engine is not None:
        try:
            await db._engine.dispose()
        except Exception:
            pass
    db._engine = None
    db._session_factory = None
    reset_settings_cache()


@pytest_asyncio.fixture
async def db_session(test_db) -> AsyncIterator[Any]:
    """提供一个测试用的 AsyncSession。"""
    from backend.db import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        yield session


# =========================
# FastAPI TestClient fixture
# =========================
@pytest_asyncio.fixture
async def api_client(test_db) -> AsyncIterator[Any]:
    """提供一个配置好的 FastAPI AsyncClient。"""
    from httpx import ASGITransport, AsyncClient

    from backend.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 触发 lifespan 启动
        async with app.router.lifespan_context(app):
            yield client


# =========================
# 标记 hook（自动添加 marker）
# =========================
def pytest_collection_modifyitems(config, items):
    """根据文件路径自动打 marker。"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
