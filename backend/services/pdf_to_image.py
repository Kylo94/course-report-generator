"""
PDF → 长图转换服务

在 PDF 导出后自动将 PDF 转为 JPG 长图。
依赖：pdf2image + Pillow（已在 pyproject.toml 中）
系统依赖：poppler（macOS: brew install poppler, Ubuntu: apt-get install poppler-utils）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pdf2image import convert_from_path

from backend.utils.logger import get_logger

log = get_logger(__name__)


def pdf_to_long_image(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    dpi: int = 150,
    quality: int = 95,
) -> str | None:
    """将 PDF 转为 JPG 长图。

    单页 PDF 直接转为 JPG；
    多页 PDF 合并为一张竖直长图。

    Args:
        pdf_path: PDF 文件路径
        output_path: 输出 JPG 路径。None 时自动生成（同名 .jpg）
        dpi: 渲染 DPI（默认 150）
        quality: JPEG 质量（默认 95）

    Returns:
        生成的 JPG 文件路径，失败返回 None
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        log.warning("PDF 文件不存在: %s", pdf_path)
        return None

    if output_path is None:
        output_path = pdf_path.with_suffix(".jpg")

    output_path = Path(output_path)

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi)
    except Exception as e:
        log.warning("PDF 转图片失败: %s", e)
        return None

    if not images:
        log.warning("PDF 没有页面: %s", pdf_path)
        return None

    try:
        if len(images) == 1:
            # 单页 → 直接保存
            images[0].convert("RGB").save(str(output_path), "JPEG", quality=quality)
        else:
            # 多页 → 合并为竖直长图
            widths, heights = zip(*(img.size for img in images))
            total_width = max(widths)
            total_height = sum(heights)

            combined = Image.new("RGB", (total_width, total_height), "white")
            y_offset = 0
            for img in images:
                img_rgb = img.convert("RGB")
                combined.paste(img_rgb, (0, y_offset))
                y_offset += img_rgb.height

            combined.save(str(output_path), "JPEG", quality=quality)

        log.info("PDF 转长图成功: %s → %s", pdf_path.name, output_path.name)
        return str(output_path)
    except Exception as e:
        log.warning("PDF 转长图保存失败: %s", e)
        return None
