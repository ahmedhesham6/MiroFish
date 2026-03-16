"""
Plugin executor: run plugin methods with timeout isolation and error capture.
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PluginResult:
    """Result of a plugin method execution."""

    success: bool
    data: Any
    error: Optional[str]
    elapsed_ms: float


class PluginExecutor:
    """Executes plugin methods in an isolated thread with timeout enforcement."""

    def execute(
        self,
        plugin: Any,
        method_name: str,
        timeout_sec: float = 30.0,
        **kwargs: Any,
    ) -> PluginResult:
        """Call plugin.<method_name>(**kwargs) with a timeout.

        Args:
            plugin: An instantiated plugin object.
            method_name: Name of the method to call on the plugin.
            timeout_sec: Maximum seconds to wait for the method to return.
            **kwargs: Arguments forwarded to the plugin method.

        Returns:
            PluginResult with success/failure, return value or error message, and elapsed time.
        """
        method = getattr(plugin, method_name, None)
        if method is None:
            return PluginResult(
                success=False,
                data=None,
                error=f"Plugin {type(plugin).__name__!r} has no method {method_name!r}",
                elapsed_ms=0.0,
            )

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(method, **kwargs)
            try:
                result = future.result(timeout=timeout_sec)
                elapsed_ms = (time.monotonic() - start) * 1000
                return PluginResult(success=True, data=result, error=None, elapsed_ms=elapsed_ms)
            except FuturesTimeoutError:
                elapsed_ms = (time.monotonic() - start) * 1000
                future.cancel()
                return PluginResult(
                    success=False,
                    data=None,
                    error=f"Plugin method {method_name!r} timed out after {timeout_sec}s",
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                return PluginResult(
                    success=False,
                    data=None,
                    error=f"{type(exc).__name__}: {exc}",
                    elapsed_ms=elapsed_ms,
                )
