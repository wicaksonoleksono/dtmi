from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from enum import Enum
import json


@dataclass
class CsvTable:
    """Represents a processed CSV table"""
    filename: str
    caption: str
    headers: List[str]
    rows: List[List[str]]
    showing_rows: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProcessedImage:
    """Represents a processed image"""
    path: str
    filename: str
    caption: str
    data: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    data_url: Optional[str] = None
    error: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Reference:
    """Represents a document reference"""
    chapter: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    page: Optional[str] = None
    section_title: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class QueryResponse:
    """Standard query response structure - simplified and predictable"""
    answer: str
    csv_paths: List[str] = None
    image_paths: List[str] = None
    metadatas: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.csv_paths is None:
            self.csv_paths = []
        if self.image_paths is None:
            self.image_paths = []
        if self.metadatas is None:
            self.metadatas = []

    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "csv_paths": self.csv_paths,
            "image_paths": self.image_paths,
            "metadatas": self.metadatas

        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class WebhookResponse:
    """Webhook response structure"""
    status: str
    query: str
    answer: str
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        result = {
            "status": self.status,
            "query": self.query,
            "answer": self.answer
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class ContextInfo:
    """Context information structure - simplified"""
    user_message: str
    bot_response: str
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "user_message": self.user_message,
            "bot_response": self.bot_response,
            "timestamp": self.timestamp
        }


@dataclass
class HealthResponse:
    """Health check response structure - simplified"""
    status: str
    services: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        result = {
            "status": self.status,
            "services": self.services
        }
        if self.error:
            result["error"] = self.error
        return result
