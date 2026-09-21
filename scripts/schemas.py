from pydantic import BaseModel, Field
from typing import List

class TopicChunk(BaseModel):
    start_time: str = Field(..., description="Thời gian bắt đầu định dạng HH:MM:SS hoặc MM:SS")
    end_time: str = Field(..., description="Thời gian kết thúc định dạng HH:MM:SS hoặc MM:SS")
    topic: str = Field(..., description="Tên chủ đề")
    summary: str = Field(..., description="Tóm tắt nội dung chủ đề")

class TopicChunkLst(BaseModel):
    topics: List[TopicChunk]