"""
Prompt 模板 3：作业 + 单词

生成课后作业（结构化）与单词学习卡。
输出：JSON 对象
"""
HOMEWORK_VOCAB_PROMPT = """你是少儿 Python 编程老师。为本节课生成：
1. 一份课后作业（难度不高、巩固本节知识点）
2. 一个英文单词（与本节强相关）

【知识点】
{knowledge_points}

【项目类型】
{project_type}

【学生基础水平】
{student_level}    （入门/初级/中级）

【作业要求】
- 目标：明确说明作业要巩固什么
- 提示：给学生 2-3 条思路提示（不要直接给答案）
- 评分点：3-5 条具体可观察的评判标准

【单词要求】
- 单词：项目代码中实际出现或密切相关的英文术语
- 音标：IPA 音标
- 中文释义：简洁（1-2 词）
- 例句：在本项目语境中的使用示例

【输出 JSON 格式】
{{
  "homework": {{
    "goal": "作业目标（30-50字）",
    "hints": ["提示1", "提示2", "提示3"],
    "criteria": ["评分点1", "评分点2", "评分点3"]
  }},
  "vocabulary": {{
    "word": "Character",
    "phonetic": "/ˈkærəktər/",
    "meaning": "角色",
    "example": "bird = Character('bird.png')"
  }}
}}
"""
