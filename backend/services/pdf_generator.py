"""PDF 生成服务：HTML → PDF。

使用 Playwright（Chromium 内核）渲染 HTML 为 A4 PDF。
渲染效果与浏览器一致，零系统依赖（无需 GTK/Pango/Cairo）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_MARGIN: dict[str, str] = {
    "top": "20mm",
    "right": "18mm",
    "bottom": "18mm",
    "left": "18mm",
}


class PDFGenerationError(Exception):
    """PDF 生成失败。"""

    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)


class PDFGenerator:
    """PDF 生成器。

    将 HTML 字符串通过 Chromium 内核转换为 PDF 文件或 bytes。
    """

    async def generate_bytes(self, html: str, margin: dict[str, Any] | None = None) -> bytes:
        """渲染 HTML → PDF bytes。

        margin: 边距字典如 {"top": "20mm", "right": "18mm", ...}，
                不传则使用默认值 (20/18/18/18 mm)。
        """
        if margin is None:
            margin = _DEFAULT_MARGIN
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                from backend.paths import get_chromium_path

                chromium_path = get_chromium_path()
                launch_kwargs = {}
                if chromium_path:
                    launch_kwargs["executable_path"] = chromium_path
                browser = await pw.chromium.launch(**launch_kwargs)
                try:
                    page = await browser.new_page()
                    await page.set_content(html, wait_until="networkidle")
                    pdf_bytes = await page.pdf(
                        format="A4",
                        print_background=True,
                        margin={
                            "top": str(margin["top"]),
                            "right": str(margin["right"]),
                            "bottom": str(margin["bottom"]),
                            "left": str(margin["left"]),
                        },
                    )
                    return pdf_bytes
                finally:
                    await browser.close()
        except ImportError:
            raise PDFGenerationError(
                "Playwright 未安装，请运行: uv add playwright && python -m playwright install chromium"
            )
        except Exception as e:
            raise PDFGenerationError(f"PDF 渲染失败: {e}", original=e)

    async def generate(
        self,
        html: str,
        output_path: str | Path,
        margin: dict[str, Any] | None = None,
    ) -> str:
        """渲染 HTML → 写入 PDF 文件。返回输出路径。"""
        pdf_bytes = await self.generate_bytes(html, margin=margin)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        log.info("PDF 已生成: %s (%d bytes)", path, len(pdf_bytes))
        return str(path.resolve())
