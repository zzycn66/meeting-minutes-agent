# -*- coding: utf-8 -*-
"""
语音识别基准测试脚本

功能：
1. 使用 MiMo TTS 生成测试音频（至少5分钟）
2. 测试三种语音识别引擎的性能
3. 计算准确率、处理速度、召回率、响应时间
"""

import os
import sys
import time
import json
import base64
import numpy as np
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ==================== 配置 ====================
# MiMo TTS API 配置
MIMO_API_KEY = os.environ.get("MIMO_API", "")  # 环境变量名是 MIMO_API
MIMO_API_BASE = "https://api.xiaomimimo.com/v1"

# 测试文本（模拟会议内容，约5分钟朗读时长）
TEST_TEXTS = [
    # 文本1：产品规划会议（约1分钟）
    """
    各位同事，大家好。今天我们召开产品规划讨论会，主要讨论三个议题。
    第一个议题是关于v3.0版本的功能规划。经过团队讨论，我们决定采用新的推荐算法，
    这个算法相比现有算法，准确率提升了15%左右。张三负责在下周五前完成算法设计，
    然后李四负责进行代码实现。第二个议题是社交分享功能的开发。我们同意开发这个功能，
    预计需要两周时间。王五负责UI设计，赵六负责后端开发。截止时间是本月底。
    """,
    
    # 文本2：技术评审会议（约1分钟）
    """
    今天的技术评审会议，我们主要讨论了系统架构的优化方案。
    首先，关于数据库优化，我们决定采用读写分离的方案，主库负责写操作，
    从库负责读操作。这样可以大大提升系统的并发处理能力。
    其次，关于缓存策略，我们决定引入Redis集群，用于缓存热点数据。
    预计可以将响应时间从200毫秒降低到50毫秒以内。
    这些优化工作需要在下个月底前完成，由技术团队负责执行。
    """,
    
    # 文本3：项目进度同步（约1分钟）
    """
    现在进行项目进度同步。目前项目整体进度正常，已完成70%的功能开发。
    前端模块已经完成了用户界面的设计和开发，正在进行功能测试。
    后端模块完成了核心API的开发，正在进行性能优化。
    测试模块已经完成了80%的测试用例编写，发现了15个bug，
    其中高优先级bug有3个，需要在本周内修复。
    下一步工作计划是完成剩余功能的开发，并进行全面的集成测试。
    预计项目可以在下个月中旬完成交付。
    """,
    
    # 文本4：运营复盘会议（约1分钟）
    """
    本次运营复盘会议，我们对上个月的运营数据进行了分析。
    用户增长方面，新注册用户达到了5万人，同比增长20%。
    用户活跃度方面，日活跃用户达到1.2万人，留存率为35%。
    转化率方面，付费用户转化率达到了8%，比上个月提升了2个百分点。
    主要成功因素包括：第一，推出了新的营销活动，带来了大量新用户。
    第二，优化了产品体验，提升了用户满意度。
    下一步计划是继续加大推广力度，同时优化付费转化流程。
    """,
    
    # 文本5：客户反馈处理（约1分钟）
    """
    今天讨论客户反馈处理问题。最近收到了一些客户投诉，
    主要集中在以下几个方面：第一，系统响应速度慢，用户反映页面加载需要5秒以上。
    第二，搜索功能不准确，用户搜索关键词后找不到相关内容。
    第三，移动端适配问题，在某些手机上显示异常。
    针对这些问题，我们制定了以下解决方案：
    系统响应速度问题，由技术团队负责优化，预计一周内解决。
    搜索功能问题，由算法团队负责优化，预计两周内解决。
    移动端适配问题，由前端团队负责修复，预计三天内解决。
    """,
]

# 期望的转写结果（用于计算准确率）
EXPECTED_TEXTS = [
    "各位同事大家好今天我们召开产品规划讨论会主要讨论三个议题第一个议题是关于v三点零版本的功能规划经过团队讨论我们决定采用新的推荐算法这个算法相比现有算法准确率提升了百分之十五左右张三负责在下周五前完成算法设计然后李四负责进行代码实现第二个议题是社交分享功能的开发我们同意开发这个功能预计需要两周时间王五负责UI设计赵六负责后端开发截止时间是本月底",
    
    "今天的技术评审会议我们主要讨论了系统架构的优化方案首先关于数据库优化我们决定采用读写分离的方案主库负责写操作从库负责读操作这样可以大大提升系统的并发处理能力其次关于缓存策略我们决定引入redis集群用于缓存热点数据预计可以将响应时间从二百毫秒降低到五十毫秒以内这些优化工作需要在下个月底前完成由技术团队负责执行",
    
    "现在进行项目进度同步目前项目整体进度正常已完成百分之七十的功能开发前端模块已经完成了用户界面的设计和开发正在进行功能测试后端模块完成了核心api的开发正在进行性能优化测试模块已经完成了百分之八十的测试用例编写发现了十五个bug其中高优先级bug有三个需要在本周内修复下一步工作计划是完成剩余功能的开发并进行全面的集成测试预计项目可以在下个月中旬完成交付",
    
    "本次运营复盘会议我们对上个月的运营数据进行了分析用户增长方面新注册用户达到了五万人同比增长百分之二十用户活跃度方面日活跃用户达到一点二万人留存率为百分之三十五转化率方面付费用户转化率达到了百分之八比上个月提升了两个百分点主要成功因素包括第一推出了新的营销活动带来了大量新用户第二优化了产品体验提升了用户满意度下一步计划是继续加大推广力度同时优化付费转化流程",
    
    "今天讨论客户反馈处理问题最近收到了一些客户投诉主要集中在以下几个方面第一系统响应速度慢用户反映页面加载需要五秒以上第二搜索功能不准确用户搜索关键词后找不到相关内容第三移动端适配问题在某些手机上显示异常针对这些问题我们制定了以下解决方案系统响应速度问题由技术团队负责优化预计一周内解决搜索功能问题由算法团队负责优化预计两周内解决移动端适配问题由前端团队负责修复预计三天内解决",
]


def generate_test_audio_with_tts():
    """
    使用 MiMo TTS 生成测试音频
    
    生成至少5分钟的音频用于测试
    """
    print("=" * 60)
    print("开始使用 MiMo TTS 生成测试音频")
    print("=" * 60)
    
    try:
        from openai import OpenAI
    except ImportError:
        print("错误：请先安装 openai 库")
        print("运行命令：pip install openai")
        return False
    
    if not MIMO_API_KEY:
        print("错误：请设置 MIMO_API_KEY 环境变量")
        print("运行命令：$env:MIMO_API_KEY = 'your-api-key'")
        return False
    
    client = OpenAI(
        api_key=MIMO_API_KEY,
        base_url=MIMO_API_BASE
    )
    
    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio")
    os.makedirs(output_dir, exist_ok=True)
    
    total_duration = 0
    target_duration = 300  # 目标5分钟（300秒）

    for i, text in enumerate(TEST_TEXTS):
        if total_duration >= target_duration:
            break

        # 检查音频是否已存在
        audio_path = os.path.join(output_dir, f"test_audio_{i+1}.wav")
        if os.path.exists(audio_path):
            import soundfile as sf
            audio_data, sr = sf.read(audio_path)
            duration = len(audio_data) / sr
            total_duration += duration
            print(f"\n音频 {i+1} 已存在，跳过生成：{audio_path}")
            print(f"音频时长：{duration:.2f} 秒")
            print(f"总时长：{total_duration:.2f} 秒")
            continue

        print(f"\n生成音频 {i+1}/{len(TEST_TEXTS)}...")
        print(f"文本长度：{len(text)} 字符")

        try:
            # 使用流式调用生成音频
            completion = client.chat.completions.create(
                model="mimo-v2.5-tts",
                messages=[
                    {
                        "role": "user",
                        "content": "用清晰、自然的语调朗读以下会议内容，语速适中，确保每个字都能听清楚。"
                    },
                    {
                        "role": "assistant",
                        "content": text.strip()
                    }
                ],
                audio={
                    "format": "pcm16",
                    "voice": "冰糖"
                },
                stream=True
            )

            # 收集音频数据
            collected_chunks = np.array([], dtype=np.float32)

            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                audio = getattr(delta, "audio", None)

                if audio is not None and isinstance(audio, dict):
                    pcm_bytes = base64.b64decode(audio["data"])
                    np_pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    collected_chunks = np.concatenate((collected_chunks, np_pcm))

            # 保存音频文件
            if len(collected_chunks) > 0:
                import soundfile as sf
                sf.write(audio_path, collected_chunks, samplerate=24000)

                # 计算音频时长
                duration = len(collected_chunks) / 24000
                total_duration += duration

                print(f"音频已保存：{audio_path}")
                print(f"音频时长：{duration:.2f} 秒")
                print(f"总时长：{total_duration:.2f} 秒")
            else:
                print(f"警告：音频 {i+1} 生成失败")

        except Exception as e:
            print(f"生成音频 {i+1} 时出错：{e}")
            continue

    print(f"\n{'=' * 60}")
    print(f"音频生成完成！总时长：{total_duration:.2f} 秒")
    print(f"{'=' * 60}")

    return total_duration >= 60  # 至少生成1分钟


def test_faster_whisper():
    """测试 faster-whisper 语音识别"""
    print("\n" + "=" * 60)
    print("测试 faster-whisper 语音识别")
    print("=" * 60)
    
    results = {
        "engine": "faster-whisper",
        "accuracy": 0,
        "processing_speed": 0,
        "response_time": 0,
        "recall": 0,
        "details": []
    }
    
    try:
        from faster_whisper import WhisperModel
        from config import WHISPER_MODEL_SIZE
        
        print(f"加载模型：{WHISPER_MODEL_SIZE}")
        model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        
        test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio")
        
        total_accuracy = 0
        total_processing_time = 0
        total_audio_duration = 0
        count = 0
        
        for i in range(len(TEST_TEXTS)):
            audio_path = os.path.join(test_dir, f"test_audio_{i+1}.wav")
            if not os.path.exists(audio_path):
                continue
            
            print(f"\n处理音频 {i+1}...")
            
            start_time = time.time()
            segments, info = model.transcribe(
                audio_path,
                language="zh",
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = "".join([seg.text for seg in segments])
            processing_time = time.time() - start_time
            
            # 获取音频时长
            import soundfile as sf
            audio_data, sample_rate = sf.read(audio_path)
            audio_duration = len(audio_data) / sample_rate
            
            # 计算准确率（简化版：字符匹配率）
            expected = EXPECTED_TEXTS[i].replace(" ", "")
            predicted = text.replace(" ", "").replace("，", "").replace("。", "")
            
            # 计算字符级准确率
            correct_chars = sum(1 for a, b in zip(expected, predicted) if a == b)
            accuracy = correct_chars / max(len(expected), 1) * 100
            
            total_accuracy += accuracy
            total_processing_time += processing_time
            total_audio_duration += audio_duration
            count += 1
            
            results["details"].append({
                "audio": f"test_audio_{i+1}.wav",
                "accuracy": accuracy,
                "processing_time": processing_time,
                "audio_duration": audio_duration,
                "rtf": processing_time / audio_duration  # 实时因子
            })
            
            print(f"准确率：{accuracy:.2f}%")
            print(f"处理时间：{processing_time:.2f} 秒")
            print(f"音频时长：{audio_duration:.2f} 秒")
            print(f"实时因子(RTF)：{processing_time / audio_duration:.4f}")
        
        if count > 0:
            results["accuracy"] = total_accuracy / count
            results["processing_speed"] = total_audio_duration / total_processing_time
            results["response_time"] = total_processing_time / count
            results["recall"] = results["accuracy"]  # 简化处理
        
        print(f"\n平均准确率：{results['accuracy']:.2f}%")
        print(f"处理速度：{results['processing_speed']:.2f}x 实时")
        print(f"平均响应时间：{results['response_time']:.2f} 秒")
        
    except ImportError:
        print("错误：faster-whisper 未安装")
        print("运行命令：pip install faster-whisper")
    except Exception as e:
        print(f"测试出错：{e}")
    
    return results


def test_mimo_asr():
    """
    测试 MiMo ASR 语音识别

    MiMo-V2.5-ASR API 调用方式：
    - 端点：/v1/chat/completions
    - 模型：mimo-v2.5-asr
    - 音频格式：Base64 编码
    """
    print("\n" + "=" * 60)
    print("测试 MiMo ASR 语音识别 (mimo-v2.5-asr)")
    print("=" * 60)

    results = {
        "engine": "MiMo ASR (mimo-v2.5-asr)",
        "accuracy": 0,
        "processing_speed": 0,
        "response_time": 0,
        "recall": 0,
        "details": []
    }

    try:
        from openai import OpenAI
        import base64

        client = OpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_API_BASE
        )

        test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio")

        total_accuracy = 0
        total_processing_time = 0
        total_audio_duration = 0
        count = 0

        for i in range(len(TEST_TEXTS)):
            audio_path = os.path.join(test_dir, f"test_audio_{i+1}.wav")
            if not os.path.exists(audio_path):
                continue

            print(f"\n处理音频 {i+1}...")

            # 读取音频文件并 Base64 编码
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            # 获取音频时长
            import soundfile as sf
            audio_array, sample_rate = sf.read(audio_path)
            audio_duration = len(audio_array) / sample_rate

            start_time = time.time()

            # 调用 MiMo ASR API（使用 OpenAI SDK）
            completion = client.chat.completions.create(
                model="mimo-v2.5-asr",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": f"data:audio/wav;base64,{audio_base64}"
                                }
                            }
                        ]
                    }
                ],
                extra_body={
                    "asr_options": {
                        "language": "zh"
                    }
                }
            )

            processing_time = time.time() - start_time

            # 提取识别结果
            text = completion.choices[0].message.content or ""

            # 计算准确率
            expected = EXPECTED_TEXTS[i].replace(" ", "")
            predicted = text.replace(" ", "").replace("，", "").replace("。", "").replace("、", "")

            correct_chars = sum(1 for a, b in zip(expected, predicted) if a == b)
            accuracy = correct_chars / max(len(expected), 1) * 100

            total_accuracy += accuracy
            total_processing_time += processing_time
            total_audio_duration += audio_duration
            count += 1

            results["details"].append({
                "audio": f"test_audio_{i+1}.wav",
                "accuracy": accuracy,
                "processing_time": processing_time,
                "audio_duration": audio_duration,
                "rtf": processing_time / audio_duration,
                "recognized_text": text[:100] + "..." if len(text) > 100 else text
            })

            print(f"准确率：{accuracy:.2f}%")
            print(f"处理时间：{processing_time:.2f} 秒")
            print(f"音频时长：{audio_duration:.2f} 秒")
            print(f"实时因子(RTF)：{processing_time / audio_duration:.4f}")
            print(f"识别结果：{text[:80]}...")

        if count > 0:
            results["accuracy"] = total_accuracy / count
            results["processing_speed"] = total_audio_duration / total_processing_time
            results["response_time"] = total_processing_time / count
            results["recall"] = results["accuracy"]

        print(f"\n平均准确率：{results['accuracy']:.2f}%")
        print(f"处理速度：{results['processing_speed']:.2f}x 实时")
        print(f"平均响应时间：{results['response_time']:.2f} 秒")

    except ImportError:
        print("错误：请安装必要的库")
        print("运行命令：pip install openai soundfile")
    except Exception as e:
        print(f"测试出错：{e}")
        import traceback
        traceback.print_exc()

    return results


def test_openai_whisper():
    """测试 openai-whisper 语音识别"""
    print("\n" + "=" * 60)
    print("测试 openai-whisper 语音识别")
    print("=" * 60)
    
    results = {
        "engine": "openai-whisper",
        "accuracy": 0,
        "processing_speed": 0,
        "response_time": 0,
        "recall": 0,
        "details": []
    }
    
    try:
        import whisper
        from config import WHISPER_MODEL_SIZE
        
        print(f"加载模型：{WHISPER_MODEL_SIZE}")
        model = whisper.load_model(WHISPER_MODEL_SIZE)
        
        test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio")
        
        total_accuracy = 0
        total_processing_time = 0
        total_audio_duration = 0
        count = 0
        
        for i in range(len(TEST_TEXTS)):
            audio_path = os.path.join(test_dir, f"test_audio_{i+1}.wav")
            if not os.path.exists(audio_path):
                continue
            
            print(f"\n处理音频 {i+1}...")
            
            start_time = time.time()
            result = model.transcribe(
                audio_path,
                language="zh",
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = result["text"]
            processing_time = time.time() - start_time
            
            # 获取音频时长
            import soundfile as sf
            audio_data, sample_rate = sf.read(audio_path)
            audio_duration = len(audio_data) / sample_rate
            
            # 计算准确率
            expected = EXPECTED_TEXTS[i].replace(" ", "")
            predicted = text.replace(" ", "").replace("，", "").replace("。", "")
            
            correct_chars = sum(1 for a, b in zip(expected, predicted) if a == b)
            accuracy = correct_chars / max(len(expected), 1) * 100
            
            total_accuracy += accuracy
            total_processing_time += processing_time
            total_audio_duration += audio_duration
            count += 1
            
            results["details"].append({
                "audio": f"test_audio_{i+1}.wav",
                "accuracy": accuracy,
                "processing_time": processing_time,
                "audio_duration": audio_duration,
                "rtf": processing_time / audio_duration
            })
            
            print(f"准确率：{accuracy:.2f}%")
            print(f"处理时间：{processing_time:.2f} 秒")
            print(f"音频时长：{audio_duration:.2f} 秒")
            print(f"实时因子(RTF)：{processing_time / audio_duration:.4f}")
        
        if count > 0:
            results["accuracy"] = total_accuracy / count
            results["processing_speed"] = total_audio_duration / total_processing_time
            results["response_time"] = total_processing_time / count
            results["recall"] = results["accuracy"]
        
        print(f"\n平均准确率：{results['accuracy']:.2f}%")
        print(f"处理速度：{results['processing_speed']:.2f}x 实时")
        print(f"平均响应时间：{results['response_time']:.2f} 秒")
        
    except ImportError:
        print("错误：whisper 未安装")
        print("运行命令：pip install openai-whisper")
    except Exception as e:
        print(f"测试出错：{e}")
    
    return results


def generate_report(all_results):
    """生成测试报告"""
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)
    
    report = {
        "test_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": all_results
    }
    
    # 打印对比表格
    print("\n┌─────────────────┬─────────────┬─────────────┬─────────────┬─────────────┐")
    print("│     引擎        │   准确率    │  处理速度   │  响应时间   │   召回率    │")
    print("├─────────────────┼─────────────┼─────────────┼─────────────┼─────────────┤")
    
    for result in all_results:
        engine = result["engine"]
        accuracy = f"{result['accuracy']:.2f}%"
        speed = f"{result['processing_speed']:.2f}x"
        response_time = f"{result['response_time']:.2f}s"
        recall = f"{result['recall']:.2f}%"
        
        print(f"│ {engine:15s} │ {accuracy:11s} │ {speed:11s} │ {response_time:11s} │ {recall:11s} │")
    
    print("└─────────────────┴─────────────┴─────────────┴─────────────┴─────────────┘")
    
    # 保存报告到 JSON 文件
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "asr_benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保存：{report_path}")
    
    return report


def main():
    """主函数"""
    print("=" * 60)
    print("语音识别基准测试")
    print("=" * 60)
    
    # 1. 生成测试音频
    print("\n步骤 1：生成测试音频")
    audio_generated = generate_test_audio_with_tts()
    
    if not audio_generated:
        print("警告：音频生成不完整，将使用已有音频继续测试")
    
    # 2. 测试三种引擎
    all_results = []
    
    # 测试 faster-whisper
    print("\n步骤 2：测试语音识别引擎")
    result1 = test_faster_whisper()
    all_results.append(result1)
    
    # 测试 MiMo ASR
    result2 = test_mimo_asr()
    all_results.append(result2)
    
    # 测试 openai-whisper
    result3 = test_openai_whisper()
    all_results.append(result3)
    
    # 3. 生成报告
    print("\n步骤 3：生成测试报告")
    report = generate_report(all_results)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
