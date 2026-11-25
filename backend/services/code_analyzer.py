"""
代码分析服务

职责：
1. 扫描项目文件夹，识别 Python / C / C++ 源文件与资源文件
2. Python 用 AST 解析；C/C++ 用轻量正则解析函数、类、#include
3. 解析启动文件顶部注释（提取课程主题、作业引导）
4. 提取依赖（Python imports / C/C++ #include）
5. 识别项目类型（pygame / turtle / web / cpp / c / algorithm）

约定启动文件识别：
  - Python：优先 main.py，其次根目录有逻辑的 .py
  - C/C++：优先 main.cpp / main.c，其次包含 main() 的文件
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
    re.compile(r"^\s*#?\s*课程\s+(.+?)\s*$"),                # "课程 飞向地球"（空格分隔）
    re.compile(r"^\s*#?\s*课程名\s*[:：]\s*(.+?)\s*$"),
    re.compile(r"^\s*#?\s*主题\s*[:：]\s*(.+?)\s*$"),
]

# 作业引导识别模式（已去除 # 前缀，因为 _extract_top_comment 已剥掉）
# 注意：三个 pattern 必须按此顺序（精确→模糊），且不能以 $ 结尾，
# 因为要兼容"作业：画五角星"（同一行有内容）和"作业："（独占一行）两种格式。
HOMEWORK_GUIDANCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*作业引导\s*[:：]"),                    # "作业引导：xxx"
    re.compile(r"^\s*作业指导\s*[:：]"),                    # "作业指导：xxx"
    re.compile(r"^\s*作业\s*[:：]"),                        # "作业：画五角星" 或 "作业："
    re.compile(r"^\s*作业\s*$"),                            # 单独一行 "作业"
    re.compile(r"^\s*Homework\s*$", re.IGNORECASE),         # 单独一行 "Homework"
    re.compile(r"^\s*HomeworkGuidance\s*[:：]", re.IGNORECASE),
]

# 入口注释中的常见段落标题（作业段之后出现这些行时，说明作业段已结束）
SECTION_START_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*笔记\s*[:：]?\s*$"),
    re.compile(r"^\s*目标\s*[:：]?\s*$"),
    re.compile(r"^\s*总结\s*[:：]?\s*$"),
    re.compile(r"^\s*内容\s*[:：]?\s*$"),
    re.compile(r"^\s*知识点\s*[:：]?\s*$"),
    re.compile(r"^\s*课堂表现\s*[:：]?\s*$"),
    re.compile(r"^\s*课程名?\s*[:：]"),
    re.compile(r"^\s*主题\s*[:：]"),
    re.compile(r"^\s*Course\s*[:：]", re.IGNORECASE),
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
    ("walimaker", "pgzero"),       # Walimaker ≈ pgzero（游戏框架）
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

# 代码文件扩展名
PYTHON_EXTS = {".py"}
C_EXTS = {".c", ".h"}
CPP_EXTS = {".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx"}
CODE_EXTS = PYTHON_EXTS | C_EXTS | CPP_EXTS

# C/C++ 控制关键字（不要把 if/for/while 等当成函数名）
CPP_CONTROL_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "default",
    "try", "catch", "throw", "return", "sizeof", "new", "delete",
    "namespace", "using", "typedef", "struct", "class", "enum",
    "static_assert", "decltype", "alignof", "typeid", "operator",
}


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
    is_code: bool = False
    language: str | None = None


@dataclass
class PyStructure:
    """单个代码文件的结构（Python / C / C++ 共用）。"""
    path: str
    language: str = "python"
    imports: list[str] = field(default_factory=list)
    from_imports: list[tuple[str, str | None]] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    top_comment: str | None = None  # 文件顶部注释
    course_title: str | None = None  # 解析出的课程主题
    homework_guidance: str | None = None  # 解析出的作业引导
    line_count: int = 0
    has_main_function: bool = False  # C/C++ 是否包含 main()


@dataclass
class ProjectMeta:
    """项目元信息汇总。"""
    folder: str
    entry_file: str | None  # 启动文件相对路径
    project_type: str  # pygame / turtle / tkinter / web / cpp / c / algorithm
    language: str  # python / cpp / c
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

    code_files = [f for f in files if f.is_code]
    if not code_files:
        raise ValueError(f"未找到任何 .py / .cpp / .c 代码文件: {folder}")

    # 2. 识别项目主语言
    language = _detect_language(code_files)

    # 3. 先解析所有代码文件，让入口选择器能基于代码内容做决策
    structures: list[PyStructure] = []
    for f in code_files:
        abs_path = folder / f.path
        try:
            if f.is_python:
                struct = _parse_py_file(abs_path)
            else:
                struct = _parse_cpp_file(abs_path)
            struct.path = f.path
            struct.language = f.language or language
            structures.append(struct)
        except Exception as e:
            log.warning("解析 %s 失败: %s", f.path, e)
            structures.append(PyStructure(
                path=f.path,
                language=f.language or language,
                line_count=0,
                top_comment="",
            ))

    # 4. 识别启动文件（基于解析结果：有函数/类/import 的小文件优先）
    entry_path = _find_entry_file(folder, code_files, structures, language)
    log.info("启动文件: %s", entry_path)

    # 4. 提取启动文件的课程主题
    entry_structure = next(
        (s for s in structures if s.path == entry_path), None
    )
    course_title = entry_structure.course_title if entry_structure else None

    # 5. 识别项目类型
    all_imports = _collect_imports(structures)
    project_type = _detect_project_type(all_imports, language)

    # 6. 总行数
    total_lines = sum(s.line_count for s in structures)

    # 7. 警告
    warnings = []
    if course_title is None and entry_structure is not None:
        comment_example = "// Course: xxx" if language != "python" else "# Course: xxx"
        warnings.append(
            f"启动文件 {entry_path} 顶部未找到课程主题注释"
            f"（如 {comment_example}）"
        )
    if not all_imports:
        warnings.append("项目没有任何 #include / import 语句")

    log.info(
        "项目分析完成: language=%s type=%s files=%d code=%d lines=%d course=%s",
        language, project_type, len(files), len(code_files), total_lines, course_title,
    )

    return ProjectMeta(
        folder=str(folder),
        entry_file=entry_path,
        project_type=project_type,
        language=language,
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
        parts = item.relative_to(folder).parts
        # 跳过排除目录（含 macOS 的 .dSYM 调试包）
        if any(part in SKIP_DIRS or part.endswith(".dSYM") for part in parts):
            continue
        rel = item.relative_to(folder)
        suffix = item.suffix.lower()
        is_python = suffix in PYTHON_EXTS
        is_code = suffix in CODE_EXTS
        if is_python:
            language = "python"
        elif suffix in {".c", ".h"}:
            language = "c"
        elif suffix in CPP_EXTS:
            language = "cpp"
        else:
            language = None
        files.append(
            FileInfo(
                path=str(rel),
                name=item.name,
                is_python=is_python,
                size_bytes=item.stat().st_size,
                is_code=is_code,
                language=language,
            )
        )
    # 文件名排序
    files.sort(key=lambda f: f.path)
    return files


def _detect_language(code_files: list[FileInfo]) -> str:
    """根据代码文件扩展名判断项目主语言。"""
    if any(f.language == "cpp" for f in code_files):
        return "cpp"
    if any(f.language == "c" for f in code_files):
        return "c"
    return "python"


def _get_line_count(f: FileInfo, structs: dict[str, PyStructure]) -> int:
    """获取文件行数：优先从 PyStructure 取，其次从大小估算。"""
    s = structs.get(f.path)
    if s and s.line_count:
        return s.line_count
    # 粗略估算：每行约 50 字节
    return max(1, f.size_bytes // 50)


def _find_entry_file(
    folder: Path,
    code_files: list[FileInfo],
    structures: list[PyStructure] | None = None,
    language: str = "python",
) -> str:
    """识别启动文件路径。

    Python 策略：优先 main.py → 根目录有逻辑的最小 .py。
    C/C++ 策略：优先 main.cpp/main.c → 包含 main() 的根目录文件 →
                根目录有函数/类的最小文件。
    """
    root_files = [f for f in code_files if "/" not in f.path]
    name_to_struct = {s.path: s for s in (structures or [])}

    # 1. 入口文件名优先
    preferred = (
        ["main.py"] if language == "python"
        else ["main.cpp", "main.c", "main.cc", "main.cxx"]
    )
    for name in preferred:
        for f in root_files:
            if f.name == name:
                return f.path

    # 2. C/C++ 找包含 main() 的文件
    if language != "python":
        for f in root_files:
            s = name_to_struct.get(f.path)
            if s and s.has_main_function:
                return f.path

    # 3. 找有实际逻辑的最小文件（排除纯数据文件）
    candidates = []
    for f in root_files:
        s = name_to_struct.get(f.path)
        has_logic = s and (s.function_names or s.class_names or s.imports)
        line_cnt = _get_line_count(f, name_to_struct)
        if has_logic:
            candidates.append((f.path, line_cnt))
    if candidates:
        return min(candidates, key=lambda x: x[1])[0]

    # 4. 回退：根目录下最小文件
    if root_files:
        return min(root_files, key=lambda x: _get_line_count(x, name_to_struct)).path

    # 5. 兜底
    return code_files[0].path


# =========================
# 内部：C/C++ 解析
# =========================
def _parse_cpp_file(path: Path) -> PyStructure:
    """解析单个 C/C++ 文件（轻量正则，不依赖编译器）。"""
    source = path.read_text(encoding="utf-8", errors="ignore")
    line_count = source.count("\n") + (1 if source else 0)

    top_comment = _extract_cpp_top_comment(source)
    clean_source = _strip_cpp_comments(source)
    includes = re.findall(r'#\s*include\s*[<"]([^>"]+)[>"]', clean_source)
    function_names = _extract_cpp_functions(clean_source)
    class_names = re.findall(
        r'(?m)^\s*(?:class|struct)\s+([A-Za-z_]\w*)', clean_source
    )

    return PyStructure(
        path=path.name,
        language="cpp" if path.suffix.lower() not in {".c", ".h"} else "c",
        imports=sorted(set(includes)),
        function_names=sorted(set(function_names)),
        class_names=sorted(set(class_names)),
        top_comment=top_comment,
        course_title=_parse_course_title(top_comment),
        homework_guidance=_parse_homework_guidance(top_comment),
        line_count=line_count,
        has_main_function="main" in function_names,
    )


def _strip_cpp_comments(source: str) -> str:
    """去掉 C/C++ 注释，保留换行以维持行号；用于 #include/函数名提取。"""
    result: list[str] = []
    i = 0
    length = len(source)
    state = "normal"  # normal | line | block | string | char
    while i < length:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < length else ""

        if state == "normal":
            if ch == "/" and nxt == "/":
                state = "line"
                result.append("  ")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block"
                result.append("  ")
                i += 2
                continue
            if ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            result.append(ch)
            i += 1
            continue

        if state == "line":
            if ch == "\n":
                state = "normal"
                result.append("\n")
            else:
                result.append(" ")
            i += 1
            continue

        if state == "block":
            if ch == "*" and nxt == "/":
                state = "normal"
                result.append("  ")
                i += 2
                continue
            result.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        # string / char：保留内容，处理转义
        result.append(ch)
        if ch == "\\":
            if i + 1 < length:
                result.append(source[i + 1])
                i += 2
                continue
        elif (state == "string" and ch == '"') or (state == "char" and ch == "'"):
            state = "normal"
        i += 1

    return "".join(result)


def _extract_cpp_top_comment(source: str) -> str:
    """提取 C/C++ 文件顶部的 // 行注释或 /* ... */ 块注释。

    支持两种常见写法：
        // 课程：xxx
        // 目标：xxx
    以及：
        /*
         * 课程：xxx
         * 目标：xxx
         */
    """
    lines = source.splitlines()
    collected: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            # 空行是注释块之间的边界，保留给作业引导解析器
            if collected and collected[-1] != "":
                collected.append("")
            i += 1
            continue

        if stripped.startswith("//"):
            collected.append(stripped[2:].strip())
            i += 1
            continue

        if stripped.startswith("/*"):
            remainder = stripped[2:]
            # 单行块注释 /* xxx */
            if "*/" in remainder:
                content = remainder.split("*/", 1)[0].strip()
                if content:
                    collected.append(content)
                collected.append("")
                i += 1
                continue

            # 多行块注释
            first = remainder.strip()
            if first:
                collected.append(first)
            i += 1
            while i < len(lines):
                body = lines[i].strip()
                if "*/" in body:
                    before = body.split("*/", 1)[0].strip()
                    if before:
                        collected.append(before.lstrip("*").strip())
                    collected.append("")
                    i += 1
                    break
                cleaned = body.lstrip("*").strip()
                if cleaned:
                    collected.append(cleaned)
                i += 1
            continue

        # 遇到 #include / 代码，顶部注释结束
        break

    return "\n".join(collected).strip()


def _extract_cpp_functions(source: str) -> list[str]:
    """从 C/C++ 源码中提取函数名（轻量规则，供入口识别和 AI 参考）。"""
    names: list[str] = []
    # 带返回类型的函数定义：int main() { / void Character::attack(int) {
    pattern_with_type = re.compile(
        r"(?m)^[ \t]*(?:template\s*<[^>]*>\s*)?"
        r"(?:[A-Za-z_][\w:<>,\s*&\[\]]*?)\s+"
        r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*"
        r"(?:const\s*)?(?:noexcept\s*)?\{"
    )
    # 构造函数：Character(...) { / explicit Character(...) {
    pattern_ctor = re.compile(
        r"(?m)^[ \t]*(?:explicit\s+)?([A-Za-z_]\w*)\s*"
        r"\([^;{}]*\)\s*(?::[^{]+)?\{"
    )
    for pattern in (pattern_with_type, pattern_ctor):
        for match in pattern.finditer(source):
            name = match.group(1)
            if name and name not in CPP_CONTROL_KEYWORDS:
                names.append(name)
    return names


# =========================
# 内部：Python AST 解析
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

    在入口注释中查找作业引导标记（如 作业引导: / 作业: / HomeworkGuidance:），
    将其后的内容（到注释末尾）提取为作业引导文本。

    支持两种格式：
    1. 标记独占一行，后续行为内容：
        作业：
        画一个五角星
        使用 circle 函数
    2. 标记和内容在同一行：
        作业：画一个五角星，使用 circle 函数
    """
    if not comment:
        return None
    lines = comment.splitlines()
    capture = False
    guidance: list[str] = []
    for line in lines:
        if not capture:
            # 检查是否是引导标记行
            matched = False
            matched_inline = False
            for pattern in HOMEWORK_GUIDANCE_PATTERNS:
                if pattern.match(line):
                    # 去掉标记后的行内内容（格式2：作业：画五角星）
                    remainder = pattern.sub("", line).strip()
                    if remainder:
                        guidance.append(remainder)
                        matched_inline = True
                    else:
                        matched = True
                    # 匹配到一个就不再继续
                    break
            if matched:
                capture = True
            elif matched_inline:
                break  # 格式2 一行搞定，直接结束
        else:
            # 收集标记后的内容行（格式1：标记后跟内容行）
            stripped = line.strip()
            if not stripped:
                # 空行表示引导结束
                break
            # 出现新的段落标题（笔记/目标/总结…）说明作业段已结束
            if any(p.match(line) for p in SECTION_START_PATTERNS):
                break
            guidance.append(line)
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


def _detect_project_type(imports: list[str], language: str = "python") -> str:
    """根据依赖列表和语言识别项目类型。"""
    imports_lower = " ".join(i.lower() for i in imports)

    if language in ("cpp", "c"):
        # C/C++ 图形/游戏框架
        gui_keywords = (
            "sfml", "sdl", "glfw", "opengl", "gl/", "qt", "qtwidgets",
            "graphics.h", "easyx", "raylib", "allegro", "imgui",
        )
        if any(keyword in imports_lower for keyword in gui_keywords):
            return "cpp_gui"
        return "cpp" if language == "cpp" else "c"

    for keyword, ptype in PROJECT_TYPE_RULES:
        if keyword in imports_lower:
            return ptype
    return "algorithm"  # 默认：无 GUI / Web 导入视为纯算法/逻辑
