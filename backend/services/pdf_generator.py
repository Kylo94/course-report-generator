"""PDF 生成服务：HTML → PDF。

使用 WeasyPrint 渲染 HTML 为 A4 PDF。
"""
from __future__ import annotations

from pathlib import Path

from backend.utils.logger import get_logger

log = get_logger(__name__)


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
