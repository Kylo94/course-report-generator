"""
代码分析服务

职责：
1. 扫描项目文件夹，识别 .py 文件与资源文件
2. 用 AST 解析每个 .py 文件的代码结构
3. 解析启动文件顶部注释（提取课程主题）
4. 提取依赖（imports）
5. 识别项目类型（pygame / turtle / tkinter / web / cli / 算法）

约定启动文件识别：
  - 优先：项目根目录的 main.py
  - 其次：项目根目录的首个 .py 文件
  - 最后：项目根目录下任何 .py 文件
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.utils.logger import get_logger

log = get_logger(__name__)


# =========================
# 课程注释解析模式
# =========================
# 支持的格式（已去除 # 前缀，因为 _extract_top_comment 已剥掉）：
#   Course: 飞翔的小鸟第一课
#   课程：飞翔的小鸟第一课
#   课程名：飞翔的小鸟第一课
#   主题：飞翔的小鸟第一课
COURSE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*#?\s*Course\s*[:：]\s*(.+?)\s*$", re.IGNORECASE),
    re.compile(r"^\s*#?\s*课程\s*[:：]\s*(.+?)\s*$"),
    re.compile(r"^\s*#?\s*课程名\s*[:：]\s*(.+?)\s*$"),
    re.compile(r"^\s*#?\s*主题\s*[:：]\s*(.+?)\s*$"),
]

# 作业引导识别模式（已去除 # 前缀，因为 _extract_top_comment 已剥掉）
HOMEWORK_GUIDANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*作业引导\s*[:：]\s*$"),
    re.compile(r"^\s*作业指导\s*[:：]\s*$"),
    re.compile(r"^\s*HomeworkGuidance\s*[:：]\s*$", re.IGNORECASE),
]

# 项目类型识别
PROJECT_TYPE_RULES: list[tuple[str, str]] = [
    # (import 关键字, 项目类型)
    ("pygame", "pygame"),
    ("turtle", "turtle"),
    ("tkinter", "tkinter"),
    ("pyqt", "pyqt"),
    ("pyside", "pyqt"),
    ("arcade", "arcade"),
    ("pgzero", "pgzero"),
    ("flask", "web"),
    ("fastapi", "web"),
    ("django", "web"),
    ("streamlit", "web"),
    ("gradio", "web"),
    ("requests", "web"),
]

GUI_TYPES = {"pygame", "turtle", "tkinter", "pyqt", "arcade", "pgzero"}
WEB_TYPES = {"web"}
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", "dist", "build", ".idea", ".vscode"}


# =========================
# 数据结构
# =========================
@dataclass
class FileInfo:
    """单个文件的信息。"""
    path: str  # 相对路径
    name: str
    is_python: bool
    size_bytes: int


@dataclass
class PyStructure:
    """单个 .py 文件的结构。"""
    path: str
    imports: list[str] = field(default_factory=list)
    from_imports: list[tuple[str, str | None]] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    top_comment: str | None = None  # 文件顶部注释
    course_title: str | None = None  # 解析出的课程主题
    homework_guidance: str | None = None  # 解析出的作业引导
    line_count: int = 0


@dataclass
class ProjectMeta:
    """项目元信息汇总。"""
    folder: str
    entry_file: str | None  # 启动文件相对路径
    project_type: str  # pygame / turtle / tkinter / web / cli / algorithm
    course_title: str | None  # 课程主题（来自启动文件注释）
    all_files: list[FileInfo] = field(default_factory=list)
    py_files: list[PyStructure] = field(default_factory=list)
    all_imports: list[str] = field(default_factory=list)
    total_lines: int = 0
    warnings: list[str] = field(default_factory=list)


# =========================
# 公共 API
# =========================
def analyze_project(folder: str | Path) -> ProjectMeta:
    """
    分析一个 Python 项目文件夹。

    步骤：
      1. 扫描所有文件
      2. 识别启动文件
      3. 解析每个 .py 文件
      4. 识别项目类型
      5. 提取课程主题
    """
    folder = Path(folder).resolve()

    if not folder.exists():
        raise FileNotFoundError(f"项目文件夹不存在: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"不是文件夹: {folder}")

    log.info("开始分析项目: %s", folder)

    # 1. 扫描所有文件
    files = _scan_files(folder)

    if not files:
        raise ValueError(f"项目文件夹为空: {folder}")

    py_files = [f for f in files if f.is_python]
    if not py_files:
        raise ValueError(f"未找到任何 .py 文件: {folder}")

    # 2. 识别启动文件
    entry_path = _find_entry_file(folder, py_files)
    log.info("启动文件: %s", entry_path)

    # 3. 解析每个 .py 文件
    structures: list[PyStructure] = []
    for f in py_files:
        abs_path = folder / f.path
        try:
            struct = _parse_py_file(abs_path)
            struct.path = f.path
            structures.append(struct)
        except SyntaxError as e:
            log.warning("解析 %s 失败: %s", f.path, e)
            structures.append(PyStructure(
                path=f.path,
                line_count=0,
                top_comment="",
            ))

    # 4. 提取启动文件的课程主题
    entry_structure = next(
        (s for s in structures if s.path == entry_path), None
    )
    course_title = entry_structure.course_title if entry_structure else None

    # 5. 识别项目类型
    all_imports = _collect_imports(structures)
    project_type = _detect_project_type(all_imports)

    # 6. 总行数
    total_lines = sum(s.line_count for s in structures)

    # 7. 警告
    warnings = []
    if course_title is None and entry_structure is not None:
        warnings.append(
            f"启动文件 {entry_path} 顶部未找到课程主题注释"
            "（如 # Course: xxx）"
        )
    if not all_imports:
        warnings.append("项目没有任何 import 语句")

    log.info(
        "项目分析完成: type=%s files=%d py=%d lines=%d course=%s",
        project_type, len(files), len(py_files), total_lines, course_title,
    )

    return ProjectMeta(
        folder=str(folder),
        entry_file=entry_path,
        project_type=project_type,
        course_title=course_title,
        all_files=files,
        py_files=structures,
        all_imports=sorted(set(all_imports)),
        total_lines=total_lines,
        warnings=warnings,
    )


# =========================
# 内部：文件扫描
# =========================
def _scan_files(folder: Path) -> list[FileInfo]:
    """递归扫描文件夹，返回文件列表（跳过常见排除目录）。"""
    files: list[FileInfo] = []
    for item in folder.rglob("*"):
        if not item.is_file():
            continue
        # 跳过排除目录中的文件
        if any(part in SKIP_DIRS for part in item.relative_to(folder).parts):
            continue
        rel = item.relative_to(folder)
        files.append(
            FileInfo(
                path=str(rel),
                name=item.name,
                is_python=item.suffix.lower() == ".py",
                size_bytes=item.stat().st_size,
            )
        )
    # 文件名排序
    files.sort(key=lambda f: f.path)
    return files


def _find_entry_file(folder: Path, py_files: list[FileInfo]) -> str:
    """识别启动文件路径。"""
    # 1. 优先 main.py
    for f in py_files:
        if f.name == "main.py" and "/" not in f.path:
            return f.path
    # 2. 根目录下首个 .py
    root_pys = [f for f in py_files if "/" not in f.path]
    if root_pys:
        return root_pys[0].path
    # 3. 任意首个
    return py_files[0].path


# =========================
# 内部：AST 解析
# =========================
def _parse_py_file(path: Path) -> PyStructure:
    """解析单个 .py 文件的 AST。"""
    source = path.read_text(encoding="utf-8", errors="ignore")
    line_count = source.count("\n") + (1 if source else 0)

    # 提取顶部注释（文件首部连续的 # 注释行）
    top_comment = _extract_top_comment(source)

    # AST 解析（容错：解析失败时返回空结构）
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        log.warning("AST 解析失败 %s: %s", path.name, e)
        return PyStructure(
            path=path.name,
            line_count=line_count,
            top_comment=top_comment,
        )

    imports: list[str] = []
    from_imports: list[tuple[str, str | None]] = []
    function_names: list[str] = []
    class_names: list[str] = []
    decorators: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module:
                imports.append(module)
            for alias in node.names:
                from_imports.append((module, alias.name))
        elif isinstance(node, ast.FunctionDef):
            function_names.append(node.name)
            for dec in node.decorator_list:
                decorators.append(_decorator_name(dec))
        elif isinstance(node, ast.AsyncFunctionDef):
            function_names.append(f"async {node.name}")
            for dec in node.decorator_list:
                decorators.append(_decorator_name(dec))
        elif isinstance(node, ast.ClassDef):
            class_names.append(node.name)
            for dec in node.decorator_list:
                decorators.append(_decorator_name(dec))

    # 解析顶部注释中的课程主题
    course_title = _parse_course_title(top_comment)
    # 解析顶部注释中的作业引导
    homework_guidance = _parse_homework_guidance(top_comment)

    return PyStructure(
        path=path.name,
        imports=sorted(set(imports)),
        from_imports=from_imports,
        function_names=function_names,
        class_names=class_names,
        decorators=sorted(set(d for d in decorators if d)),
        top_comment=top_comment,
        course_title=course_title,
        homework_guidance=homework_guidance,
        line_count=line_count,
    )


def _decorator_name(node: ast.expr) -> str:
    """从 AST 节点提取装饰器名。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _extract_top_comment(source: str) -> str:
    """提取文件首部的 # 注释行或文档字符串(v2 支持 '''/\"\"\" 多行)。"""
    lines: list[str] = []
    in_docstring = False
    quote_type = None  # '"""' 或 "'''"

    for line in source.splitlines():
        stripped = line.strip()

        # 文档字符串模式：收集到关闭引号为止
        if in_docstring:
            idx = stripped.find(quote_type)
            if idx >= 0:
                before = stripped[:idx].strip()
                if before:
                    lines.append(before)
                break
            lines.append(stripped)
            continue

        # 跳过开头的空行
        if not stripped:
            continue

        # 检测三引号文档字符串
        is_docstring = False
        for qt in ('"""', "'''"):
            if stripped.startswith(qt):
                remainder = stripped[3:]
                close_idx = remainder.rfind(qt)
                if close_idx >= 0:
                    # 单行文档字符串："""内容"""
                    content = remainder[:close_idx].strip()
                    if content:
                        lines.append(content)
                else:
                    # 多行文档字符串
                    in_docstring = True
                    quote_type = qt
                    if remainder.strip():
                        lines.append(remainder.strip())
                is_docstring = True
                break

        if is_docstring:
            continue

        # # 注释模式（原有逻辑）
        if stripped.startswith("#"):
            lines.append(stripped[1:].strip())
        else:
            break

    return "\n".join(lines)


def _parse_course_title(comment: str | None) -> str | None:
    """从注释中解析课程主题。"""
    if not comment:
        return None
    for line in comment.splitlines():
        for pattern in COURSE_PATTERNS:
            match = pattern.match(line)
            if match:
                return match.group(1).strip()
    return None


def _parse_homework_guidance(comment: str | None) -> str | None:
    """从注释中解析作业引导。

    在入口注释中查找作业引导标记（如 作业引导: / HomeworkGuidance:），
    将其后的内容（到注释末尾）提取为作业引导文本。
    """
    if not comment:
        return None
    lines = comment.splitlines()
    capture = False
    guidance: list[str] = []
    for line in lines:
        if not capture:
            # 检查是否是引导标记行
            for pattern in HOMEWORK_GUIDANCE_PATTERNS:
                if pattern.match(line):
                    capture = True
                    break
        else:
            # 收集标记后的内容行
            stripped = line.strip()
            if stripped:
                guidance.append(line)
            else:
                # 空行表示引导结束
                break
    return "\n".join(guidance).strip() or None


# =========================
# 内部：项目类型识别
# =========================
def _collect_imports(structures: list[PyStructure]) -> list[str]:
    """汇总所有 import。"""
    all_imports: list[str] = []
    for s in structures:
        all_imports.extend(s.imports)
        for module, _ in s.from_imports:
            if module:
                all_imports.append(module)
    return all_imports


def _detect_project_type(imports: list[str]) -> str:
    """根据 import 列表识别项目类型。"""
    imports_lower = " ".join(i.lower() for i in imports)
    for keyword, ptype in PROJECT_TYPE_RULES:
        if keyword in imports_lower:
            return ptype
    return "algorithm"  # 默认：无 GUI / Web 导入视为纯算法/逻辑
