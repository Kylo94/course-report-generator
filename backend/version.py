"""应用版本号唯一来源。

pyproject.toml（Hatchling 动态版本）、backend/config.py、build.py 和
build.spec 都从这里读取，避免多处手写版本号导致不一致。
"""

__version__ = "1.3.0"
