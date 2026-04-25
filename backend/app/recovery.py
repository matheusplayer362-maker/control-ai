from __future__ import annotations

import time
from functools import wraps
from typing import Callable


def with_retries(retries: int = 3, delay: float = 0.8) -> Callable:
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            wait = delay
            for _ in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    time.sleep(wait)
                    wait *= 1.7
            if last_error:
                raise last_error
            raise RuntimeError("retry wrapper failure")

        return wrapper

    return decorator
