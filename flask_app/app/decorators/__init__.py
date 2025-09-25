"""
Decorator package for clean error handling and response formatting
"""

from .chat_decorators import (
    handle_chat_errors,
    handle_webhook_errors,
    validate_chat_input,
    format_chat_response,
    handle_native_streaming_response
)

from .gen_decorators import (
    handle_service_errors,
    measure_performance,
    validate_inputs,
    cache_result,
    ok_ok as ok,
    bad_bad as bad,
    info_info as info
)

__all__ = [
    # Chat-specific decorators
    'handle_chat_errors',
    'handle_webhook_errors',
    'validate_chat_input',
    'format_chat_response',
    'handle_native_streaming_response',

    # General service decorators
    'handle_service_errors',
    'measure_performance',
    'validate_inputs',
    'cache_result',

    # Logging functions
    'ok', 'bad', 'info'
]
