"""Load and lightly validate OSI v0.2 semantic-model YAML documents.

Stdlib-only; mirrors the structure of open-semantic-interchange/OSI/core-spec/osi-schema.json
without pulling in a full JSON-Schema validator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]

    def _parse(text: str) -> dict[str, Any]:
        return yaml.safe_load(text)
except ModuleNotFoundError:
    # Minimal YAML-via-JSON fallback so the demo runs without PyYAML.
    # Falls back to the JSON-LD examples shipped alongside the YAML.
    def _parse(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "PyYAML is not installed; install it or supply a JSON OSI document."
            ) from exc


SUPPORTED_DIALECTS = {"ANSI_SQL", "SNOWFLAKE", "MDX", "TABLEAU", "DATABRICKS", "MAQL"}


@dataclass(frozen=True)
class DialectExpression:
    dialect: str
    expression: str


@dataclass(frozen=True)
class Field:
    name: str
    expressions: list[DialectExpression]
    description: str | None = None
    is_time_dimension: bool = False
    synonyms: tuple[str, ...] = ()
    instructions: str | None = None


@dataclass(frozen=True)
class Relationship:
    name: str
    from_dataset: str
    to_dataset: str
    from_columns: tuple[str, ...]
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class Dataset:
    name: str
    source: str
    primary_key: tuple[str, ...]
    unique_keys: tuple[tuple[str, ...], ...]
    description: str | None
    synonyms: tuple[str, ...]
    fields: list[Field]


@dataclass(frozen=True)
class Metric:
    name: str
    expressions: list[DialectExpression]
    description: str | None
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class SemanticModel:
    name: str
    description: str | None
    instructions: str | None
    synonyms: tuple[str, ...]
    examples: tuple[str, ...]
    datasets: list[Dataset]
    relationships: list[Relationship]
    metrics: list[Metric]
    custom_extensions: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _ai_context_synonyms(ai_context: Any) -> tuple[str, ...]:
    if isinstance(ai_context, dict):
        return tuple(ai_context.get("synonyms", []) or [])
    return ()


def _ai_context_instructions(ai_context: Any) -> str | None:
    if isinstance(ai_context, dict):
        return ai_context.get("instructions")
    if isinstance(ai_context, str):
        return ai_context
    return None


def _ai_context_examples(ai_context: Any) -> tuple[str, ...]:
    if isinstance(ai_context, dict):
        return tuple(ai_context.get("examples", []) or [])
    return ()


def _parse_expressions(spec: dict[str, Any]) -> list[DialectExpression]:
    out: list[DialectExpression] = []
    for entry in (spec.get("expression") or {}).get("dialects") or []:
        dialect = entry.get("dialect")
        if dialect not in SUPPORTED_DIALECTS:
            raise ValueError(f"Unknown OSI dialect {dialect!r}")
        out.append(DialectExpression(dialect=dialect, expression=entry["expression"]))
    if not out:
        raise ValueError("expression.dialects[] must contain at least one entry")
    return out


def _parse_field(raw: dict[str, Any]) -> Field:
    return Field(
        name=raw["name"],
        expressions=_parse_expressions(raw),
        description=raw.get("description"),
        is_time_dimension=bool((raw.get("dimension") or {}).get("is_time", False)),
        synonyms=_ai_context_synonyms(raw.get("ai_context")),
        instructions=_ai_context_instructions(raw.get("ai_context")),
    )


def _parse_dataset(raw: dict[str, Any]) -> Dataset:
    return Dataset(
        name=raw["name"],
        source=raw["source"],
        primary_key=tuple(raw.get("primary_key", []) or []),
        unique_keys=tuple(tuple(k) for k in raw.get("unique_keys", []) or []),
        description=raw.get("description"),
        synonyms=_ai_context_synonyms(raw.get("ai_context")),
        fields=[_parse_field(f) for f in raw.get("fields", []) or []],
    )


def _parse_relationship(raw: dict[str, Any]) -> Relationship:
    return Relationship(
        name=raw["name"],
        from_dataset=raw["from"],
        to_dataset=raw["to"],
        from_columns=tuple(raw["from_columns"]),
        to_columns=tuple(raw["to_columns"]),
    )


def _parse_metric(raw: dict[str, Any]) -> Metric:
    return Metric(
        name=raw["name"],
        expressions=_parse_expressions(raw),
        description=raw.get("description"),
        synonyms=_ai_context_synonyms(raw.get("ai_context")),
    )


def load(path: str | Path) -> SemanticModel:
    text = Path(path).read_text(encoding="utf-8")
    doc = _parse(text)

    if "semantic_model" not in doc:
        raise ValueError("Missing top-level semantic_model[] in document")

    models = doc["semantic_model"]
    if not models:
        raise ValueError("semantic_model[] is empty")
    if len(models) > 1:
        raise ValueError("Multi-model documents are not supported by this loader")

    sm = models[0]
    ai = sm.get("ai_context")

    return SemanticModel(
        name=sm["name"],
        description=sm.get("description"),
        instructions=_ai_context_instructions(ai),
        synonyms=_ai_context_synonyms(ai),
        examples=_ai_context_examples(ai),
        datasets=[_parse_dataset(d) for d in sm.get("datasets", []) or []],
        relationships=[_parse_relationship(r) for r in sm.get("relationships", []) or []],
        metrics=[_parse_metric(m) for m in sm.get("metrics", []) or []],
        custom_extensions=list(sm.get("custom_extensions", []) or []),
        raw=doc,
    )


def resolve_metric(model: SemanticModel, name: str, dialect: str) -> str:
    """Return the expression for ``metric`` in ``dialect``, or fall back to ANSI_SQL."""
    for metric in model.metrics:
        if metric.name != name:
            continue
        for de in metric.expressions:
            if de.dialect == dialect:
                return de.expression
        for de in metric.expressions:
            if de.dialect == "ANSI_SQL":
                return de.expression
    raise KeyError(f"No metric {name!r} (dialect={dialect!r})")
