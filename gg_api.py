import os
from googleapiclient.discovery import build
import yt_dlp
import whisper
import isodate
import logging
import torch
from datetime import datetime
import threading
import db.db_adapter as db
from multiprocessing import Pool, cpu_count
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
import time
import argparse
import tiktok_whisper_latest as tiktok
import random
from multiprocessing import Process

# ===== CẤU HÌNH =====
API_KEY = ""   # 🔑 thay bằng API key YouTube Data v3
CHANNEL_ID = "UCeCUvXYMbKs0BjOIRaIdDjw"  # channelId kênh muốn lấy
AUDIO_DIR = "downloads/audio"
SCRIPT_DIR = "downloads/transcripts"
LOG_DIR = "logs"
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(SCRIPT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ===== Cấu hình logging =====
log_file = os.path.join(LOG_DIR, "log.txt")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)


# ===== B1: Lấy video mới nhất từ kênh =====
def get_latest_video(channel_id):
    youtube = build("youtube", "v3", developerKey=API_KEY)

    # Lấy activity mới nhất (tốn 1 unit)
    request = youtube.activities().list(
        part="snippet,contentDetails",
        channelId=channel_id,
        maxResults=5
    )
    response = request.execute()
    videos = []

    for item in response.get("items", []):
        # Chỉ lấy activity dạng upload video
        if "upload" not in item.get("contentDetails", {}):
            continue

        video_id = item["contentDetails"]["upload"]["videoId"]

        # Gọi videos().list để lấy chi tiết video
        video_request = youtube.videos().list(
            part="contentDetails,snippet,status",
            id=video_id
        )
        video_response = video_request.execute()

        if not video_response["items"]:
            continue

        details = video_response["items"][0]
        duration = details["contentDetails"]["duration"]
        seconds = isodate.parse_duration(duration).total_seconds()

        # Kiểm tra trạng thái upload + quyền riêng tư
        upload_status = details["status"].get("uploadStatus", "unknown")
        privacy_status = details["status"].get("privacyStatus", "unknown")

        if seconds > 60 and upload_status == "processed" and privacy_status == "public":
            published_at_str = details['snippet']['publishedAt']
            published_at_dt = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ")

            logging.info(
                f"✅ Video hợp lệ: {details['snippet']['title']} "
                f"({seconds} giây), đăng lúc {published_at_dt}"
            )

            videos.append({
                "video_id": video_id,
                "title": details["snippet"]["title"],
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": f"{published_at_dt}"
            })

    # Trả về video mới nhất
    return videos[0] if videos else None


# ===== B2: Tải audio (MP3) bằng yt-dlp =====
# def download_audio(video_url, dir, video_id):
#     ydl_opts = {
#         'format': 'bestaudio/best',
#         'outtmpl': os.path.join(dir, '%(title)s.%(ext)s'),
#         'postprocessors': [{
#             'key': 'FFmpegExtractAudio',
#             'preferredcodec': 'mp3',
#             'preferredquality': '192',
#         }],
#     }
#     with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#         info = ydl.extract_info(video_url, download=True)
#         filename = os.path.join(dir, f"{video_id}.mp3")
#         # Đổi tên file đã tải thành video_id.mp3
#         downloaded_file = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
#         if downloaded_file != filename:
#             os.rename(downloaded_file, filename)
#         return filename
def download_audio(video_url, dir, video_id):
    # Đường dẫn file đích (luôn .mp3)
    output_path = os.path.join(dir, f"{video_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)

    # Sau postprocess, file chắc chắn là .mp3
    final_file = os.path.join(dir, f"{video_id}.mp3")
    return final_file

def transcribe_audio(file_path):
    logging.info("⏳ Đang load mô hình Whisper...")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logging.info(f"🖥️ Đang chạy trên: {device.upper()}")
    logging.info(torch.cuda.get_device_name(torch.device(device)))
    model = whisper.load_model("large").to(device)
    logging.info("🎙️ Đang nhận diện giọng nói...")
    
    result = model.transcribe(file_path, language="vi")
    return result["text"]

# def process_videos_from_db():
#     logging.info("🔍 Đang tìm video mới nhất...")
#     try:
#         conn = db.get_connection()
#         if conn is None:
#             print("❌ Không thể kết nối đến cơ sở dữ liệu PostgreSQL.")
#             exit(1)

#         try:
#             with conn.cursor() as cursor:
#                 cursor.execute("SELECT yt_id, yt_link, yt_name FROM yt_group ORDER BY RANDOM()")
#                 rows = cursor.fetchall()
#                 data_list = list(rows)
#         except Exception as e:
#             print("❌ Lỗi khi truy vấn:", e)
#             exit(1)
#         finally:
#             conn.close()

#         for id, link, name in data_list:
#             print(f"🔗 Đang truy cập nhóm: {name}_{link}")
#             latest = get_latest_video(link)
#             if latest:
#                 logging.info(f"📺 Video mới nhất {latest['video_id']}: {latest['title']}")
#                 logging.info(f"🔗 Link: {latest['url']}")
#                 if db.validate_yt_post(latest['title'], latest['url']):
#                     audio_file = download_and_save_audio(latest['url'], AUDIO_DIR)
#                     if audio_file:
#                         thread = threading.Thread(target=process_audio_file, args=(id, latest, audio_file))
#                         thread.start()
#                 else:
#                     logging.error("❌ đã tồn tại trong cơ sở dữ liệu.")
#             else:
#                 logging.warning("❌ Không tìm thấy video.")
#     except Exception as e:
#         logging.error(f"❌ Lỗi: {str(e)}", exc_info=True)

# def process_videos_from_db():
#     logging.info("🔍 Đang tìm video mới nhất...")
#     try:
#         conn = db.get_connection()
#         if conn is None:
#             print("❌ Không thể kết nối đến cơ sở dữ liệu PostgreSQL.")
#             exit(1)

#         try:
#             with conn.cursor() as cursor:
#                 cursor.execute("SELECT yt_id, yt_link, yt_name FROM yt_group ORDER BY RANDOM()")
#                 rows = cursor.fetchall()
#                 data_list = list(rows)
#         except Exception as e:
#             print("❌ Lỗi khi truy vấn:", e)
#             exit(1)
#         finally:
#             conn.close()

#         # chuẩn bị danh sách task
#         tasks = []
#         for id, link, name in data_list:
#             print(f"🔗 Đang truy cập nhóm: {name}_{link}")
#             latest = get_latest_video(link)
#             if latest:
#                 logging.info(f"📺 Video mới nhất {latest['video_id']}: {latest['title']}")
#                 logging.info(f"🔗 Link: {latest['url']}")
#                 if db.validate_yt_post(latest['title'], latest['url']):
#                     audio_file = download_and_save_audio(latest['url'], AUDIO_DIR)
#                     if audio_file:
#                         tasks.append((id, latest, audio_file))
#                 else:
#                     logging.error("❌ đã tồn tại trong cơ sở dữ liệu.")
#             else:
#                 logging.warning("❌ Không tìm thấy video.")

#         # chạy song song bằng multiprocessing
#         if tasks:
#             max_workers = min(len(tasks), cpu_count())  # giới hạn theo số CPU
#             with Pool(processes=max_workers) as pool:
#                 pool.starmap(process_audio_file, tasks)  # truyền nhiều arg

#     except Exception as e:
#         logging.error(f"❌ Lỗi: {str(e)}", exc_info=True)

def download_and_save_audio(video_url, audio_dir, video_id):
    logging.info("✅ Video chưa tồn tại trong cơ sở dữ liệu, bắt đầu tải audio...")
    logging.info("⬇️ Đang tải audio (mp3)...")
    try:
        audio_file = download_audio(video_url, audio_dir, video_id)
        logging.info(f"✅ Đã tải: {audio_file}")
        return audio_file
    except Exception as e:
        logging.error(f"❌ Lỗi khi tải audio: {e}")
        return None

def process_audio_file(id, audio_path):
    logging.info(f"🔊 Đang xử lý audio: {audio_path}")
    audio_file = str(audio_path)
    if not os.path.exists(audio_file):
        logging.error(f"❌ File audio không tồn tại: {audio_file}")
        return
    transcript = transcribe_audio(audio_file)
    try:
        os.remove(audio_file)
    except Exception as e:
        logging.warning(f"⚠️ Không thể xóa file audio: {audio_file}. Lỗi: {e}")

    logging.info("===== NỘI DUNG VIDEO =====")
    logging.info(transcript)

    if transcript.strip() == "":
        logging.error("❌ Không thể nhận diện nội dung video.")
        return

    if db.update_yt_post_content(id, transcript):
        logging.info("✅ Đã cập nhật nội dung video vào cơ sở dữ liệu.")

    # if db.insert_yt_post(f"{id}_{latest['video_id']}", latest['title'], latest['url'], transcript, latest['published_at']):
    #     logging.info("✅ Đã lưu nội dung video vào cơ sở dữ liệu.")
    #     base_txt_path = os.path.join(SCRIPT_DIR, os.path.splitext(os.path.basename(audio_file))[0] + ".txt")
    #     txt_path = base_txt_path
    #     count = 1
    #     while os.path.exists(txt_path):
    #         txt_path = os.path.join(SCRIPT_DIR, os.path.splitext(os.path.basename(audio_file))[0] + f"_{count}.txt")
    #         count += 1
    #     with open(txt_path, "w", encoding="utf-8") as f:
    #         f.write(transcript)
    #     logging.info(f"💾 Đã lưu transcript vào: {txt_path}")
    # else:
    #     logging.error("❌ Nội dung video đã tồn tại trong cơ sở dữ liệu.")

def fetch_and_download_audio():
    logging.info("🔍 Đang tìm video mới nhất...")
    conn = db.get_connection()
    if conn is None:
        logging.error("❌ Không thể kết nối DB")
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT yt_id, yt_link, yt_name FROM yt_group ORDER BY RANDOM()")
            rows = cursor.fetchall()
            data_list = list(rows)
    finally:
        conn.close()

    for id, link, name in data_list:
        logging.info(f"🔗 Nhóm: {name}_{link}")
        latest = get_latest_video(link)
        if not latest:
            logging.warning("❌ Không tìm thấy video.")
            continue

        logging.info(f"📺 Video mới nhất {latest['video_id']}: {latest['title']}")

        if not db.validate_yt_post(latest['title'], latest['url']):
            logging.warning("⚠️ Đã tồn tại trong DB, bỏ qua.")
            continue
        video_id = f"{id}_{latest['video_id']}"
        audio_file = download_and_save_audio(latest['url'], AUDIO_DIR, video_id)
        if audio_file:
            logging.info(f"💾 Đã lưu audio: {audio_file}")
            # Ghi metadata vào DB để Job 2 xử lý
            if db.insert_yt_post(video_id, latest['title'], latest['url'], "", latest['published_at']):
                logging.info("✅ Đã lưu metadata video vào cơ sở dữ liệu.")
        time.sleep(random.randint(5,15))
    # Sau khi xong thì add Job get last tiktok video ngay
    print("➡️ Job1 hoàn tất, thêm Job get last tiktok video vào lịch")
    scheduler.add_job(
        fectch_download_audio_tiktok,
        "date",   # chỉ chạy 1 lần
        run_date=datetime.now(),  # chạy ngay lập tức
        id="job3_once",
        replace_existing=True
    )


# def process_audio_job():
#     logging.info("🎶 Đang tìm audio chưa xử lý...")
#     conn = db.get_connection()
#     if conn is None:
#         logging.error("❌ Không thể kết nối DB")
#         return

#     try:
#         with conn.cursor() as cursor:
#             cursor.execute("SELECT post_id FROM yt_post WHERE post_processed = false")
#             rows = cursor.fetchall()
#     finally:
#         conn.close()

#     if not rows:
#         logging.info("✅ Không có audio mới để xử lý.")
#         return

#     for row in rows:
#         post_id = row[0]
#         audio_file = os.path.join(AUDIO_DIR, f"{post_id}.mp3")
#         process_audio_file(post_id, Path(audio_file))

    # tasks = [(post_id, Path(filename = os.path.join(AUDIO_DIR, f"{post_id}.mp3"))) for post_id in rows]

    # if not tasks:
    #     logging.info("✅ Không có audio mới.")
    #     return

    # max_workers = min(len(tasks), cpu_count())
    # with Pool(processes=max_workers) as pool:
    #     pool.starmap(process_audio_file, tasks)

    # # Sau khi xử lý xong, update trạng thái
    # conn = db.get_connection()
    # with conn.cursor() as cursor:
    #     for yt_id, yt_video_id, _ in tasks:
    #         cursor.execute("UPDATE pending_audio SET processed = true WHERE yt_id = %s AND yt_video_id = %s", (yt_id, yt_video_id))
    #     conn.commit()
    # conn.close()

def worker(gpu_id, tasks):
    # Gán GPU cho process này
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    # Load model Whisper 1 lần trên GPU đó
    logging.info(f"[GPU {gpu_id}] Load model Whisper...")
    model = whisper.load_model("large").to("cuda")

    for post_id, audio_file in tasks:
        logging.info(f"[GPU {gpu_id}] Đang xử lý {audio_file}")
        try:
            result = model.transcribe(str(audio_file), language="vi")
            text = result["text"]

            # Lưu kết quả ra file txt (hoặc update DB)
            # out_file = Path(audio_file).with_suffix(".txt")
            # with open(out_file, "w", encoding="utf-8") as f:
            #     f.write(text)
            if text.strip() == "":
                logging.error("❌ Không thể nhận diện nội dung video.")
                return

            if db.update_yt_post_content(post_id, text):
                logging.info(f"[GPU {gpu_id}] ✅ Xong {post_id}")
            
            try:
                os.remove(audio_file)
            except Exception as e:
                logging.warning(f"⚠️ Không thể xóa file audio: {audio_file}. Lỗi: {e}")

            
        except Exception as e:
            logging.error(f"[GPU {gpu_id}] ❌ Lỗi {post_id}: {e}")

def process_audio_job():
    logging.info("🎶 Đang tìm audio chưa xử lý...")

    conn = db.get_connection()
    if conn is None:
        logging.error("❌ Không thể kết nối DB")
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT post_id FROM yt_post WHERE post_processed = false")
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        logging.info("✅ Không có audio mới để xử lý.")
        return

    # Chuẩn bị list (post_id, file_path)
    tasks = []
    for row in rows:
        post_id = row[0]
        audio_file = os.path.join(AUDIO_DIR, f"{post_id}.mp3")
        tasks.append((post_id, Path(audio_file)))

    # Chia xen kẽ cho 2 GPU
    tasks_gpu0 = tasks[0::2]
    tasks_gpu1 = tasks[1::2]

    # Tạo 2 process song song
    p0 = Process(target=worker, args=(0, tasks_gpu0))
    p1 = Process(target=worker, args=(1, tasks_gpu1))

    p0.start()
    p1.start()
    p0.join()
    p1.join()

    logging.info("🎉 Hoàn tất xử lý tất cả audio chưa xử lý.")

def fectch_download_audio_tiktok():

    logging.info("🔍 Đang tìm tiktok video mới nhất...")
    conn = db.get_connection()
    if conn is None:
        logging.error("❌ Không thể kết nối DB")
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT tt_id, tt_link, tt_name FROM tt_group ORDER BY RANDOM()")
            rows = cursor.fetchall()
            data_list = list(rows)
    finally:
        conn.close()

    for id, link, name in data_list:
        logging.info(f"🔗 Nhóm: {id}/{name}_{link}")

        user_name = link  # Thay thế bằng tên kênh TikTok bạn muốn
        cookies_file = None  # Thay thế bằng đường dẫn cookies.txt nếu cần
        model_size = "medium"  # Kích thước mô hình Whisper
        language = 'vi'  # Ngôn ngữ, để trống để tự động    
        outdir = "downloads/audio"  # Thư mục tải audio
        transdir = "downloads/transcripts"  # Thư mục lưu transcript
        args = argparse.Namespace(
            username=user_name,
            cookies=cookies_file,
            model=model_size,
            lang=language,
            outdir=outdir,
            transdir=transdir
        )

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lấy video mới nhất của @{args.username} ...")
        latest_entry = tiktok.get_latest_tiktok_video_entry(args.username)

        # Cố gắng lấy URL video.
        video_url = latest_entry.get("url") or latest_entry.get("webpage_url") or latest_entry.get("original_url")
        if not video_url:
            # Trong extract_flat, TikTok đôi khi trả về 'id' thay vì URL đầy đủ
            vid_id = latest_entry.get("id")
            if vid_id:
                video_url = f"https://www.tiktok.com/@{args.username}/video/{vid_id}"
            else:
                raise RuntimeError("Không xác định được URL video mới nhất.")

        ts = latest_entry.get("timestamp")
        ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "N/A"
        logging.info(f"Video mới nhất: {video_url}\nThời gian đăng: {ts_str}")

        if not db.validate_yt_post(latest_entry['title'], video_url):
            logging.warning("⚠️ Đã tồn tại trong DB, bỏ qua.")
            continue

        logging.info("\n[Tải audio bằng yt-dlp] ...")
        video_id = f"t_{args.username}_{video_url.rstrip('/').split('/')[-1]}"
        audio_path = tiktok.download_best_audio(video_url, outdir=args.outdir, vid_id=video_id)
        if audio_path:
            logging.info(f"💾 Đã lưu audio: {audio_path}")
            # Ghi metadata vào DB để Job 2 xử lý
            if db.insert_yt_post(video_id, latest_entry['title'], video_url, "", ts_str):
                logging.info("✅ Đã lưu metadata video vào cơ sở dữ liệu.")
        time.sleep(random.randint(5,15))

                   
if __name__ == "__main__":
    # process_audio_job()  # Lấy video mới nhất và tải audio
    scheduler = BackgroundScheduler()

    # Job 1: mỗi 4 giờ (0, 4, 8, 12, 16, 20)
    scheduler.add_job(
        fetch_and_download_audio,
        "cron",
        hour="0,4,6,8,18,20,22",
        id="fetch_job",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1,
        next_run_time=datetime.now() #cho chạy luôn
    )
    # Job 2: mỗi giờ
    scheduler.add_job(
        process_audio_job,
        "interval",
        hours=1,
        id="process_job",
        max_instances=1,        # chỉ cho phép 1 job chạy
        coalesce=True,          # không chạy bù nếu lỡ
        misfire_grace_time=1,    # nếu lỡ giờ thì bỏ qua
        # next_run_time=datetime.now() #cho chạy luôn
    )
    # Start scheduler
    scheduler.start()

    print("✅ Scheduler đã khởi động. Nhấn Ctrl+C để dừng.")

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("🛑 Scheduler đã dừng.")
# pyinstaller --onefile --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py
# pyinstaller --onefile --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py

