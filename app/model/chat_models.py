"""
Chat-specific dataclasses for predictable responses
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
import json


@dataclass
class ChatMessage:
    """Single chat message structure"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessedCSV:
    """Processed CSV table structure"""
    filename: str
    caption: str
    headers: List[str]
    rows: List[List[str]]
    showing_rows: int = 0
    loading: bool = False
    error: bool = False
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.showing_rows == 0:
            self.showing_rows = len(self.rows)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessedImage:
    """Processed image structure with base64 data"""
    path: str
    filename: str
    caption: str
    data_url: Optional[str] = None  # data:image/jpeg;base64,...
    mime_type: Optional[str] = None
    size: Optional[int] = None
    error: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Reference:
    """Document reference structure"""
    chapter: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    page: Optional[str] = None
    section_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ChatResponse:
    """Complete chat response structure - matches frontend expectations exactly"""
    answer: str
    csv_tables: List[ProcessedCSV] = field(default_factory=list)
    processed_images: List[ProcessedImage] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)

    # Optional metadata
    context_used: bool = False
    processing_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "csv_tables": [table.to_dict() for table in self.csv_tables],
            "processed_images": [img.to_dict() for img in self.processed_images],
            "references": [ref.to_dict() for ref in self.references],
            "context_used": self.context_used,
            "processing_time": self.processing_time
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ErrorResponse:
    """Standardized error response"""
    error: str
    error_type: str = "general"
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class WebhookResponse:
    """Webhook response structure"""
    status: str  # 'success' or 'error'
    query: str
    answer: str
    error: Optional[str] = None
    processing_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "status": self.status,
            "query": self.query,
            "answer": self.answer
        }
        if self.error:
            result["error"] = self.error
        if self.processing_time:
            result["processing_time"] = self.processing_time
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class HealthStatus:
    """Service health check response"""
    status: str  # 'healthy', 'degraded', 'unhealthy'
    services: Dict[str, Any]
    timestamp: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "status": self.status,
            "services": self.services
        }
        if self.timestamp:
            result["timestamp"] = self.timestamp
        if self.error:
            result["error"] = self.error
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class StreamingChatResponse:
    """Streaming chat response for progressive loading"""
    answer: str = ""
    stream_id: Optional[str] = None
    is_complete: bool = False
    chunk_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "stream_id": self.stream_id,
            "is_complete": self.is_complete,
            "chunk_index": self.chunk_index
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class MetadataLoadingTask:
    """Task for loading metadata asynchronously after streaming"""
    csv_paths: List[str] = field(default_factory=list)
    image_paths: List[str] = field(default_factory=list)
    metadatas: List[Dict[str, Any]] = field(default_factory=list)
    task_id: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, error

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetadataResponse:
    """Response containing processed metadata"""
    csv_tables: List[ProcessedCSV] = field(default_factory=list)
    processed_images: List[ProcessedImage] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    task_id: Optional[str] = None
    status: str = "completed"
    processing_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "csv_tables": [table.to_dict() for table in self.csv_tables],
            "processed_images": [img.to_dict() for img in self.processed_images],
            "references": [ref.to_dict() for ref in self.references],
            "task_id": self.task_id,
            "status": self.status,
            "processing_time": self.processing_time
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
