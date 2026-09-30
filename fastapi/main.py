import os
import subprocess
import sys
from typing import List

def run_servers():
    """同时运行多个FastAPI服务"""
    servers = [
        {
            "name": "route-generator",
            "module": "route_generator",
            "port": 8000
        },
        {
            "name": "qiaoxiang_story",
            "module": "qiaoxiang_story",
            "port": 8001
        },
        {
            "name": "tts",
            "module": "tts",
            "port": 8002
        }
    ]

    processes = []

    try:
        for server in servers:
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                f"{server['module']}:app",
                "--host", "0.0.0.0",
                "--port", str(server["port"])
            ]
            
            print(f"启动 {server['name']} 服务: {' '.join(cmd)}")
            process = subprocess.Popen(cmd)
            processes.append(process)
        
        # 等待所有进程完成（通常不会自然完成，直到手动中断）
        for process in processes:
            process.wait()
            
    except KeyboardInterrupt:
        print("\n检测到中断信号，正在关闭所有服务...")
        for process in processes:
            process.terminate()
        
        # 等待所有进程终止
        for process in processes:
            process.wait()
            
        print("所有服务已关闭")

if __name__ == "__main__":
    run_servers()    
