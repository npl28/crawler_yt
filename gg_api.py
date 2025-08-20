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
    
    # Chỉ được dùng snippet ở đây
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        maxResults=5,
        type="video",
        videoDuration="any"
    )
    response = request.execute()
    videos = []

    for item in response.get("items", []):
        video_id = item["id"]["videoId"]

        # Gọi videos().list để lấy contentDetails
        video_request = youtube.videos().list(
            part="contentDetails,snippet,status",
            id=video_id
        )
        video_response = video_request.execute()

        if video_response["items"]:
            details = video_response["items"][0]
            duration = details["contentDetails"]["duration"]
            seconds = isodate.parse_duration(duration).total_seconds()

            # kiểm tra video đã publish hay chưa
            upload_status = details["status"].get("uploadStatus", "unknown")
            privacy_status = details["status"].get("privacyStatus", "unknown")

            if seconds > 60 and upload_status == "processed" and privacy_status == "public":
                published_at_str = details['snippet']['publishedAt']
                published_at_dt = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ")
                logging.info(f"✅ Video hợp lệ: {item['snippet']['title']} ({seconds} giây), đăng lúc {published_at_dt}")
                videos.append({
                    "video_id": video_id,
                    "title": details["snippet"]["title"],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": f"{published_at_dt}"
                })

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
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logging.info(f"🖥️ Đang chạy trên: {device.upper()}")
    
    model = whisper.load_model("medium").to(device)
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

    tasks = [(post_id, Path(filename = os.path.join(AUDIO_DIR, f"{post_id}.mp3"))) for post_id in rows]

    if not tasks:
        logging.info("✅ Không có audio mới.")
        return

    max_workers = min(len(tasks), cpu_count())
    with Pool(processes=max_workers) as pool:
        pool.starmap(process_audio_file, tasks)

    # # Sau khi xử lý xong, update trạng thái
    # conn = db.get_connection()
    # with conn.cursor() as cursor:
    #     for yt_id, yt_video_id, _ in tasks:
    #         cursor.execute("UPDATE pending_audio SET processed = true WHERE yt_id = %s AND yt_video_id = %s", (yt_id, yt_video_id))
    #     conn.commit()
    # conn.close()
                   
if __name__ == "__main__":
    fetch_and_download_audio()
# pyinstaller --onefile --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py
# pyinstaller --onefile --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py

