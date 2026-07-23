# -*- coding: utf-8 -*-
"""
NLP 信息提取引擎基准测试

测试三个引擎：
1. 关键词匹配引擎（规则匹配）
2. DeepSeek AI 引擎（云端 API）
3. Qwen3 本地引擎（本地推理）

测试指标：
1. 关键信息召回率
2. 响应时间
"""

import os
import sys
import time
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ==================== 测试数据 ====================
TEST_CASES = [
    {
        "id": 1,
        "text": """
        各位同事，大家好。今天我们召开产品规划讨论会，主要讨论三个议题。
        第一个议题是关于v3.0版本的功能规划。经过团队讨论，我们决定采用新的推荐算法，
        这个算法相比现有算法，准确率提升了15%左右。张三负责在下周五前完成算法设计，
        然后李四负责进行代码实现。第二个议题是社交分享功能的开发。我们同意开发这个功能，
        预计需要两周时间。王五负责UI设计，赵六负责后端开发。截止时间是本月底。
        遗留问题：服务器扩容方案需要进一步评估。
        """,
        "expected": {
            "topic": "产品规划讨论会",
            "decisions": ["采用新的推荐算法", "开发社交分享功能"],
            "action_items": [
                {"content": "完成算法设计", "person": "张三", "deadline": "下周五"},
                {"content": "进行代码实现", "person": "李四", "deadline": None},
                {"content": "UI设计", "person": "王五", "deadline": "本月底"},
                {"content": "后端开发", "person": "赵六", "deadline": "本月底"},
            ],
            "participants": ["张三", "李四", "王五", "赵六"],
            "issues": ["服务器扩容方案需要进一步评估"],
        }
    },
    {
        "id": 2,
        "text": """
        今天的技术评审会议，我们主要讨论了系统架构的优化方案。
        首先，关于数据库优化，我们决定采用读写分离的方案，主库负责写操作，
        从库负责读操作。这样可以大大提升系统的并发处理能力。
        其次，关于缓存策略，我们决定引入Redis集群，用于缓存热点数据。
        预计可以将响应时间从200毫秒降低到50毫秒以内。
        这些优化工作需要在下个月底前完成，由技术团队负责执行。
        遗留问题：缓存一致性方案需要进一步讨论。
        """,
        "expected": {
            "topic": "技术评审会议",
            "decisions": ["采用读写分离方案", "引入Redis集群"],
            "action_items": [
                {"content": "执行优化工作", "person": "技术团队", "deadline": "下个月底"},
            ],
            "participants": ["技术团队"],
            "issues": ["缓存一致性方案需要进一步讨论"],
        }
    },
    {
        "id": 3,
        "text": """
        现在进行项目进度同步。目前项目整体进度正常，已完成70%的功能开发。
        前端模块已经完成了用户界面的设计和开发，正在进行功能测试。
        后端模块完成了核心API的开发，正在进行性能优化。
        测试模块已经完成了80%的测试用例编写，发现了15个bug，
        其中高优先级bug有3个，需要在本周内修复。
        下一步工作计划是完成剩余功能的开发，并进行全面的集成测试。
        预计项目可以在下个月中旬完成交付。
        遗留问题：性能测试环境需要搭建。
        """,
        "expected": {
            "topic": "项目进度同步",
            "decisions": [],
            "action_items": [
                {"content": "修复高优先级bug", "person": "", "deadline": "本周内"},
                {"content": "完成剩余功能开发", "person": "", "deadline": None},
                {"content": "进行全面的集成测试", "person": "", "deadline": None},
            ],
            "participants": [],
            "issues": ["性能测试环境需要搭建"],
        }
    },
]


def test_keyword_engine():
    """测试关键词匹配引擎"""
    print("\n" + "=" * 60)
    print("测试关键词匹配引擎")
    print("=" * 60)

    results = {
        "engine": "关键词匹配引擎",
        "recall": 0,
        "response_time": 0,
        "details": []
    }

    try:
        from app.services.nlp_service import nlp_processor

        total_recall = 0
        total_time = 0
        count = 0

        for case in TEST_CASES:
            print(f"\n测试用例 {case['id']}...")

            start_time = time.time()
            result = nlp_processor.process(case["text"])
            processing_time = time.time() - start_time

            # 计算召回率
            expected = case["expected"]
            recalled_items = 0
            total_items = 0

            # 检查决策
            for exp_decision in expected["decisions"]:
                total_items += 1
                if any(exp_decision in d for d in result.get("key_decisions", "")):
                    recalled_items += 1

            # 检查行动项
            for exp_action in expected["action_items"]:
                total_items += 1
                if any(exp_action["content"] in a.get("content", "") for a in result.get("action_items", [])):
                    recalled_items += 1

            # 检查问题
            for exp_issue in expected["issues"]:
                total_items += 1
                if any(exp_issue in i for i in result.get("unresolved_issues", "")):
                    recalled_items += 1

            recall = recalled_items / max(total_items, 1) * 100
            total_recall += recall
            total_time += processing_time
            count += 1

            results["details"].append({
                "case_id": case["id"],
                "recall": recall,
                "processing_time": processing_time,
                "recalled_items": recalled_items,
                "total_items": total_items
            })

            print(f"召回率：{recall:.1f}% ({recalled_items}/{total_items})")
            print(f"处理时间：{processing_time:.3f} 秒")

        if count > 0:
            results["recall"] = total_recall / count
            results["response_time"] = total_time / count

        print(f"\n平均召回率：{results['recall']:.1f}%")
        print(f"平均响应时间：{results['response_time']:.3f} 秒")

    except Exception as e:
        print(f"测试出错：{e}")
        import traceback
        traceback.print_exc()

    return results


def test_deepseek_engine():
    """测试 DeepSeek AI 引擎"""
    print("\n" + "=" * 60)
    print("测试 DeepSeek AI 引擎")
    print("=" * 60)

    results = {
        "engine": "DeepSeek AI 引擎",
        "recall": 0,
        "response_time": 0,
        "details": []
    }

    try:
        from app.services.nlp_service import deepseek_nlp_processor

        if not deepseek_nlp_processor.api_key or deepseek_nlp_processor.api_key == "your-deepseek-api-key":
            print("警告：DeepSeek API Key 未配置，跳过测试")
            return results

        total_recall = 0
        total_time = 0
        count = 0

        for case in TEST_CASES:
            print(f"\n测试用例 {case['id']}...")

            start_time = time.time()
            result = deepseek_nlp_processor.process(case["text"])
            processing_time = time.time() - start_time

            # 计算召回率
            expected = case["expected"]
            recalled_items = 0
            total_items = 0

            # 检查决策
            for exp_decision in expected["decisions"]:
                total_items += 1
                if any(exp_decision in d for d in result.get("key_decisions", "")):
                    recalled_items += 1

            # 检查行动项
            for exp_action in expected["action_items"]:
                total_items += 1
                if any(exp_action["content"] in a.get("content", "") for a in result.get("action_items", [])):
                    recalled_items += 1

            # 检查问题
            for exp_issue in expected["issues"]:
                total_items += 1
                if any(exp_issue in i for i in result.get("unresolved_issues", "")):
                    recalled_items += 1

            recall = recalled_items / max(total_items, 1) * 100
            total_recall += recall
            total_time += processing_time
            count += 1

            results["details"].append({
                "case_id": case["id"],
                "recall": recall,
                "processing_time": processing_time,
                "recalled_items": recalled_items,
                "total_items": total_items
            })

            print(f"召回率：{recall:.1f}% ({recalled_items}/{total_items})")
            print(f"处理时间：{processing_time:.3f} 秒")

        if count > 0:
            results["recall"] = total_recall / count
            results["response_time"] = total_time / count

        print(f"\n平均召回率：{results['recall']:.1f}%")
        print(f"平均响应时间：{results['response_time']:.3f} 秒")

    except Exception as e:
        print(f"测试出错：{e}")
        import traceback
        traceback.print_exc()

    return results


def test_qwen3_engine():
    """测试 Qwen3 本地引擎"""
    print("\n" + "=" * 60)
    print("测试 Qwen3 本地引擎")
    print("=" * 60)

    results = {
        "engine": "Qwen3 本地引擎",
        "recall": 0,
        "response_time": 0,
        "details": []
    }

    try:
        from app.services.nlp_service import local_qwen_processor

        total_recall = 0
        total_time = 0
        count = 0

        for case in TEST_CASES:
            print(f"\n测试用例 {case['id']}...")

            start_time = time.time()
            result = local_qwen_processor.process(case["text"], max_tokens=512)
            processing_time = time.time() - start_time

            # 计算召回率
            expected = case["expected"]
            recalled_items = 0
            total_items = 0

            # 检查决策
            for exp_decision in expected["decisions"]:
                total_items += 1
                kd = result.get("key_decisions", "")
                if isinstance(kd, list):
                    kd_str = "\n".join(kd)
                else:
                    kd_str = str(kd)
                if exp_decision in kd_str:
                    recalled_items += 1

            # 检查行动项
            for exp_action in expected["action_items"]:
                total_items += 1
                if any(exp_action["content"] in a.get("content", "") for a in result.get("action_items", [])):
                    recalled_items += 1

            # 检查问题
            for exp_issue in expected["issues"]:
                total_items += 1
                ui = result.get("unresolved_issues", "")
                if isinstance(ui, list):
                    ui_str = "\n".join(ui)
                else:
                    ui_str = str(ui)
                if exp_issue in ui_str:
                    recalled_items += 1

            recall = recalled_items / max(total_items, 1) * 100
            total_recall += recall
            total_time += processing_time
            count += 1

            results["details"].append({
                "case_id": case["id"],
                "recall": recall,
                "processing_time": processing_time,
                "recalled_items": recalled_items,
                "total_items": total_items
            })

            print(f"召回率：{recall:.1f}% ({recalled_items}/{total_items})")
            print(f"处理时间：{processing_time:.3f} 秒")

        if count > 0:
            results["recall"] = total_recall / count
            results["response_time"] = total_time / count

        print(f"\n平均召回率：{results['recall']:.1f}%")
        print(f"平均响应时间：{results['response_time']:.3f} 秒")

    except Exception as e:
        print(f"测试出错：{e}")
        import traceback
        traceback.print_exc()

    return results


def generate_report(all_results):
    """生成测试报告"""
    print("\n" + "=" * 60)
    print("NLP 引擎测试报告")
    print("=" * 60)

    # 打印对比表格
    print("\n┌─────────────────────┬─────────────┬─────────────┬─────────────┐")
    print("│       指标          │ 关键词匹配  │  DeepSeek   │   Qwen3     │")
    print("├─────────────────────┼─────────────┼─────────────┼─────────────┤")

    for result in all_results:
        engine = result["engine"]
        recall = f"{result['recall']:.1f}%"
        response_time = f"{result['response_time']:.3f}s"

        if "关键词" in engine:
            print(f"│ 关键信息召回率      │ {recall:11s} │      -      │      -      │")
        elif "DeepSeek" in engine:
            print(f"│ 关键信息召回率      │      -      │ {recall:11s} │      -      │")
        elif "Qwen3" in engine:
            print(f"│ 关键信息召回率      │      -      │      -      │ {recall:11s} │")

    print("├─────────────────────┼─────────────┼─────────────┼─────────────┤")

    for result in all_results:
        engine = result["engine"]
        response_time = f"{result['response_time']:.3f}s"

        if "关键词" in engine:
            print(f"│ 平均响应时间        │ {response_time:11s} │      -      │      -      │")
        elif "DeepSeek" in engine:
            print(f"│ 平均响应时间        │      -      │ {response_time:11s} │      -      │")
        elif "Qwen3" in engine:
            print(f"│ 平均响应时间        │      -      │      -      │ {response_time:11s} │")

    print("└─────────────────────┴─────────────┴─────────────┴─────────────┘")

    # 保存报告到 JSON 文件
    report = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_cases": len(TEST_CASES),
        "results": all_results
    }

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nlp_benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存：{report_path}")

    return report


def main():
    """主函数"""
    print("=" * 60)
    print("NLP 信息提取引擎基准测试")
    print("=" * 60)
    print(f"测试用例数：{len(TEST_CASES)}")

    all_results = []

    # 测试关键词匹配引擎
    result1 = test_keyword_engine()
    all_results.append(result1)

    # 测试 DeepSeek AI 引擎
    result2 = test_deepseek_engine()
    all_results.append(result2)

    # 测试 Qwen3 本地引擎
    result3 = test_qwen3_engine()
    all_results.append(result3)

    # 生成报告
    generate_report(all_results)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
