import subprocess
import time
import datetime
import logging

# ----------------- CẤU HÌNH -----------------
CRAWLERS = [
    r"C:\CrawlerEXE\yt_tiktok\crawler_yt\dist\gg_api.exe",
    r"C:\CrawlerEXE\fb\main_bot_schedule.exe"
]

# Giờ reset hằng ngày (ví dụ 23:30 tối)
RESET_HOUR = 23
RESET_MINUTE = 30
RESET_FLAG = False

LOG_FILE = "watchdog.log"
# --------------------------------------------

# Cấu hình logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

processes = {}
last_reset_date = None  # ngày gần nhất đã reset

def start_crawler(path):
    """Khởi động 1 crawler.exe"""
    logging.info(f"[START] {path}")
    return subprocess.Popen(path, creationflags=subprocess.CREATE_NEW_CONSOLE)

def stop_all():
    """Tắt toàn bộ crawler"""
    for proc in processes.values():
        if proc and proc.poll() is None:
            logging.info(f"[STOP] PID {proc.pid}")
            proc.terminate()
    processes.clear()

def monitor():
    global last_reset_date
    global RESET_FLAG
    logging.info("🔄 Watchdog bắt đầu chạy...")

    while True:
        now = datetime.datetime.now()

        # 1. Kiểm tra đến giờ reset
        if (now.hour == RESET_HOUR and now.minute == RESET_MINUTE 
            and last_reset_date != now.date()):
            logging.info(f"[RESET] {now} - Reset toàn bộ crawler...")
            stop_all()
            last_reset_date = now.date()
            RESET_FLAG = True

        if RESET_FLAG:
            logging.info(f"[RESET] {now} - Reset cờ RESET_FLAG waiting 2000s...")
            time.sleep(2000)
            RESET_FLAG = False

        # 2. Giám sát process
        for path in CRAWLERS:
            proc = processes.get(path)

            # Nếu chưa chạy hoặc đã chết → restart
            if proc is None or proc.poll() is not None:
                processes[path] = start_crawler(path)

        # 3. Chờ 600 giây rồi kiểm tra lại
        time.sleep(600)

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        logging.info("Watchdog dừng bằng Ctrl+C, tắt toàn bộ crawler...")
        stop_all()
