"""I1 - Rule format.

A rule is YAML validated by Pydantic plus the controlled vocabulary. An LLM may
draft rules, but only by choosing from the vocabulary and the function
registry, and a rule runs only once a curator sets ``status: approved``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VOCAB_PATH = Path(__file__).with_name("vocab.yaml")


@lru_cache(maxsize=1)
def vocab() -> dict:
    return yaml.safe_load(VOCAB_PATH.read_text(encoding="utf-8"))


class RuleError(ValueError):
    pass


class Check(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    fn: str
    op: str | None = None
    value: Any | None = None
    unit: str | None = None
    tolerance_m: float | None = None
    tolerance_rel: float | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    via_edges: list[str] | None = None
    avoid: dict | None = None


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    doc: str
    clause: str | None = None
    span: list[int] | None = None


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    title: str
    family: Literal["C", "K", "P", "Q"]
    cls: Literal["threshold", "derived", "count", "traversal", "cross_reference", "arithmetic", "presence"] = Field(alias="class")
    applies_to: dict = Field(default_factory=dict)
    check: Check
    severity: Literal["critical", "major", "minor", "info"]
    needs: list[str] = []
    source: Source
    message: str
    status: Literal["draft", "approved", "rejected"] = "draft"
    version: int = 1
    approved_by: str | None = None
    params: dict = Field(default_factory=dict)
    notes: str | None = None

    @property
    def is_guidance(self) -> bool:
        return self.source.doc == "guidance"

    @field_validator("needs")
    @classmethod
    def _needs(cls, v):
        bad = [n for n in v if n not in vocab()["needs"]]
        if bad:
            raise ValueError(f"unknown needs {bad}; allowed: {vocab()['needs']}")
        return v

    @model_validator(mode="after")
    def _vocab(self):
        V = vocab()
        from .registry import REGISTRY

        if self.check.fn not in REGISTRY:
            raise ValueError(f"function {self.check.fn!r} is not in the registry")
        if self.check.op and self.check.op not in V["operators"]:
            raise ValueError(f"operator {self.check.op!r} not allowed")
        if self.check.unit and self.check.unit not in V["units"]:
            raise ValueError(f"unit {self.check.unit!r} not allowed")
        for key in ("room_type",):
            types = self.applies_to.get(key)
            if types:
                for t in [types] if isinstance(types, str) else types:
                    if t not in V["room_types"]:
                        raise ValueError(f"unknown room type {t!r}; allowed: {V['room_types']}")
        el = self.applies_to.get("element")
        if el and el not in V["element_classes"]:
            raise ValueError(f"unknown element class {el!r}")
        if self.check.avoid:
            for t in self.check.avoid.get("room_type", []):
                if t not in V["room_types"]:
                    raise ValueError(f"unknown room type in avoid: {t!r}")
        for k in self.check.via_edges or []:
            if k not in V["edge_kinds"]:
                raise ValueError(f"unknown edge kind {k!r}")
        if REGISTRY[self.check.fn].needs_scale and "scale" not in self.needs:
            self.needs = [*self.needs, "scale"]
        return self


def load_rule(path: str | Path) -> list[Rule]:
    text = Path(path).read_text(encoding="utf-8")
    out = []
    for doc in yaml.safe_load_all(text):
        if not doc:
            continue
        try:
            out.append(Rule.model_validate(doc))
        except Exception as e:  # noqa: BLE001 - re-raised with the rule id
            raise RuleError(f"{Path(path).name} / {doc.get('id', '?')}: {e}") from e
    return out


def load_pack(path: str | Path) -> list[Rule]:
    path = Path(path)
    files = [path] if path.is_file() else sorted(list(path.glob("*.yaml")) + list(path.glob("*.yml")))
    rules = []
    for f in files:
        rules += load_rule(f)
    ids = [r.id for r in rules]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise RuleError(f"duplicate rule ids: {sorted(dup)}")
    return rules


def dump_rule(rule: Rule) -> str:
    data = rule.model_dump(by_alias=True, exclude_none=True, exclude_defaults=False)
    data["check"] = rule.check.model_dump(by_alias=True, exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
