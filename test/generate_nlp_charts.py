# -*- coding: utf-8 -*-
"""生成 NLP 引擎测试结果图表"""

import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
matplotlib.rcParams['axes.unicode_minus'] = False

# NLP 测试数据
engines = ['关键词匹配引擎', 'DeepSeek AI引擎', 'Qwen3本地引擎']

# 关键信息召回率 (%)
recall = [14.29, 9.52, 47.62]

# 平均响应时间 (秒)
response_time = [0.012, 3.61, 41.54]

# ========== 图1: NLP 引擎召回率对比 ==========
fig1, ax1 = plt.subplots(figsize=(8, 5))

colors = ['#4a4a4a', '#5a5a5a', '#2d2d2d']
bars1 = ax1.bar(engines, recall, color=colors, width=0.6, edgecolor='black', linewidth=0.5)

# 添加数据标签
for bar, val in zip(bars1, recall):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             f'{val:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')

ax1.set_ylabel('关键信息召回率 (%)', fontsize=12)
ax1.set_title('三种NLP引擎关键信息召回率对比', fontsize=14, fontweight='bold', pad=15)
ax1.set_ylim(0, 60)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.tick_params(axis='x', labelsize=10)
ax1.tick_params(axis='y', labelsize=10)

plt.tight_layout()
fig1.savefig('chart_nlp_recall.png', dpi=300, bbox_inches='tight')
print("图表1已保存：chart_nlp_recall.png")

# ========== 图2: NLP 引擎响应时间对比 ==========
fig2, ax2 = plt.subplots(figsize=(8, 5))

bars2 = ax2.bar(engines, response_time, color=colors, width=0.6, edgecolor='black', linewidth=0.5)

# 添加数据标签
for bar, val in zip(bars2, response_time):
    if val < 1:
        label = f'{val*1000:.0f}ms'
    else:
        label = f'{val:.2f}s'
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             label, ha='center', va='bottom', fontsize=12, fontweight='bold')

ax2.set_ylabel('平均响应时间', fontsize=12)
ax2.set_title('三种NLP引擎响应时间对比', fontsize=14, fontweight='bold', pad=15)
ax2.set_ylim(0, max(response_time) * 1.2)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.tick_params(axis='x', labelsize=10)
ax2.tick_params(axis='y', labelsize=10)

plt.tight_layout()
fig2.savefig('chart_nlp_response.png', dpi=300, bbox_inches='tight')
print("图表2已保存：chart_nlp_response.png")

# ========== 图3: NLP 引擎综合对比（双Y轴） ==========
fig3, ax3 = plt.subplots(figsize=(10, 5))

x = range(len(engines))
width = 0.35

# 召回率柱状图
bars1 = ax3.bar([i - width/2 for i in x], recall, width, label='召回率 (%)', color='#4a4a4a', edgecolor='black', linewidth=0.5)
ax3.set_ylabel('召回率 (%)', fontsize=12)
ax3.set_ylim(0, 60)

# 响应时间柱状图（使用右侧Y轴）
ax3_right = ax3.twinx()
bars2 = ax3_right.bar([i + width/2 for i in x], response_time, width, label='响应时间 (s)', color='#8a8a8a', edgecolor='black', linewidth=0.5)
ax3_right.set_ylabel('响应时间 (秒)', fontsize=12)
ax3_right.set_ylim(0, max(response_time) * 1.2)

# 添加数据标签
for bar, val in zip(bars1, recall):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             f'{val:.1f}%', ha='center', va='bottom', fontsize=10)

for bar, val in zip(bars2, response_time):
    if val < 1:
        label = f'{val*1000:.0f}ms'
    else:
        label = f'{val:.2f}s'
    ax3_right.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             label, ha='center', va='bottom', fontsize=10)

# 设置X轴标签
ax3.set_xticks(x)
ax3.set_xticklabels(engines, fontsize=10)
ax3.set_title('NLP引擎召回率与响应时间对比', fontsize=14, fontweight='bold', pad=15)

# 合并图例
lines1, labels1 = ax3.get_legend_handles_labels()
lines2, labels2 = ax3_right.get_legend_handles_labels()
ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10)

ax3.spines['top'].set_visible(False)
ax3_right.spines['top'].set_visible(False)

plt.tight_layout()
fig3.savefig('chart_nlp_combined.png', dpi=300, bbox_inches='tight')
print("图表3已保存：chart_nlp_combined.png")

# ========== 打印数据摘要 ==========
print("\n" + "=" * 60)
print("NLP 引擎测试数据摘要")
print("=" * 60)
print(f"""
┌─────────────────────┬─────────────┬─────────────┬─────────────┐
│       指标          │ 关键词匹配  │ DeepSeek AI │ Qwen3本地   │
├─────────────────────┼─────────────┼─────────────┼─────────────┤
│ 关键信息召回率      │   {recall[0]:.1f}%    │   {recall[1]:.1f}%    │   {recall[2]:.1f}%    │
│ 平均响应时间        │   12ms      │   3.61s     │   41.54s    │
└─────────────────────┴─────────────┴─────────────┴─────────────┘
""")

plt.show()
