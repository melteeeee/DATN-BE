from pydub import AudioSegment
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