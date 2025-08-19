import os
from googleapiclient.discovery import build
import yt_dlp
import whisper
import isodate
import logging
import torch
import db.db_adapter as db

# ===== CẤU HÌNH =====
API_KEY = "AIzaSyCjWWvLL3g4SBayNEQkrekVlcoJPpb0-Qs"   # 🔑 thay bằng API key YouTube Data v3
CHANNEL_ID = "UCeCUvXYMbKs0BjOIRaIdDjw"  # channelId kênh muốn lấy
OUTPUT_DIR = "youtube/downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== Cấu hình logging =====
log_file = os.path.join(OUTPUT_DIR, "log.txt")
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
                logging.info(f"✅ Video hợp lệ: {item['snippet']['title']} ({seconds} giây)")
                videos.append({
                    "video_id": video_id,
                    "title": details["snippet"]["title"],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": details["snippet"]["publishedAt"]
                })

    return videos[0] if videos else None


# ===== B2: Tải audio (MP3) bằng yt-dlp =====
def download_audio(video_url, output_dir):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
        return filename

def transcribe_audio(file_path):
    logging.info("⏳ Đang load mô hình Whisper...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logging.info(f"🖥️ Đang chạy trên: {device.upper()}")
    
    model = whisper.load_model("medium").to(device)
    logging.info("🎙️ Đang nhận diện giọng nói...")
    
    result = model.transcribe(file_path, language="vi")
    return result["text"]

if __name__ == "__main__":
    logging.info("🔍 Đang tìm video mới nhất...")
    try:
        conn = db.get_connection()
        if conn is None:
            print("❌ Không thể kết nối đến cơ sở dữ liệu PostgreSQL.")
            exit(1)

        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT yt_id, yt_link, yt_name FROM yt_group ORDER BY RANDOM()")
                rows = cursor.fetchall()
                data_list = list(rows)
        except Exception as e:
            print("❌ Lỗi khi truy vấn:", e)
            exit(1)
        finally:
            conn.close()

        results_group = []
        for id, link, name in data_list:
            print(f"🔗 Đang truy cập nhóm: {name}_{link}")
            latest = get_latest_video(link)
            if latest:
                logging.info(f"📺 Video mới nhất {latest['video_id']}: {latest['title']}")
                logging.info(f"🔗 Link: {latest['url']}")
                if db.validate_yt_post(latest['title'], latest['url']):
                    logging.info("✅ Video chưa tồn tại trong cơ sở dữ liệu, bắt đầu tải audio...")
                    logging.info("⬇️ Đang tải audio (mp3)...")
                    audio_file = download_audio(latest['url'], OUTPUT_DIR)
                    logging.info(f"✅ Đã tải: {audio_file}")
                
                    logging.info("✅ Đã lưu vào cơ sở dữ liệu.")
                    transcript = transcribe_audio(audio_file)
                    try:
                        os.remove(audio_file)
                        # logging.info(f"🗑️ Đã xóa file audio: {audio_file}")
                    except Exception as e:
                        logging.warning(f"⚠️ Không thể xóa file audio: {audio_file}. Lỗi: {e}")

                    logging.info("===== NỘI DUNG VIDEO =====")
                    logging.info(transcript)

                    if db.insert_yt_post(f"{id}:{latest['video_id']}", latest['title'], latest['url'], transcript):
                        logging.info("✅ Đã lưu nội dung video vào cơ sở dữ liệu.")
                        base_txt_path = os.path.splitext(audio_file)[0] + ".txt"
                        txt_path = base_txt_path
                        count = 1
                        while os.path.exists(txt_path):
                            txt_path = os.path.splitext(audio_file)[0] + f"_{count}.txt"
                            count += 1
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(transcript)
                        logging.info(f"💾 Đã lưu transcript vào: {txt_path}")
                    else:
                        logging.error("❌ Nội dung video đã tồn tại trong cơ sở dữ liệu.")
 
                else:
                    logging.error("❌ đã tồn tại trong cơ sở dữ liệu.")
                
            else:
                logging.warning("❌ Không tìm thấy video.")
    except Exception as e:
        logging.error(f"❌ Lỗi: {str(e)}", exc_info=True)

# pyinstaller --onefile --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py
# pyinstaller --onefile --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --add-data "C:\Users\PC\AppData\Local\Programs\Python\Python311\Lib\site-packages\whisper\assets;whisper/assets" gg_api.py

