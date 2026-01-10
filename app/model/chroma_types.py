# app/model/chroma_types.py

from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field
from .enums import Filter, Year


class BaseMetadata(BaseModel):
    """Base metadata fields common to all document types"""
    id: str
    type: str
    chapter: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    section_title: Optional[str] = None
    page: int
    source_file: str
    source_hash: str
    pipeline_ver: float
    year: str  # SARJANA, MAGISTER, DOKTOR, GENERAL
    dep: str  # general, or specific department


class TextMetadata(BaseMetadata):
    """Metadata for text chunks"""
    type: Literal["text"] = "text"
    section_id: str
    chunk_index: int
    total_chunks_in_section: int
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    token_count: int


class ImageMetadata(BaseMetadata):
    """Metadata for image documents"""
    type: Literal["image"] = "image"
    caption: str
    image_id: str
    image_path: str


class TableCaptionMetadata(BaseMetadata):
    """Metadata for table captions"""
    type: Literal["table_caption"] = "table_caption"
    caption: str
    table_id: str
    csv_path: str
    peminatan: Optional[str] = None  # TM (Teknik Mesin) or TI (Teknik Industri)


class TableRowMetadata(BaseMetadata):
    """Metadata for table rows"""
    type: Literal["table_row"] = "table_row"
    caption: str
    table_id: str
    csv_path: str
    row_index: int
    peminatan: Optional[str] = None


class TableCellMetadata(BaseMetadata):
    """Metadata for table cells (not in Filter enum but exists in data)"""
    type: Literal["table_cell"] = "table_cell"
    caption: str
    table_id: str
    csv_path: str
    row_index: int
    col_index: int
    row_data: str
    peminatan: Optional[str] = None


class TendikMetadata(BaseMetadata):
    """Metadata for TENDIK (staff/faculty) documents"""
    type: Literal["tendik"] = "tendik"
    caption: str
    csv_path: str
    group_id: str
    row_index: int
    source: str  # "docx" or other source types
    token_count: int
    level: Optional[str] = None

    # pair: [image_path, person_name] for single person
    pair: Optional[List[str]] = None

    # pairs: [[image_path, person_name], ...] for multiple people in same row
    pairs: Optional[List[List[str]]] = None


# Union type for all metadata types
ChromaMetadata = Union[
    TextMetadata,
    ImageMetadata,
    TableCaptionMetadata,
    TableRowMetadata,
    TableCellMetadata,
    TendikMetadata
]


class ChromaDocument(BaseModel):
    """Complete ChromaDB document structure"""
    content: str
    meta: ChromaMetadata


class BatchRelevanceResponse(BaseModel):
    """Response from batch relevance checking (indoclimate pattern)"""
    rationale: str = Field(..., description="Explanation of why documents were selected or rejected")
    ids: List[int] = Field(..., description="List of relevant document tag numbers [1, 3, 5]")


# Type mapping for runtime type determination
METADATA_TYPE_MAP = {
    Filter.TEXT.value: TextMetadata,
    Filter.IMAGE.value: ImageMetadata,
    Filter.CAP_TAB.value: TableCaptionMetadata,
    Filter.ROW_TAB.value: TableRowMetadata,
    "table_cell": TableCellMetadata,
    Filter.TENDIK.value: TendikMetadata,
}


def parse_chroma_metadata(metadata_dict: dict) -> ChromaMetadata:
    """Parse raw metadata dict into appropriate Pydantic model"""
    doc_type = metadata_dict.get("type")
    if not doc_type:
        raise ValueError("Metadata missing 'type' field")

    metadata_class = METADATA_TYPE_MAP.get(doc_type)
    if not metadata_class:
        raise ValueError(f"Unknown document type: {doc_type}")

    return metadata_class(**metadata_dict)
