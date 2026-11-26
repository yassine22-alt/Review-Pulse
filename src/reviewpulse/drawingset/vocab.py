"""Loads vocab.yaml and compiles it into matchers. No language or trade word is written in code."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

VOCAB_PATH = Path(__file__).with_name("vocab.yaml")


def fold(text: str) -> str:
    """Lower case, no accents, German sharp s written ss, typographic quotes and dashes made plain, spaces collapsed."""
    t = text.replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    for a, b in (("″", '"'), ("”", '"'), ("“", '"'), ("′", "'"), ("’", "'"), ("‘", "'"),
                 ("\u2013", "-"), ("\u2014", "-"), ("−", "-"), (" ", " ")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().lower()


def plain(text: str) -> str:
    """Same as fold but keeps case (for patterns that need capital letters, such as sheet ids)."""
    t = text.replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    for a, b in (("″", '"'), ("”", '"'), ("“", '"'), ("′", "'"), ("’", "'"), ("‘", "'"),
                 ("\u2013", "-"), ("\u2014", "-"), ("−", "-"), (" ", " ")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def _alt(words: list[str]) -> str:
    """Alternation of folded words, longest first, tolerant to a final dot, spaces inside a phrase flexible."""
    ws = sorted({fold(w) for w in words}, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(w).replace(r"\ ", r"[\s.-]*") for w in ws) + r")\.?"


@dataclass
class Vocab:
    raw: dict
    kind_priority: list[str]
    kind_regex: dict[str, re.Pattern]
    level_words: list[tuple[str, int, re.Pattern]]
    level_ordinals: list[re.Pattern]
    ordinal_words: dict[str, int]
    scale_patterns: list[tuple[str, re.Pattern, str]]
    scale_slash: re.Pattern
    scale_label: re.Pattern
    no_scale: re.Pattern
    letter_id: re.Pattern
    number_id: re.Pattern
    label_regex: dict[str, re.Pattern]
    grammars: list[tuple[str, re.Pattern]]
    callout_kinds: dict[str, re.Pattern]
    ref_regex: re.Pattern
    sheet_word_regex: re.Pattern
    view_label: re.Pattern
    extra: dict = field(default_factory=dict)


def _whole(words: list[str]) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + _alt(words) + r"(?![a-z0-9])")


@lru_cache(maxsize=4)
def load_vocab(path: str | None = None) -> Vocab:
    raw = yaml.safe_load(Path(path or VOCAB_PATH).read_text(encoding="utf-8"))
    kind_regex = {k: _whole(v) for k, v in raw["view_kinds"].items()}
    levels = [(lv["label"], int(lv["rank"]), _whole(lv["words"])) for lv in raw["levels"]]
    ordinals = [re.compile(p) for p in raw["level_ordinals"]]
    sc = raw["scale"]
    pats = [(p["name"], re.compile(fold_regex(p["regex"]), re.I), p["system"]) for p in sc["patterns"]]
    labels = {k: _whole(v) for k, v in raw["title_block_labels"].items()}
    sid = raw["sheet_id"]
    sheet_words = _alt(raw["sheet_words"])
    ref_words = _alt(raw["ref_words"])
    kinds_all = [w for ws in raw["callout_kind_words"].values() for w in ws]
    sub = {
        "view": raw["view_label"], "view_num": r"\d{1,2}", "sheet": sid["letter_id"],
        "sheet_any": f"(?:{sid['letter_id']}|{sid['number_id']})", "kinds": _alt(kinds_all),
        "sheetwords": sheet_words, "refwords": ref_words,
    }
    grammars = []
    for g in raw["grammars"]:
        tpl = g["template"].replace("{{", "\x00").replace("}}", "\x01")
        for k, v in sub.items():
            tpl = tpl.replace("{" + k + "}", v)
        tpl = tpl.replace("\x00", "{").replace("\x01", "}")
        grammars.append((g["name"], re.compile(tpl, re.I)))
    return Vocab(
        raw=raw, kind_priority=raw["kind_priority"], kind_regex=kind_regex, level_words=levels, level_ordinals=ordinals,
        ordinal_words=raw["ordinal_words"], scale_patterns=pats,
        scale_slash=re.compile(raw["scale"]["ratio_slash"]),
        scale_label=_whole(sc["labels"]), no_scale=_whole(sc["no_scale"]),
        letter_id=re.compile(r"^(?:" + sid["letter_id"] + r")$"), number_id=re.compile(r"^(?:" + sid["number_id"] + r")$"),
        label_regex=labels, grammars=grammars,
        callout_kinds={k: _whole(v) for k, v in raw["callout_kind_words"].items()},
        ref_regex=re.compile(ref_words), sheet_word_regex=re.compile(sheet_words),
        view_label=re.compile(r"^(?:" + raw["view_label"] + r")$", re.I),
    )


def fold_regex(rx: str) -> str:
    return rx


def norm_id(token: str) -> str:
    """Sheet or view number made comparable: upper case, letters and digits only ("A-501", "a5.01" -> "A501")."""
    return re.sub(r"[^A-Z0-9]", "", plain(token).upper())


def shape(token: str) -> str:
    """Shape of a sheet number: letters become A, digits 9, separators stay ("A3.01" -> "A9.99", "S2" -> "A9")."""
    t = plain(token).upper().replace(" ", "")
    return re.sub(r"[0-9]", "9", re.sub(r"[A-Z]", "A", t))
