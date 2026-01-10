
import functools
import asyncio
import time
from typing import Any, Callable, Optional
from ..model.response_models import ProcessingStats


# Global logging functions


def ok_ok(msg: str):
    formatted = f"[OLKOREKT]: {msg}"
    print(formatted)
    return formatted


def bad_bad(msg: str):
    formatted = f"[SNAFU]: {msg}"
    print(formatted)
    return formatted


def info_info(msg: str):
    formatted = f"[FAFO]:{msg}"
    print(formatted)
    return formatted


class msghandler:
    def __init__(self):
        self.msg = []

    def info(self, msg: str):
        formatted = info_info(formatted)
        print(formatted)
        self.msg.append(formatted)

    def ok(self, msg: str):
        formatted = ok_ok(msg)  # uses global ok() for printing
        self.msg.append(formatted)
        return formatted

    def bad(self, msg: str):
        formatted = bad_bad(msg)  # uses global bad() for printing
        self.msg.append(formatted)
        return formatted

    def get_msg(self):
        return self.msg


def handle_service_errors(
    default_return: Any = None,
    log_errors: bool = True,
    service_name: str = "Service"
):
    """
    Decorator for handling service errors consistently
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    bad_bad(f"{service_name} error in {func.__name__}: {e}")
                if default_return is not None:
                    return default_return
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    bad_bad(f"{service_name} error in {func.__name__}: {e}")
                if default_return is not None:
                    return default_return
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def measure_performance(include_stats: bool = True):
    """
    Decorator for measuring performance
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time

            if include_stats and isinstance(result, dict):
                if 'processing_stats' not in result:
                    result['processing_stats'] = ProcessingStats(
                        total_time=elapsed
                    ).to_dict()
                else:
                    result['processing_stats']['total_time'] = elapsed

            print(f"[Performance] {func.__name__}: {elapsed:.3f}s")
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time

            print(f"[Performance] {func.__name__}: {elapsed:.3f}s")
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def validate_inputs(
    required_params: Optional[list] = None,
    param_types: Optional[dict] = None
):
    """
    Decorator for input validation
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get function signature for parameter names
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Check required parameters
            if required_params:
                for param in required_params:
                    if param not in bound_args.arguments or bound_args.arguments[param] is None:
                        raise ValueError(f"Required parameter '{param}' is missing or None")

            # Check parameter types
            if param_types:
                for param, expected_type in param_types.items():
                    if param in bound_args.arguments:
                        value = bound_args.arguments[param]
                        if value is not None and not isinstance(value, expected_type):
                            raise TypeError(
                                f"Parameter '{param}' must be of type {expected_type.__name__}, got {type(value).__name__}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


def cache_result(cache_key_func: Callable = None, ttl_seconds: int = 300):
    """
    Simple caching decorator
    """
    cache = {}

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            if cache_key_func:
                key = cache_key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}_{hash(str(args) + str(sorted(kwargs.items())))}"
            if key in cache:
                cached_time, cached_result = cache[key]
                if time.time() - cached_time < ttl_seconds:
                    print(f"[Cache] Hit for {func.__name__}")
                    return cached_result
            result = await func(*args, **kwargs)
            cache[key] = (time.time(), result)
            print(f"[Cache] Stored for {func.__name__}")
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Same logic for sync functions
            if cache_key_func:
                key = cache_key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}_{hash(str(args) + str(sorted(kwargs.items())))}"

            if key in cache:
                cached_time, cached_result = cache[key]
                if time.time() - cached_time < ttl_seconds:
                    print(f"[Cache] Hit for {func.__name__}")
                    return cached_result

            result = func(*args, **kwargs)
            cache[key] = (time.time(), result)
            print(f"[Cache] Stored for {func.__name__}")
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
