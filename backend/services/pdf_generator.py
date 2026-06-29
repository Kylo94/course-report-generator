"""PDF 生成服务：HTML → PDF。

使用 WeasyPrint 渲染 HTML 为 A4 PDF。
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

from backend.utils.logger import get_logger

log = get_logger(__name__)

# macOS：预加载 Homebrew 安装的 glib/Pango/Cairo 系统库
if platform.system() == "Darwin":
    _brew_lib = "/opt/homebrew/lib"
    if os.path.isdir(_brew_lib):
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", _brew_lib)
        try:
            import ctypes
            for _lib in ("libgobject-2.0.0.dylib", "libpango-1.0.0.dylib", "libcairo.2.dylib",
                         "libpangocairo-1.0.0.dylib", "libgdk_pixbuf-2.0.0.dylib"):
                _p = os.path.join(_brew_lib, _lib)
                if os.path.isfile(_p):
                    ctypes.cdll.LoadLibrary(_p)
        except Exception as _e:
            log.warning("预加载 Homebrew 图形库失败: %s（PDF 导出可能不可用）", _e)


class PDFGenerationError(Exception):
    """PDF 生成失败。"""

    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)


class PDFGenerator:
    """PDF 生成器。

    将 HTML 字符串通过 WeasyPrint 转换为 PDF 文件或 bytes。
    """

    def generate_bytes(self, html: str) -> bytes:
        """渲染 HTML → PDF bytes。"""
        try:
            from weasyprint import HTML as WeasyHTML
            doc = WeasyHTML(string=html)
            return doc.write_pdf()
        except ImportError:
            raise PDFGenerationError(
                "WeasyPrint 未安装，请运行: brew install pango glib gdk-pixbuf && uv add weasyprint"
            )
        except Exception as e:
            raise PDFGenerationError(f"WeasyPrint 渲染失败: {e}", original=e)

    def generate(self, html: str, output_path: str | Path) -> str:
        """渲染 HTML → 写入 PDF 文件。返回输出路径。"""
        pdf_bytes = self.generate_bytes(html)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        log.info("PDF 已生成: %s (%d bytes)", path, len(pdf_bytes))
        return str(path.resolve())
