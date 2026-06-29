"""PDF 生成器单元测试。"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.pdf_generator import PDFGenerationError, PDFGenerator


class TestPDFGenerator:
    """PDF 生成器测试。"""

    async def test_generate_bytes_returns_bytes(self) -> None:
        """generate_bytes 返回非空 bytes。"""
        gen = PDFGenerator()
        html = "<html><body><h1>测试 PDF</h1><p>中文内容</p></body></html>"
        pdf_bytes = await gen.generate_bytes(html)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        # PDF 文件头必须是 %
        assert pdf_bytes.startswith(b"%")

    async def test_generate_bytes_with_chinese(self) -> None:
        """包含中文的 HTML 可以生成 PDF。"""
        gen = PDFGenerator()
        html = """
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"></head>
        <body>
          <h1>课程报告</h1>
          <p>学生姓名：张三</p>
          <p>上课时间：2026-06-29</p>
          <p>评价：上课认真，逻辑清晰，能够独立完成课堂练习。</p>
        </body>
        </html>
        """
        pdf_bytes = await gen.generate_bytes(html)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 200

    async def test_generate_creates_file(self, tmp_path: Path) -> None:
        """generate 将 PDF 写入文件。"""
        gen = PDFGenerator()
        html = "<html><body><h1>测试</h1></body></html>"
        output = tmp_path / "test_output.pdf"
        result = await gen.generate(html, str(output))
        assert output.exists()
        assert output.stat().st_size > 100
        assert result == str(output.resolve())

    async def test_generate_creates_parent_dir(self, tmp_path: Path) -> None:
        """generate 自动创建父目录。"""
        gen = PDFGenerator()
        html = "<html><body><h1>测试</h1></body></html>"
        output = tmp_path / "subdir" / "report.pdf"
        result = await gen.generate(html, str(output))
        assert output.exists()
        assert output.stat().st_size > 100

    async def test_generate_with_special_chars(self) -> None:
        """HTML 含特殊字符不出错。"""
        gen = PDFGenerator()
        html = "<html><body><p>&lt;test&gt; &amp; 报告</p></body></html>"
        pdf_bytes = await gen.generate_bytes(html)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100

    async def test_generate_with_full_page_layout(self) -> None:
        """多内容分页 HTML 生成 PDF 不出错。"""
        gen = PDFGenerator()
        items = "".join(f'<div style="page-break-after:always"><h1>第{i}页</h1><p>内容{i}</p></div>' for i in range(4))
        html = f"<html><body>{items}</body></html>"
        pdf_bytes = await gen.generate_bytes(html)
        assert isinstance(pdf_bytes, bytes)
        # Playwright 生成的 4 页 PDF 通常 > 1KB
        assert len(pdf_bytes) > 500

    async def test_generate_bytes_empty_html(self) -> None:
        """空 HTML 生成空 PDF 不出错。"""
        gen = PDFGenerator()
        pdf_bytes = await gen.generate_bytes("<html></html>")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
