"""Agent Memory"""

from enum import StrEnum
from typing import Any, Callable, Optional
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class MemoryPolicyType(StrEnum):
    """Memory policy"""

    NULL = "null"
    """Null policy"""

    ROLLING_WINDOW = "rolling_window"
    """Rolling window policy"""

    SUMMARIZE = "summarize"
    """Summarize older messages into a compact summary while keeping recent ones"""

    CUSTOM = "custom"
    """Custom policy"""


class MemoryConfig(BaseModel):
    """Memory config"""

    model_config = ConfigDict(extra="allow")

    policy: MemoryPolicyType = MemoryPolicyType.ROLLING_WINDOW
    """Memory policy"""

    window: int = 10
    """Memory window"""

    summary_max_chars: int = 1000
    """Maximum characters to keep in auto-generated summaries (for SUMMARIZE policy)"""

    callable: Optional[Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] = None
    """Memory callable"""


class MemoryManager:
    """Memory"""

    def __init__(self, config: MemoryConfig | None = None, **kwargs):
        """Initialize the memory manager"""
        if config is None:
            config = MemoryConfig(**kwargs)
        self.policy = config.policy
        self.window = config.window
        self.summary_max_chars = config.summary_max_chars
        self.callable = config.callable
        self.memory: list[dict[str, Any]] = []

    def add_message(self, message: dict[str, Any]):
        """Add a message to the memory"""
        if self.policy == MemoryPolicyType.ROLLING_WINDOW:
            self.memory.append(message)
            if len(self.memory) > self.window:
                self.memory.pop(0)
        elif self.policy == MemoryPolicyType.NULL:
            pass
        elif self.policy == MemoryPolicyType.SUMMARIZE:
            # Keep a rolling window, but compress older messages into a single summary entry
            self.memory.append(message)
            if len(self.memory) > self.window:
                # Split into older and recent segments
                recent_to_keep = max(self.window - 1, 0)
                older_messages = self.memory[: max(len(self.memory) - recent_to_keep, 0)]
                recent_messages = self.memory[-recent_to_keep:] if recent_to_keep > 0 else []

                # If a callable is provided, let it produce the summarized memory list
                # The callable should accept the full memory and return the new list
                if self.callable:
                    self.memory = self.callable(self.memory)
                    return

                # Default simple summarization strategy: concatenate text-like fields
                def extract_text(m: dict[str, Any]) -> str:
                    content = m.get("content")
                    if isinstance(content, str):
                        return content
                    # Fallback to stringified message if no string content
                    return str(content) if content is not None else str(m)

                summary_text = "\n\n".join(extract_text(m) for m in older_messages)
                if len(summary_text) > self.summary_max_chars:
                    summary_text = summary_text[: self.summary_max_chars].rstrip() + "…"

                summary_message = {
                    "role": "system",
                    "content": f"Summary of earlier context (compressed):\n\n{summary_text}",
                }

                self.memory = [summary_message] + recent_messages
        elif self.policy == MemoryPolicyType.CUSTOM:
            if self.callable:
                self.memory = self.callable(self.memory)
        else:
            raise ValueError(f"Invalid policy: {self.policy}")

    # Persistence / Export APIs
    def export_to_dict(self) -> dict[str, Any]:
        """Export memory state and configuration to a serializable dict."""
        return {
            "policy": str(self.policy),
            "window": self.window,
            "summary_max_chars": self.summary_max_chars,
            # callable is not serialized (non-serializable function)
            "memory": list(self.memory),
        }

    def save(self, file_path: str | Path) -> None:
        """Save memory state to a JSON file.

        The file contains both the configuration and the memory messages.
        """
        path = Path(file_path)
        data = self.export_to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, file_path: str | Path) -> None:
        """Load memory state from a JSON file.

        Accepts either the full export dict format or a plain list of messages.
        """
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Support both formats: { ... , "memory": [...] } or just [...]
        if isinstance(data, dict) and "memory" in data:
            loaded_memory = data.get("memory", [])
            if isinstance(data.get("window"), int):
                self.window = int(data["window"])
            if isinstance(data.get("summary_max_chars"), int):
                self.summary_max_chars = int(data["summary_max_chars"])
            # policy may be string; keep current if invalid
            policy_value = data.get("policy")
            if isinstance(policy_value, str):
                try:
                    self.policy = MemoryPolicyType(policy_value)
                except ValueError:
                    pass
        else:
            loaded_memory = data

        if not isinstance(loaded_memory, list):
            raise ValueError("Loaded memory must be a list of messages")
        # Shallow-validate entries are dict-like
        sanitized: list[dict[str, Any]] = []
        for m in loaded_memory:
            if isinstance(m, dict):
                sanitized.append(m)
            else:
                sanitized.append({"role": "system", "content": str(m)})
        self.memory = sanitized
