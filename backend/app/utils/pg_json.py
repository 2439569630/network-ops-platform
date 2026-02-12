import json
from typing import Any, Optional


def jsonb_param(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return json.dumps(value, ensure_ascii=False, default=str)
