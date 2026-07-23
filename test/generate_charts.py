# -*- coding: utf-8 -*-
"""生成语音识别测试结果图表"""

import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
matplotlib.rcParams['axes.unicode_minus'] = False

# 真实测试数据
engines = ['faster-whisper', 'openai-whisper', 'MiMo ASR']

# 准确率 (%)
accuracy = [51.48, 51.48, 75.87]

# 处理速度 (x实时) - 数值越大越快
speed_realtime = [2.07, 0.37, 14.15]

# 平均响应时间 (秒)
response_time = [17.50, 96.85, 2.56]

# 实时因子 RTF (越小越好)
rtf = [0.48, 2.67, 0.07]

# ========== 图1: 准确率对比 ==========
fig1, ax1 = plt.subplots(figsize=(8, 5))

colors = ['#4a4a4a', '#4a4a4a', '#2d2d2d']
bars1 = ax1.bar(engines, accuracy, color=colors, width=0.6, edgecolor='black', linewidth=0.5)

# 添加数据标签
for bar, val in zip(bars1, accuracy):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
             f'{val:.1f}%', ha='center', va='bottom', fontsize=12, fontweight='bold')

ax1.set_ylabel('准确率 (%)', fontsize=12)
ax1.set_title('三种语音识别引擎准确率对比', fontsize=14, fontweight='bold', pad=15)
ax1.set_ylim(0, 100)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.tick_params(axis='x', labelsize=11)
ax1.tick_params(axis='y', labelsize=10)

plt.tight_layout()
fig1.savefig('chart_accuracy.png', dpi=300, bbox_inches='tight')
print("图表1已保存：chart_accuracy.png")

# ========== 图2: 处理速度对比（秒/分钟音频） ==========
fig2, ax2 = plt.subplots(figsize=(8, 5))

# 计算秒/分钟音频
total_audio_minutes = 181.28 / 60  # 总音频时长（分钟）
speed_per_minute = [17.50/total_audio_minutes, 96.85/total_audio_minutes, 2.56/total_audio_minutes]

bars2 = ax2.bar(engines, speed_per_minute, color=colors, width=0.6, edgecolor='black', linewidth=0.5)

# 添加数据标签
for bar, val in zip(bars2, speed_per_minute):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
             f'{val:.1f}s', ha='center', va='bottom', fontsize=12, fontweight='bold')

ax2.set_ylabel('处理时间 (秒/分钟音频)', fontsize=12)
ax2.set_title('三种语音识别引擎处理速度对比', fontsize=14, fontweight='bold', pad=15)
ax2.set_ylim(0, max(speed_per_minute) * 1.2)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.tick_params(axis='x', labelsize=11)
ax2.tick_params(axis='y', labelsize=10)

plt.tight_layout()
fig2.savefig('chart_speed.png', dpi=300, bbox_inches='tight')
print("图表2已保存：chart_speed.png")

# ========== 图3: 综合对比雷达图 ==========
fig3, ax3 = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

categories = ['准确率', '处理速度', '响应时间', '实时性']
N = len(categories)

# 归一化数据（0-100分）
scores = {
    'faster-whisper': [51.48, 68, 75, 76],  # 准确率, 速度(越快分越高), 响应时间(越短分越高), RTF(越低分越高)
    'openai-whisper': [51.48, 12, 15, 13],
    'MiMo ASR': [75.87, 100, 100, 100]
}

angles = [n / float(N) * 2 * 3.14159 for n in range(N)]
angles += angles[:1]

for engine, values in scores.items():
    values_plot = values + values[:1]
    ax3.plot(angles, values_plot, 'o-', linewidth=2, label=engine)
    ax3.fill(angles, values_plot, alpha=0.1)

ax3.set_xticks(angles[:-1])
ax3.set_xticklabels(categories, fontsize=11)
ax3.set_ylim(0, 100)
ax3.set_title('三种引擎综合性能对比', fontsize=14, fontweight='bold', pad=20)
ax3.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)

plt.tight_layout()
fig3.savefig('chart_radar.png', dpi=300, bbox_inches='tight')
print("图表3已保存：chart_radar.png")

# ========== 打印数据摘要 ==========
print("\n" + "=" * 60)
print("测试数据摘要")
print("=" * 60)
print(f"""
┌─────────────────────┬─────────────┬─────────────┬─────────────┐
│       指标          │ faster-whisper│ MiMo ASR   │openai-whisper│
├─────────────────────┼─────────────┼─────────────┼─────────────┤
│ 识别准确率          │   {accuracy[0]:.1f}%    │   {accuracy[2]:.1f}%    │   {accuracy[1]:.1f}%    │
│ 处理速度 (x实时)    │   {speed_realtime[0]:.2f}x     │   {speed_realtime[2]:.2f}x     │   {speed_realtime[1]:.2f}x     │
│ 平均响应时间 (秒)   │   {response_time[0]:.2f}s    │   {response_time[2]:.2f}s     │   {response_time[1]:.2f}s    │
│ 实时因子 (RTF)      │    {rtf[0]:.2f}     │    {rtf[2]:.2f}      │    {rtf[1]:.2f}     │
│ 处理时间(秒/分钟)   │   {speed_per_minute[0]:.1f}s     │   {speed_per_minute[2]:.1f}s      │   {speed_per_minute[1]:.1f}s     │
└─────────────────────┴─────────────┴─────────────┴─────────────┘
""")

plt.show()
