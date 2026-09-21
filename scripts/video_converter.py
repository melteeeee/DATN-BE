import os
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

from pydub import AudioSegment
import subprocess
import os

# def convert_video_to_ready_wav_pydub(video_path: str, output_wav_path: str) -> str:
#     """
#     Trích xuất âm thanh từ video dùng pydub, xuất ra WAV 1 kênh, 16000Hz.
#     """
#     if not os.path.exists(video_path):
#         raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")

#     try:
#         print("Đang đọc file video, vui lòng đợi...")
#         # Đọc trực tiếp file video (mp4, mkv, avi...)
#         audio = AudioSegment.from_file(video_path)
        
#         # Chuyển về 1 kênh và 16000 Hz
#         ready_audio = audio.set_channels(1).set_frame_rate(16000)
        
#         # Xuất ra file
#         ready_audio.export(output_wav_path, format="wav")
#         print(f"✅ Đã chuyển đổi thành công: {output_wav_path}")
#         return output_wav_path
#     except Exception as e:
#         print(f"❌ Có lỗi xảy ra: {e}")
#         raise e

def convert_video_to_ready_wav_pydub(video_path: str, output_wav_path: str) -> str:
    """
    Trích xuất âm thanh từ video dùng pydub, xuất ra WAV 1 kênh, 16000Hz, 16-bit PCM.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")

    try:
        print("Đang đọc file video, vui lòng đợi...")
        # Đọc trực tiếp file video (mp4, mkv, avi...)
        audio = AudioSegment.from_file(video_path)
        
        # Chuyển về 1 kênh (mono), 16000 Hz và độ sâu 16-bit (2 bytes)
        ready_audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        
        # Xuất ra file, ép buộc sử dụng codec pcm_s16le bằng tham số của FFmpeg
        ready_audio.export(
            output_wav_path, 
            format="wav",
            parameters=["-acodec", "pcm_s16le"] # <-- THÊM CÁI NÀY
        )
        print(f"✅ Đã chuyển đổi thành công: {output_wav_path}")
        return output_wav_path
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")
        raise e


def parse_time_to_seconds(time_str: str) -> float:
    """
    Chuyển đổi thời gian dạng HH:MM:SS hoặc MM:SS sang giây.
    """
    parts = time_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    else:
        return float(parts[0])


def split_video_by_topics(video_path: str, topics: list, output_dir: str = None) -> list:
    """
    Chia video thành các video con theo từng chủ đề.
    
    Args:
        video_path: Đường dẫn video gốc
        topics: Danh sách các chủ đề có start_time, end_time, topic
        output_dir: Thư mục output (mặc định cùng folder với video gốc)
    
    Returns:
        Danh sách đường dẫn các video con đã tạo
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")
    
    # Lấy tên và extension của video gốc
    video_dir = os.path.dirname(video_path)
    video_basename = os.path.basename(video_path)
    video_name, video_ext = os.path.splitext(video_basename)
    
    # Nếu không có output_dir, dùng cùng folder video gốc
    if output_dir is None:
        output_dir = video_dir + "/splitted"
    
    os.makedirs(output_dir, exist_ok=True)
    
    output_files = []
    
    print(f"Đang chia video thành {len(topics)} phần...")
    
    for i, topic in enumerate(topics):
        start_sec = parse_time_to_seconds(topic.start_time)
        end_sec = parse_time_to_seconds(topic.end_time)
        duration = end_sec - start_sec
        
        # Tạo tên file output
        output_filename = f"{video_name}_{i+1}{video_ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        # Tạo tên topic ngắn gọn cho file
        short_topic = topic.topic[:50].replace("/", "-").replace("\\", "-")
        
        print(f"  [{i+1}/{len(topics)}] {topic.start_time} - {topic.end_time}: {short_topic}...")
        
        try:
            # Dùng ffmpeg để cắt video
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(start_sec),
                "-t", str(duration),
                "-c", "copy",  # Copy codec không encode lại
                "-avoid_negative_ts", "make_zero",
                output_path,
                "-y"  # Ghi đè nếu tồn tại
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 phút timeout
            )
            
            if result.returncode == 0:
                output_files.append(output_path)
                print(f"    ✅ Thành công: {output_filename}")
            else:
                print(f"    ❌ Lỗi: {result.stderr[:200]}")
                
        except subprocess.TimeoutExpired:
            print(f"    ❌ Timeout khi xử lý: {output_filename}")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
    
    print(f"\nHoàn thành! Đã tạo {len(output_files)}/{len(topics)} video con.")
    return output_files