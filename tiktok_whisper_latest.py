import argparse
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

import yt_dlp
import torch
import whisper
from whisper.utils import get_writer


def get_latest_tiktok_video_entry(username: str) -> Dict[str, Any]:
    """
    Lấy metadata video mới nhất từ profile TikTok của @username bằng yt-dlp (extract_flat).
    Trả về dict entry chứa ít nhất 'url' hoặc 'webpage_url' và 'timestamp'.
    """
    profile_url = f"https://www.tiktok.com/@{username}"
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,         # không tải, chỉ lấy danh sách
        "skip_download": True,
        "nocheckcertificate": True,
        "noplaylist": False,
    }
    # if cookies_file and os.path.exists(cookies_file):
    #     ydl_opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(profile_url, download=False)

    entries: List[Dict[str, Any]] = info.get("entries", []) if isinstance(info, dict) else []
    if not entries:
        raise RuntimeError("Không lấy được danh sách video. Có thể TikTok chặn truy cập (yêu cầu cookies) hoặc username sai.")

    # Chọn entry có timestamp lớn nhất (mới nhất)
    def entry_ts(e):
        ts = e.get("timestamp")
        # Nếu thiếu timestamp, ưu tiên đầu danh sách (thường là mới nhất)
        return ts if ts is not None else 0

    latest = max(entries, key=entry_ts)
    return latest


def download_best_audio(video_url: str, outdir: str, vid_id: str) -> str:
    # os.makedirs(outdir, exist_ok=True)
    output_path = os.path.join(outdir, f"{vid_id}.%(ext)s")
    ydl_opts = {
        "quiet": False,
        "outtmpl": output_path,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "nocheckcertificate": True,
    }

    # with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    #     info = ydl.extract_info(video_url, download=True)
    #     filename = ydl.prepare_filename(info)   # tên file gốc (thường .mp4)
    #     audio_path = os.path.splitext(filename)[0] + ".mp3"  # đổi sang .mp3 sau postprocess

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)

    # Sau postprocess, file chắc chắn là .mp3

    final_file = os.path.join(outdir, f"{vid_id}.mp3")

    return final_file



def transcribe_with_whisper(audio_path: str, model_size: str = "medium", language: Optional[str] = None,
                            outdir: str = "transcripts") -> Dict[str, str]:
    """
    Transcribe audio bằng OpenAI Whisper (local).
    - model_size: tiny/base/small/medium/large-v2/large-v3
    - language: mã ISO (vd 'vi' cho tiếng Việt) hoặc None để auto-detect
    Xuất file .txt và .srt. Trả về dict đường dẫn file.
    """
    os.makedirs(outdir, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[Whisper] Loading model={model_size} on device={device} ...")
    model = whisper.load_model(model_size, device=device)

    # Bạn có thể thêm options như fp16 nếu GPU hỗ trợ
    transcribe_kwargs = {}
    if language:
        transcribe_kwargs["language"] = language

    print("[Whisper] Transcribing...")
    result = model.transcribe(audio_path, **transcribe_kwargs)

    base = os.path.splitext(os.path.basename(audio_path))[0]
    txt_path = os.path.join(outdir, f"{base}.txt")
    srt_path = os.path.join(outdir, f"{base}.srt")

    # Ghi .txt
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(result.get("text", "").strip())

    # # Ghi .srt
    # srt_writer = get_writer("srt", outdir)
    # srt_writer(result, base)

    return {"txt": txt_path, "srt": srt_path}


def main():

    user_name = "ongtoanvlog"  # Thay thế bằng tên kênh TikTok bạn muốn
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
    latest_entry = get_latest_tiktok_video_entry(args.username)

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
    print(f"Video mới nhất: {video_url}\nThời gian đăng: {ts_str}")

    print("\n[Tải audio bằng yt-dlp] ...")
    video_id = f"t_{args.username}_{video_url.rstrip('/').split('/')[-1]}"
    audio_path = download_best_audio(video_url, outdir=args.outdir, vid_id=video_id)
    print(f"Đã tải audio: {audio_path}")

    print("\n[Transcribe bằng Whisper] ...")
    outputs = transcribe_with_whisper(audio_path, model_size=args.model, language=args.lang, outdir=args.transdir)



if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Lỗi: {e}", file=sys.stderr)
        sys.exit(1)
