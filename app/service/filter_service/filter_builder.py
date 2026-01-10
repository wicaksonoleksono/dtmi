# app/service/filter_service/filter_builder.py

from typing import Any, Dict, List, Tuple, Optional, Union
from app.model.enums import Filter, Year


def build_filter(modalities: Union[str, List[str], None] = None,
                 year: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
    """Build MongoDB filter with correct INTERSECTION logic and always-include rules"""
    query_types = (modalities or "all").lower() if isinstance(modalities, str) else "all"
    year_key = year.upper() if year else None

    # Build type filter with TENDIK always included directly in $in array
    type_conditions = []
    if query_types == "text":
        type_conditions = [Filter.TEXT.value]
    elif query_types == "image":
        type_conditions = [Filter.IMAGE.value]
    elif query_types == "table":
        type_conditions = [Filter.ROW_TAB.value, Filter.CAP_TAB.value]
    elif query_types == "all":
        type_conditions = [Filter.TEXT.value, Filter.IMAGE.value, Filter.ROW_TAB.value, Filter.CAP_TAB.value]

    # Always include ROW_TENDIK directly in the type conditions
    if type_conditions:
        type_conditions.append(Filter.TENDIK.value)
        type_filter = {"type": {"$in": type_conditions}}
    else:
        # Fallback for empty conditions
        type_filter = {"type": {"$exists": True}}
    # Build year filter with GENERAL always included
    year_filter = None
    if year_key in [Year.YEAR_SARJANA.value, Year.YEAR_MAGISTER.value, Year.YEAR_DOKTOR.value]:
        year_filter = {
            "$or": [
                {"year": year_key},
                {"year": Year.YEAR_GENERAL.value}
            ]
        }

    # Combine filters with INTERSECTION (AND) logic
    conditions = [type_filter]
    if year_filter:
        conditions.append(year_filter)

    # Always exclude LAMPIRAN
    # conditions.append({"chapter": {"$ne": "LAMPIRAN"}})

    # Final filter structure
    final_filter = {"$and": conditions}

    # Build description
    desc_parts = []
    if query_types != "all":
        desc_parts.append(f"Types: {query_types}")
    if year_key:
        desc_parts.append(f"Year: {year_key}")
    desc_parts.append("+ TENDIK always")
    desc_parts.append("+ GENERAL always")

    filter_msg = " | ".join(desc_parts)

    return final_filter, filter_msg
