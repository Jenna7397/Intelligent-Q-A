# -*- coding: utf-8 -*-
"""
侨乡知识库 RAG 检索层评测脚本（混合检索版，候选池敏感性实验）
用法: python eval_rag.py
原理: 对每个「问题 → 期望实体」测试对调用 search_kb（向量 + BM25 + RRF 融合），
      检查期望实体是否出现在前 k 名检索结果的 name 或 text 中，
      统计 HitRate@1/3/5 与 MRR。

输出:
  - 候选池大小 N ∈ {5, 10, 20, 50} 的指标对比表（用数据决定最终候选池）
  - 最优 N 下的失败明细（未召回 / 排位靠后），便于定位 metadata/切分问题
"""
import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_retriever import search_kb, extract_remittance_short

TOP_K = 5

# ===== 手工测试集（贴近真实问法）=====
TESTS = [
    # —— 人物 ——
    ("谢易初是做什么的", "谢易初"),
    ("李嘉诚为家乡做了什么", "李嘉诚"),
    ("陈弼臣有哪些成就", "陈弼臣"),
    ("林百欣是谁", "林百欣"),
    ("吴南生做了什么", "吴南生"),
    ("正大集团的创始人是谁", "谢易初"),
    ("哪位侨胞捐建了汕头大学", "李嘉诚"),
    ("胡文虎与永安堂有什么关系", "胡文虎"),
    ("陈伟南在潮汕做了哪些慈善", "陈伟南"),
    ("林义顺在新加坡的贡献", "林义顺"),
    ("蚁美厚是做什么的", "蚁美厚"),
    ("张煜南修了什么铁路", "张煜南"),
    ("陈旭年在南洋的主要事迹", "陈旭年"),
    ("黄敏如从事什么行业", "黄敏如"),
    ("林百欣创办了什么集团", "林百欣"),
    ("谢国民与正大集团的关系", "谢易初"),
    # —— 侨宅 ——
    ("东观楼是谁建的", "东观楼"),
    ("兰香楼的主人是谁", "兰香楼"),
    ("泰华里侨宅在哪里", "泰华里"),
    ("陈慈黉故居的建筑面积多大", "陈慈黉故居"),
    ("从熙公祠有什么特色", "从熙公祠"),
    ("小可楼为什么叫小可楼", "小可楼"),
    ("明安里在哪里", "明安里"),
    ("兄弟楼位于哪个镇", "兄弟楼"),
    ("大夫第的主人是谁", "大夫第"),
    ("南盛里侨宅在哪里", "南盛里"),
    # —— 村落 / 侨批 ——
    ("东溪村在哪里", "东溪村"),
    ("葛洲村有什么历史", "葛洲村"),
    ("侨批是什么", "侨批"),
    ("抗战时期的侨批有什么意义", "侨批"),
]

# ===== 自动生成测试集（实体 × 问题模板）=====
CSV_SOURCES = [
    ("persons.csv", "人物", "name", ["{x}是谁", "{x}做了什么事", "{x}有什么成就"]),
    ("hometowns.csv", "村落", "name", ["{x}在哪里", "{x}有什么特色"]),
    ("houses.csv", "侨宅", "place", ["{x}在哪里", "{x}的主人是谁"]),
    ("remittances.csv", "侨批", "name", ["{x}是什么", "介绍一下{x}"]),
]


def build_auto_tests() -> list:
    """从 CSV 抽取全部实体，按模板生成测试对"""
    csv_dir = Path(__file__).resolve().parent.parent / "kb_data" / "qiao"
    tests = []
    for filename, _, name_col, templates in CSV_SOURCES:
        path = csv_dir / filename
        if not path.exists():
            print(f"[跳过] {path} 不存在")
            continue
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get(name_col) or "").strip()
                if not name:
                    continue
                # 侨批：用短实体名生成真实问法（长标题不适合做查询），提取不出则跳过
                if filename == "remittances.csv":
                    name = extract_remittance_short(name)
                    if not name:
                        continue
                for tpl in templates:
                    tests.append((tpl.format(x=name), name))
    return tests


def hit_rank(query: str, expect: str, candidates: int) -> int:
    """返回期望实体在检索结果中的排位；未召回返回 0。"""
    results = search_kb(query, TOP_K, candidates=candidates)
    if not results:
        return 0
    for i, r in enumerate(results, 1):
        if expect in r.get("name", "") or expect in r.get("text", "")[:300]:
            return i
    return 0


def evaluate(tests: list, candidates: int):
    """跑一组评测，返回 (hit, mrr, failures)"""
    hit = {1: 0, 3: 0, 5: 0}
    reciprocal = []
    failures = []
    for query, expect in tests:
        rank = hit_rank(query, expect, candidates)
        for k in hit:
            if 0 < rank <= k:
                hit[k] += 1
        reciprocal.append(1.0 / rank if rank else 0.0)
        if rank == 0 or rank > 1:
            failures.append((query, expect, rank))
    mrr = sum(reciprocal) / len(reciprocal)
    return hit, mrr, failures


def main() -> None:
    auto = build_auto_tests()
    tests = TESTS + auto
    n_tests = len(tests)
    print(f"评测集: {n_tests} 条（手工 {len(TESTS)} + 自动 {len(auto)}）| top_k = {TOP_K}")
    print(f"混合检索: 向量 + BM25 + RRF(k={__import__('kb_retriever').RRF_K})\n")

    # 候选池经 5/10/20/50 敏感性实验验证，用户拍板默认 20（HitRate@5 最高）
    cands = [20]
    results = {}
    print(f"{'候选池N':>8} | {'HitRate@1':>9} | {'HitRate@3':>9} | {'HitRate@5':>9} | {'MRR':>6} | 失败条数")
    print("-" * 70)
    for n in cands:
        hit, mrr, failures = evaluate(tests, n)
        results[n] = (hit, mrr, failures)
        print(f"{n:>8} | {hit[1]/n_tests:>9.3f} | {hit[3]/n_tests:>9.3f} | {hit[5]/n_tests:>9.3f} | {mrr:>6.3f} | {len(failures)}")

    # 用 MRR 最高（综合排序质量）作为最优 N，@5 次之
    best = max(cands, key=lambda n: (results[n][1], results[n][0][5]))
    hit, mrr, failures = results[best]
    print("-" * 70)
    print(f"最优候选池 N = {best}")

    print("\n" + "=" * 52)
    print(f"最优配置指标: HitRate@1={hit[1]/n_tests:.3f} | @3={hit[3]/n_tests:.3f} | "
          f"@5={hit[5]/n_tests:.3f} | MRR={mrr:.3f} | 失败 {len(failures)}/{n_tests}")
    print("=" * 52)

    if failures:
        print(f"\n失败/排位靠后明细（{len(failures)} 条，仅列前 60）：")
        for q, e, r in failures[:60]:
            print(f"  rank={r if r else '未召回'} | {q}  -> 期望: {e}")
        if len(failures) > 60:
            print(f"  ... 其余 {len(failures) - 60} 条略")
    else:
        print("\n全部测试对均在 rank=1 召回。")

    print("\n解读: HitRate@5 >= 0.8 视为检索健康;")
    print("      N 敏感性实验用于确定混合检索候选池大小（trade-off：覆盖 vs 噪声）。")


if __name__ == "__main__":
    main()
