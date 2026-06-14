from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def load_lore(lore_path: Path) -> str:
    if not lore_path.is_file():
        return ""
    return lore_path.read_text(encoding="utf-8")


def _split_sections(lore_text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = ""
    current_text: list[str] = []
    for line in lore_text.split("\n"):
        if line.startswith("## "):
            if current_title and current_text:
                sections.append({"title": current_title, "text": "\n".join(current_text).strip()})
            current_title = line[3:].strip()
            current_text = []
        elif current_title:
            current_text.append(line)
    if current_title and current_text:
        sections.append({"title": current_title, "text": "\n".join(current_text).strip()})
    return sections


def _build_keyword_index(sections: list[dict[str, str]]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    keywords_pool = {
        "槐", "槐くん", "崩月", "先輩", "会長", "生徒会", "学園",
        "B.E.G.", "BEG", "ウィドウ", "瓦礫", "停止", "反現実", "怪獣", "戦闘", "能力", "任務",
        "結婚", "新婚", "式", "指輪", "誓い", "家族", "子供", "未来",
        "デート", "散歩", "料理", "キス", "触れる", "抱き", "夜",
        "死", "殺", "薬", "注射", "命", "犠牲", "守る", "救う",
        "ソフイ", "華淡", "水仙", "N.A.V.I.", "ナビ",
        "学園祭", "文化祭", "クリスマス", "イベント",
        "グランド", "真結局", "大団円", "最終", "最期", "エピローグ",
        "共通", "華淡", "ソフィ", "水仙", "ランカスター",
        "マシュー", "ブラン", "黒列車", "森道", "ポータル", "次元",
        "暗殺", "任務", "崩月家", "恒常性", "ダンスノーツ",
        "幼少", "訓練", "父親", "母親", "妹", "家族",
        "クリスマス", "プレゼント", "サンタ",
    }
    for i, section in enumerate(sections):
        combined = section["title"] + " " + section["text"]
        combined_lower = combined.lower()
        for kw in keywords_pool:
            if kw.lower() in combined_lower:
                index.setdefault(kw, []).append(i)
    return index


class CharacterLore:
    def __init__(self, lore_path: Path) -> None:
        self.lore_text = load_lore(lore_path)
        self.sections = _split_sections(self.lore_text)
        self.index = _build_keyword_index(self.sections)

    def search(self, query: str, max_sections: int = 5) -> str:
        """Search lore for sections relevant to the query."""
        if not self.sections:
            return ""

        matched_indices: set[int] = set()
        query_lower = query.lower()

        for keyword, indices in self.index.items():
            if keyword.lower() in query_lower:
                matched_indices.update(indices[:5])

        if not matched_indices:
            return ""

        results: list[str] = []
        for idx in list(matched_indices)[:max_sections]:
            section = self.sections[idx]
            text = section["text"]
            if len(text) > 3000:
                text = text[:3000] + "\n..."
            results.append(f"【{section['title']}】\n{text}")

        if not results:
            return ""

        header = (
            "【桜の記憶·参考用】以下は桜の原作経験です。"
            "自然に会話に織り込んでください。"
            "このテキストをそのまま引用·復唱してはいけません。\n\n"
        )
        return header + "\n\n---\n\n".join(results)

    def has_content(self) -> bool:
        return len(self.sections) > 0


_lore_cache: dict[str, CharacterLore] = {}


def get_character_lore(character_dir: Path) -> CharacterLore | None:
    key = str(character_dir.resolve())
    if key in _lore_cache:
        return _lore_cache[key]
    lore_path = character_dir / "lore.md"
    if not lore_path.is_file():
        return None
    lore = CharacterLore(lore_path)
    _lore_cache[key] = lore
    return lore
