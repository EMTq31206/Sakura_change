from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _converter():  # type: ignore[no-untyped-def]
    try:
        from opencc import OpenCC
    except ImportError:
        return None
    return OpenCC("t2s")


def to_simplified_chinese(text: str) -> str:
    converter = _converter()
    if converter is None or not text:
        return text
    return str(converter.convert(text))
