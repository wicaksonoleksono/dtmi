"""
Model package for deterministic dataclasses
"""

from .interfaces import (
    IQueryProcessor, IContextManager,
    IPromptBuilder, IFilterProcessor
)
from .response_models import (
    FilterInfo, ProcessingStats, ContextInfo,
    RAGResult, SimpleResponse
)
from .ref_models import (CsvTable,
                         ProcessedImage,
                         Reference,
                         QueryResponse,
                         WebhookResponse,
                         ContextInfo,
                         HealthResponse,)
from .enums import Year, Filter
__all__ = [
    'FilterInfo', 'ProcessingStats', 'ContextInfo',
    'RAGResult', 'SimpleResponse', 'Year', 'Filter',
    'CsvTable',
    'ProcessedImage', 'Reference', 'QueryResponse', 'WebhookResponse', 'ContextInfo', 'HealthResponse',
    'IQueryProcessor', 'IContextManager',
    'IPromptBuilder', 'IFilterProcessor',

    # Decorators
    'handle_service_errors', 'measure_performance',
    'validate_inputs', 'cache_result',
]
