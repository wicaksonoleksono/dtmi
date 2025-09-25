# app/utils.py
import re
import json
import os
import csv
import base64
import mimetypes
from pathlib import Path
from typing import List, Dict, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from pathlib import Path
import pandas as pd
import json


# def csv_to_markdown(csv_path: str) -> dict:
#     p = Path(csv_path)
#     if not p.exists():
#         return {}
#     return pd.read_csv(p).to_dict(orient="split")
def csv_to_markdown(csv_path: str) -> str:
    """
    Convert a CSV into JSONL where each line represents a ROW:
    {"<col1>": "<val11>", "<col2>": "<val21>", ...}
    - All values coerced to strings
    - Empty cells become ""
    """
    p = Path(csv_path)
    if not p.exists():
        raise ValueError(f"CSV file does not exist: {csv_path}")

    try:
        df = pd.read_csv(p).fillna("").astype(str)  # ensure strings
    except Exception as e:
        raise ValueError(f"Failed to read CSV file {csv_path}: {e}")

    records = df.to_dict(orient="records")  # row-wise dicts
    lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
    return "\n".join(lines)


def _deduplicate_and_join_text(docs, sep=" ") -> str:
    """
    Deduplicate and join text chunks with overlap detection and proper grammar.
    Uses regex to detect and remove overlapping text between adjacent chunks.
    """
    if not docs:
        return ""

    if len(docs) == 1:
        text = docs[0].page_content.strip()
        return ' '.join(text.split())
    # Process chunks with overlap detection
    processed_chunks = []
    for i, doc in enumerate(docs):
        current_text = ' '.join(doc.page_content.strip().split())

        if not current_text:
            continue

        if i == 0:
            processed_chunks.append(current_text)
        else:
            prev_text = processed_chunks[-1]
            merged = _merge_with_overlap_detection(prev_text, current_text)
            if merged != prev_text:
                # Replace the last chunk with merged version
                processed_chunks[-1] = merged
            else:
                # No overlap found, add as separate chunk
                processed_chunks.append(current_text)

    # Join all processed chunks
    joined = sep.join(processed_chunks)
    joined = re.sub(r'\s+', ' ', joined)  # Multiple spaces -> single space
    joined = re.sub(r'\.+', '.', joined)  # Multiple periods -> single period
    joined = re.sub(r'\s+\.', '.', joined)  # Space before period -> remove space

    return joined.strip()


def _merge_with_overlap_detection(text1: str, text2: str, chunk_stride: int = 10) -> str:
    """
    Token-based overlap detection using the same sliding window logic as the original chunker.

    Uses tiktoken tokenization to find systematic overlaps based on CHUNK_STRIDE.

    Examples:
    - Chunks with 10-token overlap: merge by removing duplicate tokens
    - "Program Educational Objectives (PEO" + "O), di mana" → "(PEO), di mana" 
    - "Pro" + "ri termanifestasi" → "Profil termanifestasi"
    """
    if not text1 or not text2:
        return text1 + " " + text2 if text1 and text2 else text1 or text2

    text1 = text1.strip()
    text2 = text2.strip()

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")

        # Tokenize both texts
        tokens1 = enc.encode(text1)
        tokens2 = enc.encode(text2)

        # Look for token-level overlap at the boundary
        # Check various overlap sizes around the expected CHUNK_STRIDE
        max_check = min(len(tokens1), len(tokens2), chunk_stride * 2)  # Check up to 2x stride

        for overlap_len in range(max_check, 1, -1):  # Start from largest possible overlap
            # Get suffix of text1 and prefix of text2
            tokens1_suffix = tokens1[-overlap_len:]
            tokens2_prefix = tokens2[:overlap_len]

            # Exact token match
            if tokens1_suffix == tokens2_prefix:
                # Merge by combining tokens1 + tokens2[overlap_len:]
                merged_tokens = tokens1 + tokens2[overlap_len:]
                return enc.decode(merged_tokens)

        # Check for partial word reconstruction at token boundaries
        # This handles cases like "Pro" + "ri termanifestasi"
        if len(tokens1) >= 2 and len(tokens2) >= 2:
            # Get the last few tokens from text1 and first few from text2
            for i in range(1, min(5, len(tokens1), len(tokens2))):  # Check 1-4 token combinations
                # Try combining last i tokens from text1 with first j tokens from text2
                for j in range(1, min(10, len(tokens2))):
                    partial_tokens = tokens1[-i:] + tokens2[:j]
                    partial_text = enc.decode(partial_tokens).strip()

                    # Check if this partial combination appears at the start of text2
                    if text2.lower().startswith(partial_text.lower()) and len(partial_text) >= 4:
                        # Found a word that spans the boundary
                        # Reconstruct: text1[:-i] + text2
                        remaining_tokens1 = tokens1[:-i]
                        reconstructed_tokens = remaining_tokens1 + tokens2
                        return enc.decode(reconstructed_tokens)

    except ImportError:
        # Fall back to character-based if tiktoken not available
        pass
    except Exception:
        # Any tokenization error, fall back to simple concat
        pass

    # No systematic overlap found, simple concatenation
    return text1 + " " + text2


def _calculate_text_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings using character overlap."""
    if not str1 or not str2:
        return 0.0

    # Remove common words and focus on meaningful content
    from difflib import SequenceMatcher
    return SequenceMatcher(None, str1, str2).ratio()


def to_static_url(relative_path):
    """Convert ./app/static/csv/file.csv to /static/file.csv"""
    if relative_path and relative_path.startswith('./app/static/'):
        filename = relative_path.split('/')[-1]  # Just get the filename
        return f"/static/{filename}"
    return relative_path


# ==============================================
# LEGACY UTILITY FUNCTIONS FOR BASE64 & CSV
# ==============================================

def load_image_base64(image_path: str, image_caption: str) -> Dict[str, Any]:
    """Load image and convert to base64 - from legacy code"""
    if not image_path:
        print(f"[Image Load Error] No image_path provided for caption: {image_caption}")
        return {
            'path': image_path,
            'filename': 'Unknown',
            'caption': 'Image file not found',
            'error': True,
            'error_message': 'No image path provided'
        }

    if not os.path.exists(image_path):
        print(f"[Image Load Error] File not found: {image_path}")
        return {
            'path': image_path,
            'filename': os.path.basename(image_path),
            'caption': 'Image file not found',
            'error': True,
            'error_message': 'File does not exist'
        }

    try:
        file_size = os.path.getsize(image_path)

        # 10MB limit
        if file_size > 10 * 1024 * 1024:
            print(f"[Image Load Error] File too large: {image_path} ({file_size / (1024*1024):.2f}MB)")
            return {
                'path': image_path,
                'filename': os.path.basename(image_path),
                'caption': 'Image file too large (>10MB)',
                'error': True,
                'size': file_size,
                'error_message': 'File too large'
            }

        # Get MIME type
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type or not mime_type.startswith('image/'):
            ext = os.path.splitext(image_path.lower())[1]
            mime_map = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'
            }
            mime_type = mime_map.get(ext, 'image/jpeg')  # Default to jpeg if unknown
            if not mime_type.startswith('image/'):  # If still not an image type
                print(f"[Image Load Error] Unsupported MIME type for {image_path}: {mime_type}")
                return {
                    'path': image_path,
                    'filename': os.path.basename(image_path),
                    'caption': 'Unsupported image format',
                    'error': True,
                    'error_message': f'Unsupported MIME type: {mime_type}'
                }

        # Read and encode
        with open(image_path, 'rb') as f:
            image_binary = f.read()
            image_base64 = base64.b64encode(image_binary).decode('utf-8')

        print(f"[Image Load Success] Loaded {image_path}")
        return {
            'path': image_path,
            'filename': os.path.basename(image_path),
            'caption': image_caption or 'Image loaded successfully',
            'data': image_base64,
            'mime_type': mime_type,
            'size': file_size,
            'data_url': f"data:{mime_type};base64,{image_base64}"
        }

    except Exception as e:
        print(f"[Image Load Exception] Error processing {image_path}: {e}")
        return {
            'path': image_path,
            'filename': os.path.basename(image_path),
            'caption': 'Error loading image',
            'error': True,
            'error_message': str(e)
        }


def parse_csv_file(csv_path: str, csv_caption: str, max_rows: int = 50) -> Dict[str, Any]:
    """Parse CSV file - from legacy code"""
    try:
        with open(csv_path, 'r', encoding='utf-8', newline='') as file:
            # Detect CSV format
            sample = file.read(2048)
            file.seek(0)

            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample, delimiters=',;\t|')
                has_header = sniffer.has_header(sample)
            except:
                dialect = csv.excel
                has_header = True

            if has_header:
                reader = csv.DictReader(file, dialect=dialect)
                rows = []
                headers = None

                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    if headers is None:
                        headers = list(row.keys())
                    rows.append([str(row.get(header, '')).strip() for header in headers])
            else:
                reader = csv.reader(file, dialect=dialect)
                all_rows = [row for i, row in enumerate(reader) if i < max_rows]

                if not all_rows:
                    headers = ['No Data']
                    rows = [['Empty CSV file']]
                else:
                    num_cols = len(all_rows[0])
                    headers = [f'Column {i+1}' for i in range(num_cols)]
                    rows = all_rows

            # Normalize row lengths
            if headers:
                formatted_rows = []
                for row in rows:
                    while len(row) < len(headers):
                        row.append('')
                    formatted_row = [str(cell).strip() if cell else '' for cell in row[:len(headers)]]
                    formatted_rows.append(formatted_row)

                return {
                    'filename': os.path.basename(csv_path),
                    'caption': csv_caption or os.path.basename(csv_path),
                    'headers': headers,
                    'rows': formatted_rows,
                    'showing_rows': len(formatted_rows)
                }

            return {
                'filename': os.path.basename(csv_path),
                'caption': csv_caption or 'Empty file',
                'headers': ['No Data'],
                'rows': [['Empty CSV file']]
            }

    except Exception as e:
        return {
            'filename': os.path.basename(csv_path),
            'caption': csv_caption or 'Error processing file',
            'headers': ['Error'],
            'rows': [[f'Failed to parse: {str(e)}']]
        }


def process_images(image_paths: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Process multiple images in parallel - from legacy code"""
    if not image_paths:
        return []

    processed_images = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_image = {
            executor.submit(load_image_base64, image_path, image_caption): (image_path, image_caption)
            for image_path, image_caption in image_paths if image_path
        }

        for future in as_completed(future_to_image):
            image_path, image_caption = future_to_image[future]
            try:
                image_data = future.result(timeout=10)
                processed_images.append(image_data)
            except Exception as e:
                processed_images.append({
                    'path': image_path,
                    'filename': os.path.basename(image_path),
                    'caption': 'Error loading image',
                    'error': True,
                    'error_message': str(e)
                })

    return processed_images


def process_csv_files(csv_paths: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Process multiple CSV files in parallel - from legacy code"""
    if not csv_paths:
        return []

    csv_tables = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_csv = {
            executor.submit(parse_csv_file, csv_path, csv_caption): (csv_path, csv_caption)
            for csv_path, csv_caption in csv_paths if csv_path
        }

        for future in as_completed(future_to_csv):
            csv_path, csv_caption = future_to_csv[future]
            try:
                table_data = future.result(timeout=30)
                csv_tables.append(table_data)
            except Exception as e:
                csv_tables.append({
                    'filename': os.path.basename(csv_path),
                    'caption': csv_caption or 'Error processing file',
                    'headers': ['Error'],
                    'rows': [[f'Failed to parse: {str(e)}']]
                })

    return csv_tables


def extract_references(metadatas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract references from metadata - from legacy code"""
    if not metadatas or not isinstance(metadatas, list):
        return []

    references = []
    for metadata in metadatas:
        if isinstance(metadata, dict):
            ref = {}

            # Extract reference fields
            field_mappings = {
                'chapter': 'chapter',
                'section': 'section',
                'subsection': 'subsection',
                'page': ['page', 'page_number'],
                'section_title': ['section_title', 'title']
            }

            for key, sources in field_mappings.items():
                if isinstance(sources, str):
                    sources = [sources]

                for source in sources:
                    if source in metadata and metadata[source]:
                        ref[key] = str(metadata[source])
                        break

            if ref:
                references.append(ref)

    return references
