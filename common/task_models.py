"""UI-independent task request and result contracts."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class TaskCallbacks:
    log: Callable[[str], None]
    status: Callable[[str], None]
    error: Callable[[str], None]
    confirm: Optional[Callable[[str], bool]] = None
    finished: Optional[Callable[[], None]] = None
    info: Optional[Callable[[str], None]] = None
    warning: Optional[Callable[[str], None]] = None


@dataclass
class TaskResult:
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeedrawFieldRequest:
    code: str
    config_path: str
    upload_pc_image: bool
    fill_pc_value: bool
    upload_mobile_image: bool
    fill_mobile_value: bool
    overwrite_existing: bool = False
    skip_existing: bool = False
    modify_only: bool = False
    rename_option: bool = False


@dataclass(frozen=True)
class DeedrawTaskRequest:
    fields: List[DeedrawFieldRequest]
    settings: Dict[str, Any]


@dataclass(frozen=True)
class PimTaskRequest:
    config_path: str
    fill_pc_value: bool
    fill_mobile_value: bool
    upload_pc_image: bool
    upload_mobile_image: bool
    preset_module: bool
    pixel_size: str


class TaskCancelled(Exception):
    """Cooperative cancellation, distinct from a business failure."""
