import subprocess
import time
import os

# Danh sách exe cần giám sát
CRAWLERS = [
    r"C:\crawler\crawler_fb_1.exe",
    r"C:\crawler\crawler_fb_2.exe",
    r"C:\crawler\crawler_fb_3.exe"
]

# Lưu tiến trình đã start
processes = {}

def start_crawler(path):
    """Khởi động 1 crawler.exe"""
    print(f"[START] {path}")
    return subprocess.Popen([path], stdout=open(path+".log", "a"), stderr=subprocess.STDOUT)
    # return subprocess.Popen(path, creationflags=subprocess.CREATE_NEW_CONSOLE)

def monitor():
    """Giám sát và restart crawler nếu chết"""
    while True:
        for path in CRAWLERS:
            proc = processes.get(path)

            # Nếu chưa chạy hoặc đã chết → restart
            if proc is None or proc.poll() is not None:
                processes[path] = start_crawler(path)

        time.sleep(5)  # mỗi 5 giây kiểm tra 1 lần

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n[STOP] Đang tắt toàn bộ crawler...")
        for proc in processes.values():
            if proc and proc.poll() is None:
                proc.terminate()
