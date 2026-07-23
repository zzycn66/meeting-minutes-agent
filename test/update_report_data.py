# -*- coding: utf-8 -*-
"""更新课程报告中的测试数据"""

from docx import Document
import os

# 测试结果数据
TEST_DATA = {
    "faster-whisper": {
        "accuracy": 51.48,
        "speed": 2.07,
        "response_time": 17.50,
        "recall": 51.48,
        "rtf": 0.48
    },
    "MiMo ASR": {
        "accuracy": 75.87,
        "speed": 14.15,
        "response_time": 2.56,
        "recall": 75.87,
        "rtf": 0.07
    },
    "openai-whisper": {
        "accuracy": 51.48,
        "speed": 0.37,
        "response_time": 96.85,
        "recall": 51.48,
        "rtf": 2.67
    }
}

def update_docx表格(doc_path):
    """更新 Word 文档中的表格数据"""
    doc = Document(doc_path)

    print("扫描文档中的表格...")

    for i, table in enumerate(doc.tables):
        print(f"\n表格 {i+1}：")
        for j, row in enumerate(table.rows):
            row_text = [cell.text.strip() for cell in row.cells]
            print(f"  行 {j}: {row_text}")

            # 查找包含语音识别数据的表格
            if any("faster-whisper" in cell.text.lower() or "whisper" in cell.text.lower() for cell in row.cells):
                print(f"  -> 找到语音识别表格！")

    return doc

def create_data_summary():
    """创建数据摘要供用户手动更新"""
    print("\n" + "=" * 60)
    print("测试数据摘要 - 请手动更新到课程报告中")
    print("=" * 60)

    print("""
┌─────────────────────────────────────────────────────────────────────────┐
│                        语音识别测试结果对比                              │
├─────────────────────┬─────────────┬─────────────┬───────────────────────┤
│       指标          │ faster-whisper│ MiMo ASR   │  openai-whisper      │
├─────────────────────┼─────────────┼─────────────┼───────────────────────┤
│ 识别准确率          │   51.48%    │   75.87%    │     51.48%           │
│ 处理速度 (x实时)    │   2.07x     │   14.15x    │     0.37x            │
│ 平均响应时间 (秒)   │   17.50s    │    2.56s    │     96.85s           │
│ 实时因子 (RTF)      │    0.48     │    0.07     │      2.67            │
│ 召回率              │   51.48%    │   75.87%    │     51.48%           │
└─────────────────────┴─────────────┴─────────────┴───────────────────────┘

测试环境：
- 测试音频：5段会议录音，总时长 181.28 秒（约 3 分钟）
- 测试音频来源：使用 MiMo TTS (冰糖音色) 合成
- CPU 环境：无 GPU，纯 CPU 推理
- Whisper 模型：medium（769M 参数）

结论：
1. MiMo ASR 准确率最高（75.87%），是 faster-whisper 的 1.47 倍
2. MiMo ASR 速度最快（14.15x 实时），是 faster-whisper 的 6.83 倍
3. faster-whisper 比 openai-whisper 快 5.59 倍（CTranslate2 加速）
4. openai-whisper 最慢，处理 1 秒音频需要 2.67 秒
""")

if __name__ == "__main__":
    docx_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "docx_output",
        "课程报告-最终版v8.docx"
    )

    if os.path.exists(docx_path):
        print(f"找到课程报告：{docx_path}")
        doc = update_docx表格(docx_path)
    else:
        print(f"未找到课程报告：{docx_path}")

    create_data_summary()
