import os
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import math
import time
from pathlib import Path

import instructor
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

from scripts.schemas import TopicChunkLst
from scripts.video_converter import (
    convert_video_to_ready_wav_pydub,
    split_video_by_topics,
)

load_dotenv()


def format_time(seconds: float) -> str:
    """Convert seconds to HH:MM:SS hoac MM:SS format"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def transcribe_long_audio(
    input_wav_path: str,
    chunk_minutes: int = 10,
    model: str = "qwen/qwen3-asr-1.7b",
) -> list:
    """
    Cat audio thanh cac doan nho, gui len API de nhan dien va ghop ket qua.
    Ap dung co che Overlap de chong mat chu o ranh gioi cat.
    Tra ve danh sach segments voi thoi gian.
    """
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    print(f"Dang tai file {input_wav_path}...")
    audio = AudioSegment.from_wav(input_wav_path)

    chunk_length_ms = chunk_minutes * 60 * 1000
    overlap_ms = 2 * 1000
    total_length_ms = len(audio)
    total_chunks = math.ceil(total_length_ms / chunk_length_ms)

    print(f"Tong thoi luong: {total_length_ms / 1000 / 60:.2f} phut.")
    print(f"Se chia thanh {total_chunks} doan de xu ly.")

    all_segments = []

    for i in range(total_chunks):
        start_ms = i * chunk_length_ms
        end_ms = min(total_length_ms, (i + 1) * chunk_length_ms + overlap_ms)
        chunk_offset_sec = start_ms / 1000

        print(f"  Doan {i + 1}/{total_chunks} ({start_ms/1000:.0f}s - {end_ms/1000:.0f}s)... ", end="", flush=True)

        chunk = audio[start_ms:end_ms]
        temp_chunk_path = f"temp_chunk_{i}.wav"
        chunk.export(temp_chunk_path, format="wav", parameters=["-acodec", "pcm_s16le"])

        try:
            with open(temp_chunk_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    language="vi",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            if hasattr(transcription, "segments") and transcription.segments:
                for seg in transcription.segments:
                    all_segments.append({
                        "start": seg.start + chunk_offset_sec,
                        "end": seg.end + chunk_offset_sec,
                        "text": seg.text.strip(),
                    })
            else:
                all_segments.append({
                    "start": chunk_offset_sec,
                    "end": end_ms / 1000,
                    "text": transcription.text.strip(),
                })
            print("OK")
        except Exception as e:
            print(f"LOI: {e}")
        finally:
            if os.path.exists(temp_chunk_path):
                os.remove(temp_chunk_path)

        if i < total_chunks - 1:
            time.sleep(1)

    total_chars = sum(len(s["text"]) for s in all_segments)
    print(f"\nHoan thanh! Tong so ky tu: {total_chars}, so segment: {len(all_segments)}")
    return all_segments


def extract_topics(
    segments: list,
    model: str = "deepseek/deepseek-v4.1-flash",
) -> TopicChunkLst:
    """
    Dung LLM de tach segments thanh cac chu de co timestamp.
    """
    SYSTEM_PROMPT = """
Bạn là chuyên gia phân tích nội dung giáo dục.
Bạn sẽ nhận được transcript của một bài giảng, mỗi dòng có định dạng [MM:SS] nội dung.

Hãy tách ra thành các CHỦ ĐỀ LỚN được nói tới trong bài giảng.
Mỗi chủ đề nên có thời lượng ít nhất 5 phút. Các nội dung nhỏ lẻ liên quan đến nhau nên được gộp thành một chủ đề lớn.

Ví dụ:
- "Công thức lượng giác cơ bản, công thức cộng, nhân đôi, hạ bậc" nên là MỘT chủ đề
- "Định lý sin" là một chủ đề riêng
- "Định lý côsin" là một chủ đề riêng
- "Bài tập ứng dụng" có thể gộp nhiều bài tập liên quan vào một chủ đề

Với mỗi chủ đề, hãy xác định thời gian bắt đầu và kết thúc dựa trên timestamp trong transcript.
Tóm tắt nội dung mỗi chủ đề một cách súc tích.
"""

    # Format segments thanh text voi timestamp
    transcript_text = "\n".join(
        f"[{format_time(s['start'])}] {s['text']}" for s in segments
    )

    client = instructor.from_openai(
        OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    )

    print("Dang phan tach chu de voi LLM...")
    topic_chunks = client.chat.completions.create(
        model=model,
        response_model=TopicChunkLst,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcribe cua bai giang:\n\n{transcript_text}"},
        ],
        temperature=0.2,
    )

    print(f"Da tim duoc {len(topic_chunks.topics)} chu de.")
    return topic_chunks


def process_video(
    video_path: str,
    chunk_minutes: int = 10,
    transcribe_model: str = "qwen/qwen3-asr-1.7b",
    topic_model: str = "deepseek/deepseek-v4.1-flash",
    split_video: bool = True,
) -> TopicChunkLst:
    """
    Full pipeline: video -> audio -> transcribe -> topics -> (optional) split video.

    Args:
        video_path: Duong dan video goc
        chunk_minutes: So moi chunk khi transcribe
        transcribe_model: Model ASR de transcribe
        topic_model: Model LLM de tach chu de
        split_video: Co chia video theo chu de khong

    Returns:
        TopicChunkLst voi start_time, end_time, topic, summary
    """
    video_path = str(Path(video_path).resolve())
    video_name = Path(video_path).stem

    # Step 1: Video -> WAV
    print("=" * 50)
    print("STEP 1: Chuyen doi video thanh WAV")
    print("=" * 50)
    wav_dir = str(Path(video_path).parent.parent / "audio" / "test")
    os.makedirs(wav_dir, exist_ok=True)
    output_wav_path = os.path.join(wav_dir, f"{video_name}.wav")
    convert_video_to_ready_wav_pydub(video_path, output_wav_path)

    # Step 2: WAV -> Transcribe segments
    print("\n" + "=" * 50)
    print("STEP 2: Transcribe audio thanh van ban")
    print("=" * 50)
    segments = transcribe_long_audio(output_wav_path, chunk_minutes, transcribe_model)

    # Step 3: Segments -> LLM topics
    print("\n" + "=" * 50)
    print("STEP 3: Phan tach chu de voi LLM")
    print("=" * 50)
    topic_chunks = extract_topics(segments, topic_model)

    # Hien thi ket qua
    print("\n" + "=" * 50)
    print("KET QUA: CAC CHU DE")
    print("=" * 50)
    for i, chunk in enumerate(topic_chunks.topics, 1):
        print(f"\n--- Chu de {i}: {chunk.topic} ---")
        print(f"Thoi gian: {chunk.start_time} - {chunk.end_time}")
        print(f"Tom tat: {chunk.summary}")

    # Step 4: (Optional) Split video by topics
    if split_video:
        print("\n" + "=" * 50)
        print("STEP 4: Chia video theo chu de")
        print("=" * 50)
        split_video_by_topics(video_path, topic_chunks.topics)

    return topic_chunks
