#!/usr/bin/env python3
"""
测试脚本：验证DSPy优化器完整流程

运行步骤：
1. 解析评估报告
2. 构建训练集
3. 测试豆包API连通性
4. 运行BootstrapFewShot优化（如果数据准备完成）
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generators.evaluation_parser import EvaluationParser, analyze_reports
from generators.trainset_builder import quick_build_eval_trainset, EvaluationAwareBuilder


def test_evaluation_parser():
    """测试评估报告解析器"""
    print("="*60)
    print("步骤1: 测试评估报告解析器")
    print("="*60)
    
    parser = EvaluationParser()
    
    # 查找评估报告
    eval_dirs = [
        "input/现代农业创业项目路演_安康学院",
        "input/自动控制原理_山西大学",
        "外部评估报告"
    ]
    
    all_reports = []
    for eval_dir in eval_dirs:
        if os.path.exists(eval_dir):
            reports = parser.parse_directory(eval_dir)
            all_reports.extend(reports)
            print(f"✓ 从 {eval_dir} 解析了 {len(reports)} 个报告")
    
    if not all_reports:
        print("⚠ 未找到评估报告，跳过此步骤")
        return None
    
    # 分析统计
    stats = analyze_reports(all_reports)
    print(f"\n统计信息:")
    print(f"  总报告数: {stats['total_reports']}")
    print(f"  分数范围: {stats['score_stats']['min']:.1f} - {stats['score_stats']['max']:.1f}")
    print(f"  平均分: {stats['score_stats']['avg']:.1f}")
    print(f"  ≥85分: {stats['score_stats']['above_85']} 个")
    print(f"  ≥90分: {stats['score_stats']['above_90']} 个")
    
    return all_reports


def test_trainset_builder():
    """测试训练集构建器"""
    print("\n" + "="*60)
    print("步骤2: 测试训练集构建器")
    print("="*60)
    
    # 尝试构建训练集
    print("正在构建训练集...")
    output_path = quick_build_eval_trainset()
    
    if output_path and os.path.exists(output_path):
        print(f"✓ 训练集已保存: {output_path}")
        
        # 加载查看
        import json
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        meta = data.get('metadata', {})
        print(f"\n训练集统计:")
        print(f"  总样本: {meta.get('total_examples', 0)}")
        print(f"  黄金标准(≥90): {meta.get('golden_examples', 0)}")
        print(f"  及格(≥85): {meta.get('pass_examples', 0)}")
        
        if meta.get('score_distribution'):
            print(f"\n分数分布:")
            for range_name, count in meta['score_distribution'].items():
                if count > 0:
                    print(f"    {range_name}: {count} 个")
        
        return output_path
    else:
        print("⚠ 未能构建训练集（可能缺少数据）")
        return None


def test_api_connection():
    """测试豆包API连通性"""
    print("\n" + "="*60)
    print("步骤3: 测试豆包API连通性")
    print("="*60)
    
    try:
        import dspy
        from config import DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL
        
        if not DOUBAO_API_KEY:
            print("⚠ 未配置豆包API Key，跳过测试")
            return False
        
        print(f"API Key: {DOUBAO_API_KEY[:20]}...")
        print(f"Base URL: {DOUBAO_BASE_URL}")
        print(f"Model: {DOUBAO_MODEL}")
        
        # 创建LM实例
        print("\n正在创建LM实例...")
        lm = dspy.LM(
            model=f"openai/{DOUBAO_MODEL}",
            api_key=DOUBAO_API_KEY,
            api_base=DOUBAO_BASE_URL,
            max_tokens=100,
            temperature=0.7
        )
        
        # 测试简单调用
        print("正在测试API调用...")
        dspy.configure(lm=lm)
        
        # 简单测试
        test_module = dspy.Predict('input -> output')
        test_module.input = dspy.InputField(desc="输入")
        test_module.output = dspy.OutputField(desc="输出")
        
        # 实际调用
        result = test_module(input="你好")
        print(f"✓ API调用成功！")
        print(f"  响应: {result.output[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"✗ API测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_optimizer_readiness(trainset_path: str = None):
    """测试优化器就绪状态"""
    print("\n" + "="*60)
    print("步骤4: 优化器就绪检查")
    print("="*60)
    
    from generators.dspy_optimizer import run_optimize_dspy
    from generators.trainset_builder import load_trainset
    
    # 检查训练集
    if trainset_path and os.path.exists(trainset_path):
        print(f"✓ 训练集就绪: {trainset_path}")
        
        # 加载样本
        try:
            examples = load_trainset(trainset_path)
            if examples and len(examples) >= 4:
                print(f"✓ 样本数量充足: {len(examples)} 个")
                print(f"  可以运行BootstrapFewShot优化（需要≥4个样本）")
                return True
            else:
                print(f"⚠ 样本数量不足: {len(examples) if examples else 0} 个")
                print(f"  需要至少4个样本才能运行优化")
                return False
        except Exception as e:
            print(f"✗ 加载训练集失败: {e}")
            return False
    else:
        print("⚠ 训练集未就绪")
        print("  请先完成数据准备阶段")
        return False


def main():
    """主函数"""
    print("\n" + "="*60)
    print("DSPy优化器完整流程测试")
    print("="*60 + "\n")
    
    # 步骤1: 解析评估报告
    reports = test_evaluation_parser()
    
    # 步骤2: 构建训练集
    trainset_path = test_trainset_builder()
    
    # 步骤3: 测试API
    api_ready = test_api_connection()
    
    # 步骤4: 检查优化器就绪状态
    optimizer_ready = test_optimizer_readiness(trainset_path)
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    checks = {
        "评估报告解析": reports is not None and len(reports) > 0,
        "训练集构建": trainset_path is not None,
        "API连通性": api_ready,
        "优化器就绪": optimizer_ready
    }
    
    for check_name, status in checks.items():
        symbol = "✓" if status else "✗"
        print(f"{symbol} {check_name}: {'通过' if status else '未通过'}")
    
    if all(checks.values()):
        print("\n🎉 所有检查通过！可以运行优化器")
        print("\n下一步:")
        print("  python run_optimizer.py --trainset output/optimizer/trainset.json")
    else:
        print("\n⚠ 部分检查未通过，请根据提示修复")
        if not checks["评估报告解析"]:
            print("\n建议:")
            print("  1. 将评估报告放入 input/项目名/ 目录")
            print("  2. 或将评估报告放入项目 output 或 input 下对应目录")
            print("  3. 确保文件名包含 'evaluation' 或 'eval'")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
