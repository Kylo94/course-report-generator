"""报告渲染服务：CourseRecord → HTML 字符串。

使用 Jinja2 渲染模板，内联 CSS，处理 Logo 和截图路径。"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from backend.config import PROJECT_ROOT, get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)

TEMPLATES_DIR = PROJECT_ROOT / "templates"
CUSTOM_TEMPLATES_DIR = PROJECT_ROOT / "data" / "custom_templates"
# 所有模板共享的 A4 分页 / 图片等比缩放 / 长文本密度样式
BASE_CSS_PATH = TEMPLATES_DIR / "_base.css"
_CPP_EXTS = {".cpp", ".cc", ".cxx", ".c++", ".c", ".h", ".hpp", ".hh", ".hxx"}


class TemplateNotFoundError(Exception):
    """模板不存在。"""

    def __init__(self, template_id: str):
        self.template_id = template_id
        super().__init__(f"模板不存在: {template_id}")


def _load_json(value: str | None, default: Any = None) -> Any:
    """安全解析 JSON 字符串（也兼容已经是 list/dict 的值）。"""
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _url_to_fs_path(url_path: str) -> str | None:
    """将 HTTP 访问路径（如 /api/assets/screenshots/abc.jpg）转为绝对文件路径。"""
    settings = get_settings()
    if url_path.startswith("/api/assets/screenshots/"):
        filename = url_path[len("/api/assets/screenshots/"):]
        full = Path(settings.report.screenshot_dir) / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/showcase/"):
        # PR3: 学生展示图目录
        filename = url_path[len("/api/assets/showcase/"):]
        full = Path(settings.report.screenshot_dir).parent / "showcase" / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/"):
        # 通用 assets 路径：/api/assets/bg2.png → data/assets/bg2.png
        # 优先 data/assets/（用户上传），回退 static/assets/（内置默认）
        from backend.config import PROJECT_ROOT
        filename = url_path[len("/api/assets/"):]
        full = Path(settings.report.asset_dir) / filename
        if full.exists():
            return str(full.resolve())
        static_full = PROJECT_ROOT / "static" / "assets" / filename
        if static_full.exists():
            return str(static_full.resolve())
    return None


def _image_to_data_uri(image_path: str) -> str | None:
    """将图片文件转为 base64 data URI。"""
    try:
        p = Path(image_path)
        if not p.exists():
            return None
        ext = p.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "image/png")
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        log.warning("图片转 data URI 失败: %s", e)
        return None


def _text_chars(values) -> int:
    """统计一组文本值的字符数（忽略 None）。"""
    total = 0
    for value in values:
        if isinstance(value, str):
            total += len(value)
    return total


def _density_class(score: int, compact: int, ultra: int) -> str:
    """根据内容体量返回密度档位 class。"""
    if score >= ultra:
        return "density-ultra"
    if score >= compact:
        return "density-compact"
    return ""


def _compute_density(
    knowledge_points: list,
    content_items: list,
    code_excerpt: str,
    vocabulary: dict,
    homework: dict,
    evaluation: str,
    ability_improvement: str,
    has_code_images: bool = False,
) -> dict[str, str]:
    """估算每页内容量，供模板切换字号/行距，避免文字撑出 A4。

    只做启发式估算：正常内容保持原设计；文字明显偏多时逐级压缩。
    """
    kp_chars = _text_chars(knowledge_points)
    kp_score = kp_chars + len(knowledge_points) * 4
    if len(knowledge_points) >= 12:
        p1 = "density-ultra"
    elif len(knowledge_points) >= 8:
        p1 = "density-compact"
    else:
        p1 = _density_class(kp_score, 100, 180)

    content_chars = sum(
        _text_chars([item.get("kp", ""), item.get("text", "")])
        for item in content_items
        if isinstance(item, dict)
    )
    p2 = _density_class(content_chars + len(content_items) * 12, 1000, 1450)

    vocabulary = vocabulary if isinstance(vocabulary, dict) else {}
    homework = homework if isinstance(homework, dict) else {}
    vocab_chars = _text_chars(
        [vocabulary.get(k, "") for k in ("word", "phonetic", "meaning", "example")]
    )
    p3_score = len(code_excerpt) + vocab_chars + len(ability_improvement or "")
    if not has_code_images and code_excerpt:
        p3_score += 120
    p3 = _density_class(p3_score, 900, 1300)

    questions = homework.get("questions")
    questions = questions if isinstance(questions, list) else []
    hw_chars = _text_chars([homework.get("goal", ""), homework.get("hint", "")])
    for q in questions:
        if isinstance(q, dict):
            hw_chars += _text_chars([q.get("goal", ""), q.get("hint", "")])
            hints = q.get("hints")
            if isinstance(hints, list):
                hw_chars += _text_chars(hints)
    p4_score = hw_chars + len(evaluation or "") + len(questions) * 60
    if len(questions) >= 5:
        p4 = "density-ultra"
    elif len(questions) >= 3:
        p4 = "density-compact"
    else:
        p4 = _density_class(p4_score, 800, 1200)

    return {"p1": p1, "p2": p2, "p3": p3, "p4": p4}


def list_templates() -> list[dict[str, Any]]:
    """扫描 templates/ 和 data/custom_templates/ 目录，返回所有模板列表。"""
    templates: list[dict[str, Any]] = []

    # 扫描内置模板目录
    if TEMPLATES_DIR.exists():
        for entry in sorted(TEMPLATES_DIR.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            config_path = entry / "config.json"
            if not config_path.exists():
                continue
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                templates.append({
                    "id": config.get("id", entry.name),
                    "name": config.get("name", entry.name),
                    "version": config.get("version", "1.0"),
                    "is_builtin": config.get("is_builtin", True),
                    "parent_template": config.get("parent_template"),
                    "thumbnail": config.get("thumbnail", ""),
                    "description": config.get("description", ""),
                    "page_size": config.get("page_size", "A4"),
                })
            except Exception as e:
                log.warning("模板配置加载失败 %s: %s", entry.name, e)

    # 扫描自定义模板目录
    if CUSTOM_TEMPLATES_DIR.exists():
        for entry in sorted(CUSTOM_TEMPLATES_DIR.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            config_path = entry / "config.json"
            if not config_path.exists():
                continue
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                # 自定义模板的 id 可能冲突，加 is_builtin=false
                config.setdefault("is_builtin", False)
                templates.append({
                    "id": config.get("id", entry.name),
                    "name": config.get("name", entry.name),
                    "version": config.get("version", "1.0"),
                    "is_builtin": config.get("is_builtin", False),
                    "parent_template": config.get("parent_template"),
                    "thumbnail": config.get("thumbnail", ""),
                    "description": config.get("description", ""),
                    "page_size": config.get("page_size", "A4"),
                })
            except Exception as e:
                log.warning("自定义模板加载失败 %s: %s", entry.name, e)

    return templates


def _find_template_dir(template_id: str) -> Path | None:
    """在 TEMPLATES_DIR 和 CUSTOM_TEMPLATES_DIR 中查找模板目录。"""
    for base_dir in (TEMPLATES_DIR, CUSTOM_TEMPLATES_DIR):
        d = base_dir / template_id
        if d.exists() and (d / "config.json").exists():
            return d
    return None


def get_template_config(template_id: str) -> dict[str, Any]:
    """加载单个模板配置。"""
    template_dir = _find_template_dir(template_id)
    if template_dir is None:
        raise TemplateNotFoundError(template_id)
    config_path = template_dir / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise TemplateNotFoundError(template_id) from e


class ReportRenderer:
    """报告渲染器。

    加载指定模板的 HTML + CSS，传入 CourseRecord 数据，
    返回完整 HTML 字符串（内联 CSS）。
    """

    def __init__(self, template_id: str = "classic"):
        self.template_id = template_id
        tpl_dir = _find_template_dir(template_id)
        if tpl_dir is None:
            raise TemplateNotFoundError(template_id)
        self.template_dir = tpl_dir

        # 加载模板文件
        self.html_template = self._load_file("template.html")
        # 共享布局样式前置，模板自身样式可以继续覆盖外观
        base_css = ""
        if BASE_CSS_PATH.exists():
            base_css = BASE_CSS_PATH.read_text("utf-8")
        self.css_content = f"{base_css}\n\n{self._load_file('style.css')}"

        # 加载配置
        self.config = get_template_config(template_id)

    def _load_file(self, filename: str) -> str:
        path = self.template_dir / filename
        if not path.exists():
            log.warning("模板文件缺失: %s", path)
            return ""
        return path.read_text("utf-8")

    def render(
        self,
        record,
        student_name: str = "",
        layout_config: dict | None = None,
        run_screenshots: list[str] | None = None,
        code_screenshots: list[str] | None = None,
        homework_screenshots: list[str] | None = None,
        showcase_photo: str | None = None,
    ) -> str:
        """渲染完整报告 HTML。

        run_screenshots: 运行效果/项目截图 URL 列表，模板中在运行效果区域展示图片。
        code_screenshots: 代码截图 URL 列表，模板中优先显示图片而非 code_excerpt 文本。
        homework_screenshots: 作业截图 URL 列表，模板中在作业区域展示图片。
        showcase_photo: PR3 每学生独有的展示图 URL（/api/assets/showcase/xxx.jpg），
                        模板中在"学生作品展示"区域展示。None/空字符串则不展示。
        """

        # 合并布局覆盖与主题
        merged = merge_layout_with_theme(self.config, layout_config)

        # 解析背景图 URL → data URI（保证 PDF 和预览都能正常显示）
        bg = merged.get("background_image")
        if bg and bg.startswith("/api/assets/"):
            fs_path = _url_to_fs_path(bg)
            if fs_path:
                data_uri = _image_to_data_uri(fs_path)
                if data_uri:
                    merged["background_image"] = data_uri

        # 提前读取 Logo 配置（在 custom_style 中需要 margin 值生成 CSS 变量）
        logo_cfg = _load_json(record.logo_config, {})
        _logo_margin = logo_cfg.get("margin")  # 不依赖 enabled 状态，CSS 变量在无 Logo 时无害

        custom_style = self._build_custom_style(merged, _logo_margin)

        # 反序列化 JSON 字段
        kp = _load_json(record.knowledge_points, [])
        content_items = _load_json(record.content_items, [])
        vocabulary = _load_json(record.vocabulary, {})
        homework = _load_json(record.homework, {})
        screenshots = _load_json(record.screenshot_paths, [])

        # 处理 Logo
        logo_data: dict[str, Any] | None = None
        if logo_cfg.get("enabled", True):  # 默认启用（有文件就显示）
            # 优先使用模板内嵌的 logo，再回退到全局 Logo 文件
            logo_data_uri = self.config.get("logo_data_uri")
            # 如果配置中是 URL（如 /api/assets/logo.png），转为 data URI
            if logo_data_uri and not logo_data_uri.startswith("data:"):
                fs_path = _url_to_fs_path(logo_data_uri)
                if fs_path:
                    logo_data_uri = _image_to_data_uri(fs_path)
            if not logo_data_uri or logo_data_uri.startswith("/api/"):
                # 回退到从磁盘读取全局 Logo 文件
                settings = get_settings()
                asset_dir = Path(settings.report.asset_dir)
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    logo_path = asset_dir / f"logo{ext}"
                    if logo_path.exists():
                        logo_data_uri = _image_to_data_uri(str(logo_path))
                        break
            if logo_data_uri:
                _size_val = logo_cfg.get("size", 30)
                if isinstance(_size_val, str):
                    _size_map = {"small": 20, "medium": 30, "large": 45}
                    _size_val = _size_map.get(_size_val, 30)
                logo_data = {
                    "data_uri": logo_data_uri,
                    "position": logo_cfg.get("position", "top-right"),
                    "width_mm": _size_val,
                    "show_on_all_pages": logo_cfg.get("show_on_all_pages", True),
                }

        # 处理所有截图路径：URL → 文件路径
        resolved_screenshots: list[str] = []
        log.info("渲染器: screenshot_paths 类型=%s 值(前200)=%s", type(screenshots).__name__, str(screenshots)[:200])
        for s in screenshots:  # 处理所有截图
            if not isinstance(s, str):
                log.warning("渲染器: 截图路径非字符串: %s", type(s).__name__)
                continue
            fs_path = _url_to_fs_path(s)
            log.info("渲染器: 解析截图 URL=%s → fs_path=%s", s, fs_path)
            if fs_path:
                data_uri = _image_to_data_uri(fs_path)
                resolved_screenshots.append(data_uri or fs_path)
            else:
                log.warning("渲染器: 截图路径无法解析为文件路径: %s", s)
        log.info("渲染器: 截图解析完成 %d 条 → %d 条", len(screenshots), len(resolved_screenshots))

        # 提取代码片段：优先使用 AI 分析结果中的 line range 精确截取，最多 15 行
        code_excerpt = ""
        if record.project_meta and record.project_folder:
            try:
                import ast as _ast
                import re as _re

                pm = _load_json(record.project_meta)
                folder = Path(pm.get("folder", record.project_folder)) if pm else Path(record.project_folder)

                # 1. 从 ai_meta 读取代码分析结果（含精确行号）
                ai_meta = _load_json(record.ai_meta, {}) if record.ai_meta else {}
                key_funcs = ai_meta.get("key_functions", [])

                # 2. 从 content_items 中提取被引用的函数名
                referenced_funcs: set[str] = set()
                for item in content_items:
                    for match in _re.finditer(r'`([a-zA-Z_]\w*)\(\)', item.get("text", "")):
                        referenced_funcs.add(match.group(1))

                # 3. 收集待提取的代码块（函数名 → {file_path, start, end, name}）
                code_blocks: list[dict] = []

                # 优先用分析结果中的 line range
                if referenced_funcs:
                    for func_name in referenced_funcs:
                        matched = [f for f in key_funcs
                                   if f.get("name", "").strip("()") == func_name]
                        for m in matched:
                            fp = m.get("file_path", "")
                            sl = m.get("start_line")
                            el = m.get("end_line")
                            if fp and sl and el:
                                code_blocks.append({
                                    "file": fp,
                                    "start": sl - 1,  # 转 0-index
                                    "end": el,
                                    "name": m["name"],
                                })
                else:
                    # 没有引用时取前 2 个关键函数
                    for m in key_funcs[:2]:
                        fp = m.get("file_path", "")
                        sl = m.get("start_line")
                        el = m.get("end_line")
                        if fp and sl and el:
                            code_blocks.append({
                                "file": fp,
                                "start": sl - 1,
                                "end": el,
                                "name": m["name"],
                            })

                # 4. 从源码文件中读取代码
                def _read_func_block(block: dict) -> str:
                    fpath = folder / block["file"]
                    if not fpath.exists():
                        return ""
                    try:
                        lines = fpath.read_text("utf-8").splitlines()
                        selected = lines[block["start"]:block["end"]]
                        marker = "//" if fpath.suffix.lower() in _CPP_EXTS else "#"
                        header = f"{marker} {block['file']}:{block['start'] + 1}"
                        return header + "\n" + "\n".join(selected)
                    except (OSError, IndexError):
                        return ""

                raw_blocks = [_read_func_block(b) for b in code_blocks if b]
                raw_blocks = [b for b in raw_blocks if b]

                # 5. 无 line range 时降级到 AST 解析
                if not raw_blocks:
                    entry_path = folder / pm.get("entry_file", "") if pm and pm.get("entry_file") else None
                    if not entry_path and pm and "py_files" in pm and pm["py_files"]:
                        entry_path = folder / pm["py_files"][0]["path"]
                    if entry_path and entry_path.exists():
                        source = entry_path.read_text("utf-8")
                        source_lines = source.splitlines()
                        if entry_path.suffix.lower() in _CPP_EXTS:
                            # C/C++：优先从 main() 所在行开始截取
                            start = 0
                            for idx, line in enumerate(source_lines):
                                if _re.search(r"\bmain\s*\(", line):
                                    start = idx
                                    break
                            raw_blocks.append(
                                f"// {entry_path.name}:{start + 1}\n"
                                + "\n".join(source_lines[start:start + 15])
                            )
                        else:
                            try:
                                tree = _ast.parse(source)
                                for node in _ast.walk(tree):
                                    if not isinstance(node, _ast.FunctionDef):
                                        continue
                                    if referenced_funcs and node.name not in referenced_funcs:
                                        continue
                                    start = node.lineno - 1
                                    end = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start + 5
                                    raw_blocks.append(f"# {entry_path.name}:{node.lineno}\n" + "\n".join(source_lines[start:end]))
                                    if len("\n\n".join(raw_blocks)) > 800:
                                        break
                            except SyntaxError:
                                body = [l for l in source_lines if l.strip() and not l.strip().startswith(("import ", "from ", "#"))]
                                raw_blocks = [line for line in body[:15]]

                # 6. 限制总行数 ≤ 15
                if raw_blocks:
                    combined = "\n\n".join(raw_blocks)
                    lines = combined.splitlines()
                    code_excerpt = "\n".join(lines[:15])
            except Exception as e:
                log.warning("提取代码片段失败: %s", e)

        # 处理代码截图：URL → data URI（模板优先显示图片）
        resolved_code_screenshots: list[str] = []
        if code_screenshots:
            for s in code_screenshots:
                if not isinstance(s, str):
                    continue
                fs_path = _url_to_fs_path(s)
                if fs_path:
                    data_uri = _image_to_data_uri(fs_path)
                    resolved_code_screenshots.append(data_uri or fs_path)
                else:
                    resolved_code_screenshots.append(s)

        # 处理作业截图：URL → data URI
        resolved_homework_screenshots: list[str] = []
        if homework_screenshots:
            for s in homework_screenshots:
                if not isinstance(s, str):
                    continue
                fs_path = _url_to_fs_path(s)
                if fs_path:
                    data_uri = _image_to_data_uri(fs_path)
                    resolved_homework_screenshots.append(data_uri or fs_path)
                else:
                    resolved_homework_screenshots.append(s)

        # 处理运行效果/项目截图：URL → data URI
        resolved_run_screenshots: list[str] = []
        if run_screenshots:
            for s in run_screenshots:
                if not isinstance(s, str):
                    continue
                fs_path = _url_to_fs_path(s)
                if fs_path:
                    data_uri = _image_to_data_uri(fs_path)
                    resolved_run_screenshots.append(data_uri or fs_path)
                else:
                    resolved_run_screenshots.append(s)

        # PR3: 展示图（单张）URL → data URI
        resolved_showcase_photo: str | None = None
        if showcase_photo and isinstance(showcase_photo, str):
            fs_path = _url_to_fs_path(showcase_photo)
            if fs_path:
                data_uri = _image_to_data_uri(fs_path)
                resolved_showcase_photo = data_uri or fs_path
            else:
                resolved_showcase_photo = showcase_photo

        # 首页「项目运行效果」统一图片区：学生展示图 + 运行截图 + 其他截图。
        # 展示图不再单独占一个区块，避免破坏首页版式。
        effect_images: list[str] = []
        for image in ([resolved_showcase_photo] if resolved_showcase_photo else []) + \
                resolved_run_screenshots + resolved_screenshots:
            if image and image not in effect_images:
                effect_images.append(image)
        # 固定网格最多容纳 4 张（2x2），超出的不展示，保证页面不溢出
        effect_images = effect_images[:4]

        density = _compute_density(
            knowledge_points=kp,
            content_items=content_items,
            code_excerpt=code_excerpt,
            vocabulary=vocabulary or {},
            homework=homework or {},
            evaluation=record.evaluation or "",
            ability_improvement=record.ability_improvement or "",
            has_code_images=bool(resolved_code_screenshots),
        )

        # 模板上下文
        ctx = {
            "css_content": self.css_content,
            "custom_style": custom_style,
            "course_topic": record.course_topic or "",
            "student_name": student_name,
            "course_date": record.course_date or "",
            "knowledge_points": kp,
            "ability_improvement": record.ability_improvement or "",
            "content_items": content_items,
            "vocabulary": vocabulary or {},
            "homework": homework or {},
            "evaluation": record.evaluation or "",
            "screenshots": resolved_screenshots,
            "logo": logo_data,
            "code_excerpt": code_excerpt,
            "run_screenshots": resolved_run_screenshots,
            "code_screenshots": resolved_code_screenshots,
            "homework_screenshots": resolved_homework_screenshots,
            # PR3: 学生独有展示图（保留给自定义模板；内置模板已合并进 effect_images）
            "showcase_photo": resolved_showcase_photo,
            # 首页项目运行效果图片（含展示图），固定网格展示
            "effect_images": effect_images,
            # 每页文字密度档位（"" / density-compact / density-ultra）
            "density": density,
        }

        # 使用 Jinja2 渲染
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=True,
        )
        template = env.from_string(self.html_template)
        html = template.render(ctx)

        # 文字过多时自动缩小正文区域，确保内容始终留在 A4 页面内。
        # PDF（Playwright/Chromium）与浏览器预览都会执行这段脚本。
        if "</body>" in html:
            html = html.replace("</body>", _FIT_SCRIPT + "\n</body>", 1)
        else:
            html += _FIT_SCRIPT

        return html

    @staticmethod
    def _build_custom_style(merged: dict, logo_margin_mm: int | None = None) -> str:
        """从合并后的布局配置生成 CSS 变量覆盖块。

        logo_margin_mm: Logo 内边距（mm），控制 Logo 距离页面边缘的距离。
        """
        lines = [":root {"]
        lines.append(f"  --primary: {merged['primary_color']};")
        lines.append(f"  --secondary: {merged['secondary_color']};")
        lines.append(f"  --bg-color: {merged['background_color']};")
        lines.append(f"  --font-title: \"{merged['font_title']}\", \"PingFang SC\", sans-serif;")
        lines.append(f"  --font-body: \"{merged['font_body']}\", \"SimSun\", serif;")
        lines.append(f"  --fs-title: {merged['font_size_title']}pt;")
        lines.append(f"  --fs-body: {merged['font_size_body']}pt;")
        lines.append(f"  --page-margin-top: {merged['page_margin_top']}mm;")
        lines.append(f"  --page-margin-right: {merged['page_margin_right']}mm;")
        lines.append(f"  --page-margin-bottom: {merged['page_margin_bottom']}mm;")
        lines.append(f"  --page-margin-left: {merged['page_margin_left']}mm;")
        if logo_margin_mm is not None:
            lines.append(f"  --logo-offset-top: {logo_margin_mm}mm;")
            lines.append(f"  --logo-offset-right: {logo_margin_mm}mm;")
            lines.append(f"  --logo-offset-bottom: {logo_margin_mm}mm;")
            lines.append(f"  --logo-offset-left: {logo_margin_mm}mm;")
        lines.append("}")

        # 页面尺寸和内边距（A4 固定盒模型，内容不会溢出到下一页）
        lines.append(".page {")
        lines.append("  width: 210mm;")
        lines.append("  height: 296mm;")
        lines.append("  min-height: 0;")
        lines.append("  box-sizing: border-box;")
        lines.append("  overflow: hidden;")
        lines.append("  display: flex;")
        lines.append("  flex-direction: column;")
        lines.append("  padding:")
        lines.append(f"    var(--page-margin-top, 20mm)")
        lines.append(f"    var(--page-margin-right, 18mm)")
        lines.append(f"    var(--page-margin-bottom, 18mm)")
        lines.append(f"    var(--page-margin-left, 18mm);")
        lines.append("}")

        if merged.get("background_image"):
            lines.append(".page, .page-content {")
            lines.append(f"  background-image: url('{merged['background_image']}');")
            lines.append("  background-size: 100% 100%;")
            lines.append("  background-position: center;")
            lines.append("  background-repeat: no-repeat;")
            lines.append("}")

        return "\n".join(lines)


def merge_layout_with_theme(
    template_config: dict,
    layout_config: dict | None,
) -> dict:
    """将按报告布局覆盖与模板主题默认值合并。"""
    theme = (template_config or {}).get("theme", {})
    result = {
        "primary_color": theme.get("primary_color", "#3B7DDD"),
        "secondary_color": theme.get("secondary_color", "#F5F5F5"),
        "font_title": theme.get("font_title", "Heiti SC"),
        "font_body": theme.get("font_body", "STSong"),
        "font_size_title": theme.get("font_size_title", 24),
        "font_size_body": theme.get("font_size_body", 11),
        "background_color": theme.get("background_color", "#FFFFFF"),
        "background_image": theme.get("background_image"),
        "page_margin_top": theme.get("page_margin_top", 20),
        "page_margin_bottom": theme.get("page_margin_bottom", 18),
        "page_margin_left": theme.get("page_margin_left", 18),
        "page_margin_right": theme.get("page_margin_right", 18),
    }
    if layout_config:
        for key in result:
            if key in layout_config and layout_config[key] is not None:
                result[key] = layout_config[key]
    return result


_FIT_SCRIPT = """\
<script>
(function () {
  var MIN_SCALE = 0.45;

  function reset(inner) {
    inner.style.transform = '';
    inner.style.transformOrigin = '';
    inner.style.width = '';
    inner.style.zoom = '';
  }

  function fit(parent) {
    if (!parent) return;
    var inner = parent.querySelector(':scope > .fit');
    if (!inner) return;

    reset(inner);
    var available = parent.clientHeight;
    var contentHeight = inner.scrollHeight;
    if (!available || contentHeight <= available + 1) return;

    // 用 transform 等比缩放，既能保留阅读顺序，也能让 Chrome 正常打印 PDF
    var scale = Math.max(MIN_SCALE, available / contentHeight);
    inner.style.transformOrigin = 'top left';
    inner.style.transform = 'scale(' + scale.toFixed(4) + ')';
    // 缩放后让内容仍然铺满正文宽度，避免右侧留白
    inner.style.width = (100 / scale).toFixed(4) + '%';
  }

  function run() {
    var pages = document.querySelectorAll('.page');
    for (var i = 0; i < pages.length; i++) {
      fit(pages[i].querySelector('.page1-kp'));
      fit(pages[i].querySelector('.page-body'));
    }
  }

  if (document.readyState === 'complete') {
    run();
  } else {
    window.addEventListener('load', run, { once: true });
  }
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(run);
  }
  window.addEventListener('beforeprint', run);
})();
</script>
"""


_A4_PREVIEW_CSS = """\
<style>
@media screen {
  body {
    background-color: #e8e8e8 !important;
    padding: 30px 0 !important;
  }
  .page {
    width: 210mm !important;
    height: 296mm !important;
    min-height: 0 !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
    margin: 28px auto !important;
    padding-top: var(--page-margin-top, 20mm) !important;
    padding-right: var(--page-margin-right, 18mm) !important;
    padding-bottom: var(--page-margin-bottom, 18mm) !important;
    padding-left: var(--page-margin-left, 18mm) !important;
    background-color: #fff !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.12) !important;
    page-break-after: always !important;
  }
  .page:last-of-type {
    margin-bottom: 30px !important;
    page-break-after: auto !important;
  }
}
@media print {
  .page {
    width: 210mm;
    height: 296mm;
    min-height: 0;
    box-sizing: border-box;
    overflow: hidden;
    padding-top: var(--page-margin-top, 20mm);
    padding-right: var(--page-margin-right, 18mm);
    padding-bottom: var(--page-margin-bottom, 18mm);
    padding-left: var(--page-margin-left, 18mm);
    page-break-after: always;
  }
  .page:last-of-type { page-break-after: auto; }
}
</style>
"""


def wrap_preview_html(html: str) -> str:
    """为预览 HTML 添加 A4 纸张模拟 CSS，使其在浏览器屏幕中呈现分页效果。"""
    return html.replace("</head>", _A4_PREVIEW_CSS + "</head>", 1)
