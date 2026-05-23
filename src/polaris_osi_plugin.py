"""Polaris OSI plugin scaffold — *intent-spec* in Python pseudocode.

In the real Polaris codebase this would be a Java module: a
``SemanticModelEntity`` JPA class, a Quarkus REST resource, and a service
that delegates to the Iceberg catalog for ``source`` resolution. We
sketch the same shape here in Python so the REST surface from
ARCHITECTURE.md §2 is concrete and testable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osi_loader import SemanticModel, load
from navigator_from_osi import PolarisContext, build_bundle


# ── In-memory entity model ──────────────────────────────────────────────


@dataclass
class SemanticModelEntity:
    catalog: str
    namespace: str
    name: str
    document_yaml: str
    document_sha256: str
    spec_version: str
    created_by: str
    created_at: str
    updated_at: str
    parsed: SemanticModel
    grants: list[dict[str, Any]] = field(default_factory=list)

    def to_resource(self) -> dict[str, Any]:
        """REST representation — mirrors examples/07_polaris_semantic_model.json."""
        model = self.parsed
        return {
            "kind": "SemanticModel",
            "apiVersion": "polaris/v1",
            "metadata": {
                "catalog": self.catalog,
                "namespace": self.namespace,
                "name": self.name,
                "specVersion": self.spec_version,
                "createdAt": self.created_at,
                "createdBy": self.created_by,
                "updatedAt": self.updated_at,
            },
            "spec": {
                "documentRef": {
                    "sha256": self.document_sha256,
                    "contentType": "application/yaml",
                    "uri": f"polaris://{self.catalog}/blobs/sha256:{self.document_sha256}",
                },
                "index": {
                    "datasets": [
                        {
                            "name": ds.name,
                            "source": ds.source,
                            "resolvedTable": f"{self.catalog}.{ds.source}",
                        }
                        for ds in model.datasets
                    ],
                    "metrics": [
                        {
                            "name": m.name,
                            "synonyms": list(m.synonyms),
                            "dialects": [e.dialect for e in m.expressions],
                        }
                        for m in model.metrics
                    ],
                    "aiContextSummary": {
                        "instructions": model.instructions,
                        "synonyms": list(model.synonyms),
                    },
                },
            },
            "status": {
                "validatedAgainstSchema": self.spec_version,
                "validationState": "VALID",
                "resolvedSources": "ALL_RESOLVED",
            },
            "_links": {
                "self": (
                    f"/v1/{self.catalog}/namespaces/{self.namespace}"
                    f"/semantic-models/{self.name}"
                ),
                "document": (
                    f"/v1/{self.catalog}/namespaces/{self.namespace}"
                    f"/semantic-models/{self.name}/document"
                ),
                "metrics": (
                    f"/v1/{self.catalog}/namespaces/{self.namespace}"
                    f"/semantic-models/{self.name}/metrics"
                ),
                "navigatorBundle": (
                    f"/v1/{self.catalog}/namespaces/{self.namespace}"
                    f"/semantic-models/{self.name}/navigator-bundle"
                ),
            },
        }


# ── Plugin / service ────────────────────────────────────────────────────


class PolarisSemanticModelService:
    """In-memory stand-in for the Polaris service-layer class."""

    def __init__(self, base_url: str = "https://polaris.example.com") -> None:
        self._store: dict[tuple[str, str, str], SemanticModelEntity] = {}
        self.base_url = base_url

    # ---- CRUD ----------------------------------------------------------

    def put(
        self,
        catalog: str,
        namespace: str,
        name: str,
        document_path: Path,
        principal: str,
    ) -> SemanticModelEntity:
        text = Path(document_path).read_text(encoding="utf-8")
        parsed = load(document_path)
        if parsed.name != name:
            raise ValueError(
                f"Document's semantic_model.name={parsed.name!r} != path name={name!r}"
            )
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing = self._store.get((catalog, namespace, name))
        entity = SemanticModelEntity(
            catalog=catalog,
            namespace=namespace,
            name=name,
            document_yaml=text,
            document_sha256=sha,
            spec_version=parsed.raw.get("version", "OSI 0.2.0.dev0"),
            created_by=existing.created_by if existing else principal,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            parsed=parsed,
            grants=existing.grants if existing else [],
        )
        self._store[(catalog, namespace, name)] = entity
        return entity

    def get(self, catalog: str, namespace: str, name: str) -> SemanticModelEntity:
        return self._store[(catalog, namespace, name)]

    def list(self, catalog: str, namespace: str) -> list[SemanticModelEntity]:
        return [
            e
            for (c, n, _), e in self._store.items()
            if c == catalog and n == namespace
        ]

    def delete(self, catalog: str, namespace: str, name: str) -> None:
        self._store.pop((catalog, namespace, name), None)

    # ---- Derived endpoints --------------------------------------------

    def metric_expression(
        self,
        catalog: str,
        namespace: str,
        name: str,
        metric: str,
        dialect: str,
    ) -> str:
        from osi_loader import resolve_metric

        entity = self.get(catalog, namespace, name)
        return resolve_metric(entity.parsed, metric, dialect)

    def navigator_bundle(
        self,
        catalog: str,
        namespace: str,
        name: str,
        principal: str,
    ) -> dict[str, Any]:
        entity = self.get(catalog, namespace, name)
        ctx = PolarisContext(
            catalog=catalog,
            namespace=namespace,
            principal=principal,
            base_url=self.base_url,
            iceberg_metadata=self._mock_iceberg_metadata(entity.parsed),
            grants=entity.grants,
        )
        return build_bundle(ctx, entity.parsed)

    @staticmethod
    def _mock_iceberg_metadata(model: SemanticModel) -> dict[str, str]:
        # In real Polaris this is a TableOperations.refresh() over each source.
        return {
            ds.source: f"s3://lake/iceberg/{ds.source.replace('.', '/')}/metadata/latest.json"
            for ds in model.datasets
        }


# ── Demo: run it like a tiny REST harness ───────────────────────────────


def demo(osi_path: Path) -> None:
    service = PolarisSemanticModelService()
    entity = service.put(
        catalog="prod-catalog",
        namespace="ecommerce",
        name="ecommerce_analytics",
        document_path=osi_path,
        principal="polaris://prod-catalog/principal/analytics-team",
    )

    print("── PUT  /v1/prod-catalog/namespaces/ecommerce/semantic-models/ecommerce_analytics ──")
    print(json.dumps(entity.to_resource(), indent=2))

    print("\n── GET  .../metrics/total_revenue?dialect=SNOWFLAKE ──")
    print(
        service.metric_expression(
            "prod-catalog", "ecommerce", "ecommerce_analytics", "total_revenue", "SNOWFLAKE"
        )
    )

    print("\n── GET  .../navigator-bundle ──")
    bundle = service.navigator_bundle(
        "prod-catalog",
        "ecommerce",
        "ecommerce_analytics",
        principal="polaris://prod-catalog/principal/analytics-team",
    )
    print(json.dumps(bundle, indent=2, default=str)[:2000] + "\n... (truncated)")


if __name__ == "__main__":
    import sys

    demo(Path(sys.argv[1]))
