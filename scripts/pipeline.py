import os
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import math
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import instructor
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

from scripts.schemas import TopicChunkLst
from scripts.video_converter import (
    convert_video_to_ready_wav_pydub,
    parse_time_to_seconds,
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


def _transcribe_chunk(args: tuple) -> tuple:
    """
    Transcribe mot chunk duy nhat (worker function cho ThreadPoolExecutor).
    Tra ve (chunk_index, list_of_segments).
    """
    i, chunk_audio, chunk_offset_sec, model, api_key = args

    # Tạo temp file unique de tranh conflict
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        temp_path = tmp.name

    try:
        # Export chunk vao temp file
        chunk_audio.export(temp_path, format="wav", parameters=["-acodec", "pcm_s16le"])

        # Tao client moi cho moi thread (thread-safe)
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language="vi",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        if hasattr(transcription, "segments") and transcription.segments:
            for seg in transcription.segments:
                segments.append({
                    "start": seg.start + chunk_offset_sec,
                    "end": seg.end + chunk_offset_sec,
                    "text": seg.text.strip(),
                })
        else:
            # Fallback: neu API khong tra ve segments
            chunk_end_sec = chunk_offset_sec + len(chunk_audio) / 1000
            segments.append({
                "start": chunk_offset_sec,
                "end": chunk_end_sec,
                "text": transcription.text.strip(),
            })

        print(f"  Doan {i + 1}: OK ({len(segments)} segments)")
        return i, segments

    except Exception as e:
        print(f"  Doan {i + 1}: LOI - {e}")
        return i, []
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def transcribe_long_audio(
    input_wav_path: str,
    chunk_minutes: int = 10,
    model: str = "qwen/qwen3-asr-1.7b",
    max_workers: int = 5,
) -> list:
    """
    Cat audio thanh cac doan nho, gui len API de nhan dien va ghop ket qua.
    Ap dung co che Overlap de chong mat chu o ranh gioi cat.
    Chay da luong voi ThreadPoolExecutor de tang toc.
    Tra ve danh sach segments voi thoi gian.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")

    print(f"Dang tai file {input_wav_path}...")
    audio = AudioSegment.from_wav(input_wav_path)

    chunk_length_ms = chunk_minutes * 60 * 1000
    overlap_ms = 2 * 1000
    total_length_ms = len(audio)
    total_chunks = math.ceil(total_length_ms / chunk_length_ms)

    print(f"Tong thoi luong: {total_length_ms / 1000 / 60:.2f} phut.")
    print(f"Se chia thanh {total_chunks} doan de xu ly.")
    print(f"Chay da luong voi {max_workers} workers...")

    # Prepare chunk args
    chunk_args = []
    for i in range(total_chunks):
        start_ms = i * chunk_length_ms
        end_ms = min(total_length_ms, (i + 1) * chunk_length_ms + overlap_ms)
        chunk_offset_sec = start_ms / 1000
        chunk_audio = audio[start_ms:end_ms]
        chunk_args.append((i, chunk_audio, chunk_offset_sec, model, api_key))

    # Chay da luong
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_transcribe_chunk, args): args[0]
            for args in chunk_args
        }

        for future in as_completed(future_to_idx):
            idx, segments = future.result()
            results[idx] = segments

    # Merge results theo thu tu chunk
    all_segments = []
    for i in range(total_chunks):
        all_segments.extend(results.get(i, []))

    total_chars = sum(len(s["text"]) for s in all_segments)
    print(f"\nHoan thanh! Tong so ky tu: {total_chars}, so segment: {len(all_segments)}")
    return all_segments


def attach_sub_text(segments: list, topic_chunks: TopicChunkLst) -> TopicChunkLst:
    """
    Gan sub_text cho moi topic tu segments goc.
    sub_text = toan bo text cac segments co thoi gian nam trong [start_time, end_time] cua topic.
    """
    for topic in topic_chunks.topics:
        start_sec = parse_time_to_seconds(topic.start_time)
        end_sec = parse_time_to_seconds(topic.end_time)

        # Loc segments nam trong khoang thoi gian topic (overlap check)
        matched = [
            s["text"] for s in segments
            if s["end"] > start_sec and s["start"] < end_sec
        ]

        topic.sub_text = " ".join(matched)

    return topic_chunks


def extract_topics(
    segments: list,
    model: str = "deepseek/deepseek-v4.1-flash",
) -> TopicChunkLst:
    """
    Dung LLM de tach segments thanh cac chu de co timestamp.
    """
    prompt_path = Path(__file__).parent.parent / "assets" / "prompt" / "topic_detect_segment.md"
    SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8")

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

    # Step 3.5: Attach sub_text cho moi topic
    print("\n" + "=" * 50)
    print("STEP 3.5: Gan sub_text cho tung chu de")
    print("=" * 50)
    topic_chunks = attach_sub_text(segments, topic_chunks)
    print(f"Da gan sub_text cho {len(topic_chunks.topics)} chu de.")

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
