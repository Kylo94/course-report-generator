# 模板开发指南

本目录包含课程报告生成工具的内置模板。你可以通过"模板管理"页面的 **上传模板** 功能导入自己编写的自定义模板。

---

## 目录结构

每个模板是一个独立的文件夹，包含 **3 个必需文件**：

```
my-template/
  config.json      # 模板配置（元信息、主题、Logo 设置）
  template.html    # Jinja2 模板（报告内容布局）
  style.css        # 样式表（页面外观）
```

上传时将这 3 个文件打包成一个 **zip**（无子目录），在模板管理页面上传即可。

---

## config.json 参考

### 完整结构

```json
{
  "id": "my-template",                    // 自动生成，写什么都会被覆盖
  "name": "我的模板",                      // 【必填】显示名称，最长 50 字
  "version": "1.0",                       // 可选，默认 "1.0"
  "is_builtin": false,                    // 自动设为 false
  "parent_template": null,                // 自动清除
  "thumbnail": "",                        // 可选，预览缩略图路径
  "description": "简洁专业的模板风格",     // 可选，模板简介
  "page_size": "A4",                      // 可选，默认 "A4"
  "theme": {
    "primary_color": "#2563EB",           // 主色（十六进制）
    "secondary_color": "#EFF6FF",         // 辅色（十六进制）
    "font_title": "Heiti SC",             // 标题字体
    "font_body": "STSong",                // 正文字体
    "font_size_title": 26,                // 标题字号 (pt)
    "font_size_body": 11,                 // 正文字号 (pt)
    "background_color": null,             // 页面背景色（十六进制或 null）
    "background_image": null,             // 背景图片（data URI 或 null）
    "page_margin_top": 20,                // 上边距 (mm)
    "page_margin_right": 18,              // 右边距 (mm)
    "page_margin_bottom": 18,             // 下边距 (mm)
    "page_margin_left": 18                // 左边距 (mm)
  },
  "logo_config": {
    "enabled": true,                      // 是否显示 Logo
    "position": "top-right",              // 位置：top-left / top-right / top-center / bottom-left / bottom-right / bottom-center
    "size": 30,                           // Logo 宽度 (mm)
    "show_on_all_pages": true,            // 是否每页显示
    "margin": 5                           // Logo 距页面边缘距离 (mm)
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 模板显示名称，最长 50 字 |
| `theme` | 否 | 主题设置。所有子字段均可省略，省略则使用系统默认值 |
| `theme.primary_color` | 否 | 主色，用于标题、强调元素 |
| `theme.secondary_color` | 否 | 辅色，用于背景区块、卡片 |
| `theme.font_title` | 否 | 标题字体，建议使用系统常见字体 |
| `theme.font_body` | 否 | 正文字体 |
| `theme.font_size_title` | 否 | 标题字号 (pt)，范围 12-48 |
| `theme.font_size_body` | 否 | 正文字号 (pt)，范围 8-20 |
| `theme.page_margin_*` | 否 | 页面边距 (mm)，范围 5-40 |
| `logo_config` | 否 | 省略则不显示 Logo |
| 其他字段 | 否 | 上传时自动处理 |

> **注意**：`id`、`is_builtin`、`parent_template` 在上传时会被自动覆盖，config.json 中写什么值都无效。

---

## template.html — Jinja2 模板

上传后系统使用 **Jinja2** 引擎渲染该文件。以下变量可在模板中直接使用：

### 样式变量

| 变量 | 说明 |
|---|---|
| `{{ css_content \| safe }}` | `style.css` 的全部内容，用 `<style>` 包裹 |
| `{{ custom_style \| safe }}` | 从 `config.json theme` 自动生成的 CSS 自定义属性（`:root { ... }`）|

### 报告内容变量

| 变量 | 类型 | 说明 |
|---|---|---|
| `{{ course_topic }}` | string | 课程名称 |
| `{{ student_name }}` | string | 学生姓名 |
| `{{ course_date }}` | string | 上课日期（YYYY-MM-DD） |
| `{{ knowledge_points }}` | list\[string\] | 知识点列表，如 `["if-else条件判断", "函数定义"]` |
| `{{ ability_improvement }}` | string | 能力提升描述文本 |
| `{{ content_items }}` | list\[dict\] | 内容详解，每项 `{kp: "知识点名", text: "60-100字描述"}` |
| `{{ vocabulary }}` | dict | 单词学习卡：`{word, phonetic, meaning, example}` |
| `{{ homework }}` | dict | 作业：`{goal, hints: [], criteria: [], questions: []}` |
| `{{ evaluation }}` | string | 学生评价文本 |
| `{{ screenshots }}` | list\[string\] | 截图列表（data URI 格式） |
| `{{ logo }}` | dict\|null | Logo 信息：`{data_uri, position, width_mm, show_on_all_pages}`，无 Logo 时为 null |
| `{{ code_excerpt }}` | string | 代码片段（最多 15 行） |

### Jinja2 语法示例

```html
<!-- 条件判断 -->
{% if logo %}
<div class="logo">
  <img src="{{ logo.data_uri }}" style="width: {{ logo.width_mm }}mm;">
</div>
{% endif %}

<!-- 循环 -->
{% for kp in knowledge_points %}
<span class="kp-badge">{{ kp }}</span>
{% endfor %}

<!-- 列表下标 + 安全过滤 -->
{{ code_excerpt | e }}

<!-- 不转义（CSS 内容需要） -->
{{ css_content | safe }}
```

> 完整示例参考本目录下的 `classic/template.html`。

---

## style.css 编写指南

### CSS 自定义属性

系统根据 `config.json` 的 `theme` 自动生成以下 CSS 变量，可在 `style.css` 中直接引用：

```css
:root {
  --primary: #2563EB;              /* theme.primary_color */
  --secondary: #EFF6FF;            /* theme.secondary_color */
  --bg-color: #FFFFFF;             /* theme.background_color */
  --font-title: "Heiti SC", ...;   /* theme.font_title + fallback */
  --font-body: "STSong", ...;      /* theme.font_body + fallback */
  --fs-title: 26pt;                /* theme.font_size_title */
  --fs-body: 11pt;                 /* theme.font_size_body */
  --page-margin-top: 20mm;        /* theme.page_margin_top */
  --page-margin-right: 18mm;      /* theme.page_margin_right */
  --page-margin-bottom: 18mm;     /* theme.page_margin_bottom */
  --page-margin-left: 18mm;       /* theme.page_margin_left */
  --logo-offset-top: 5mm;         /* 根据 logo_config.margin 计算 */
  --logo-offset-right: 5mm;       /* 同上 */
  --logo-offset-bottom: 5mm;      /* 同上 */
  --logo-offset-left: 5mm;        /* 同上 */
}
```

**推荐做法**：始终用 `var(--name, fallback)` 形式引用，确保即使变量缺失也有默认值：

```css
.title {
  color: var(--primary, #2563EB);
  font-family: var(--font-title, "Heiti SC", sans-serif);
}
```

### 打印设置

为 PDF 打印做准备，建议在 CSS 开头设置：

```css
@page {
  size: A4;
  margin: 0;
}
```

### 页面分隔

每页内容用 `.page` 类包裹，CSS 中设置自动分页：

```css
.page {
  page-break-after: always;
}
```

系统会在预览时为 `.page` 添加 A4 纸张模拟样式。

### 字体建议

中文字体推荐（需附带英文字体 fallback）：

- 标题：`"Heiti SC", "PingFang SC", sans-serif`
- 正文：`"STSong", "SimSun", "Noto Serif SC", serif`
- 等宽（代码）：`"SF Mono", "Menlo", "Consolas", monospace`

---

## 打包与上传

1. **准备 3 个文件**：`config.json`、`template.html`、`style.css`
2. **打包为 zip**（无子目录）：
   ```bash
   cd my-template/
   zip -j my-template.zip config.json template.html style.css
   ```
   > `-j` 参数确保 zip 中不包含目录路径
3. **上传**：在"模板管理"页面，点击 **上传模板**，选择 zip 文件
4. **验证**：上传成功后可在自定义模板列表中看到新模板，点击 **预览** 查看效果

### 文件要求

| 要求 | 说明 |
|---|---|
| 文件数量 | 恰好 3 个文件，无多余文件 |
| 子目录 | 不允许 |
| 路径穿越 | 不允许（文件名含 `..` 会被拒绝） |
| 大小限制 | zip 不超过 **5MB** |
| 编码 | `template.html` 和 `style.css` 使用 UTF-8 编码 |
| config.json | 必须是合法 JSON，必须有 `name` 字段 |
| template.html | 不能为空 |

---

## 最佳实践

1. **页边距**：建议至少保留 15mm 边距，避免内容被打印裁切
2. **颜色**：主色用于标题和强调元素，辅色用于背景区块，保持对比度
3. **字体大小**：标题 22-30pt，正文 10-13pt 为宜
4. **截图**：截图以 data URI 嵌入，建议在模板中设计画廊区域（flex 布局）
5. **代码**：使用深色背景 + 等宽字体展示代码片段
6. **Logo**：如果在 `logo_config` 中启用，模板中记得预留 Logo 位置
7. **测试**：上传后立即预览，确保布局正常、变量正确渲染

---

## 示例：最小模板

### config.json

```json
{
  "name": "简洁模板",
  "description": "一个简洁的课程报告模板",
  "theme": {
    "primary_color": "#3B82F6",
    "secondary_color": "#EFF6FF",
    "font_title": "Heiti SC",
    "font_body": "STSong"
  }
}
```

### template.html

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{{ css_content | safe }}</style>
<style>{{ custom_style | safe }}</style>
</head>
<body>
<div class="page">
  <h1 class="title">{{ course_topic }}</h1>
  <p class="info">{{ student_name }} | {{ course_date }}</p>

  <h2>知识点</h2>
  <ul>
  {% for kp in knowledge_points %}
    <li>{{ kp }}</li>
  {% endfor %}
  </ul>

  <h2>评价</h2>
  <p>{{ evaluation }}</p>
</div>
</body>
</html>
```

### style.css

```css
@page { size: A4; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--font-body, "STSong", serif);
  font-size: var(--fs-body, 11pt);
  color: #333;
  padding: 20mm;
}
.page { page-break-after: always; }
.title {
  font-family: var(--font-title, "Heiti SC", sans-serif);
  font-size: var(--fs-title, 26pt);
  color: var(--primary, #3B82F6);
  text-align: center;
  margin-bottom: 10mm;
}
.info { text-align: center; color: #666; margin-bottom: 8mm; }
h2 {
  color: var(--primary, #3B82F6);
  margin: 6mm 0 3mm;
  border-bottom: 2px solid var(--secondary, #EFF6FF);
}
li { margin: 2mm 0; line-height: 1.7; }
```

---

## 升级兼容性说明

如果从旧版本升级，需要注意：

- `theme` 中的 `page_margin_*` 和 `background_*` 字段是后续增加的，旧模板无需修改
- `logo_config` 也是后续新增的，旧模板省略时不会显示 Logo
- 上传的 config.json 中如果包含未列出的字段，将被保留但不会影响渲染
