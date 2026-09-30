# -*- coding: utf-8 -*-
"""鮀城漫游 回归测试脚本（2026-09-26）
用途：验证路线规划修复效果（时间升序 / 演出排期 / 景点介绍 / 主动联网）
用法：
  1. 先启动服务（停掉旧进程后）: & "D:\anaconda3\envs\qa_env\python.exe" main.py
  2. 再运行本脚本:              & "D:\anaconda3\envs\qa_env\python.exe" test_routes.py
"""
import requests

BASE = "http://127.0.0.1:8000"   # 若 main.py 用的不是 8000，改成实际端口

CASES = [
    ("亲子+英歌舞+冰沙（核心复现场景）", "我跟我两个儿子，想去看英歌舞，还想吃冰沙"),
    ("小公园一带亲子一日", "带两个儿子，安排小公园一带从早到晚的一天行程"),
    ("非遗体验馆问答（正常问答不报错）", "汕头有什么适合带孩子体验的非遗馆？"),
]


def main():
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        print(f"[1] 服务健康检查: HTTP {r.status_code} -> {r.json().get('status')}")
    except Exception as e:
        print(f"[1] 服务没起来或端口不对: {e}")
        print("    请先运行: & \"D:\\anaconda3\\envs\\qa_env\\python.exe\" main.py")
        return

    for i, (name, query) in enumerate(CASES, start=2):
        print(f"\n===== 用例{i}：{name} =====")
        print(f"提问：{query}")
        try:
            resp = requests.post(
                f"{BASE}/api/agent_route",
                json={"user_query": query, "conversation_id": None},
                timeout=180,
            )
            data = resp.json()
            if resp.status_code != 200:
                print(f"HTTP {resp.status_code}: {data}")
                continue
            print("---- 回答 ----")
            print(data.get("answer", data))
        except Exception as e:
            print(f"调用异常：{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
