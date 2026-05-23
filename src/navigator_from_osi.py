"""Project an OSI semantic model into a QueryGraph AI Navigator bundle.

Implements the deterministic OSI -> {Croissant, CDIF, DID, ODRL} mapping
described in REPORT.md §5.3 and ARCHITECTURE.md §4.

Mirrors the structure of qg-python's ``AiNavigator.build()`` but takes a
Polaris context object in place of the CLI ``NavigatorInput``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osi_loader import SemanticModel, load

# A trimmed Bitcoin-base58 alphabet, matching qg-python/querygraph/base58.py.
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out: list[str] = []
    while n > 0:
        n, r = divmod(n, 58)
        out.append(_B58_ALPHABET[r])
    leading = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading + "".join(reversed(out)) or "1"


def _did_oyd(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    multihash = bytes([0x12, 0x20]) + digest
    return f"did:oyd:z{_b58encode(multihash)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PolarisContext:
    """Everything the projector needs that comes from Polaris, not from OSI."""

    catalog: str
    namespace: str
    principal: str  # e.g. "polaris://prod-catalog/principal/analytics-team"
    base_url: str = "https://polaris.example.com"
    # Per-dataset Iceberg metadata locations; key is OSI dataset.source.
    iceberg_metadata: dict[str, str] = field(default_factory=dict)
    # Polaris grants on the semantic model, expressed as ODRL-shaped rules.
    grants: list[dict[str, Any]] = field(default_factory=list)
    prohibitions: list[dict[str, Any]] = field(default_factory=list)

    def model_url(self, model_name: str) -> str:
        return (
            f"{self.base_url}/catalogs/{self.catalog}"
            f"/namespaces/{self.namespace}/semantic-models/{model_name}"
        )

    def rest_endpoint(self) -> str:
        return f"{self.base_url}/api/catalog/v1/{self.catalog}"

    def metadata_uri(self, source: str) -> str:
        return self.iceberg_metadata.get(source, f"polaris://{self.catalog}/{source}")


_CONTEXT = {
    "schema": "https://schema.org/",
    "cr": "http://mlcommons.org/croissant/",
    "cdif": "https://cdif.codata.org/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "osi": "https://open-semantic-interchange.org/ns#",
    "polaris": "https://polaris.apache.org/ns#",
    "querygraph": "https://querygraph.ai/ns#",
}


def _croissant_dataset_id(ctx: PolarisContext, model: SemanticModel) -> str:
    return f"{ctx.model_url(model.name)}#dataset"


def _project_record_set(dataset, model: SemanticModel) -> dict[str, Any]:
    refs_by_field: dict[str, dict[str, str]] = {}
    for rel in model.relationships:
        if rel.from_dataset != dataset.name:
            continue
        for src, dst in zip(rel.from_columns, rel.to_columns, strict=True):
            refs_by_field[src] = {"@id": rel.to_dataset, "field": dst}

    return {
        "@type": "cr:RecordSet",
        "@id": dataset.name,
        "name": dataset.name,
        "description": dataset.description,
        "field": [
            {
                "@type": "cr:Field",
                "name": f.name,
                "description": f.description,
                "dataType": "sc:Date" if f.is_time_dimension else "sc:Text",
                **({"alternateName": list(f.synonyms)} if f.synonyms else {}),
                **({"references": refs_by_field[f.name]} if f.name in refs_by_field else {}),
            }
            for f in dataset.fields
        ],
    }


def _project_croissant(ctx: PolarisContext, model: SemanticModel) -> dict[str, Any]:
    dataset_id = _croissant_dataset_id(ctx, model)
    keywords: list[str] = list(model.synonyms)
    for ds in model.datasets:
        keywords.extend(ds.synonyms)

    return {
        "@context": {"@vocab": "https://schema.org/", "cr": "http://mlcommons.org/croissant/"},
        "@type": "cr:Dataset",
        "@id": dataset_id,
        "name": model.name,
        "description": model.description,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "keywords": sorted(set(keywords)),
        "creator": [{"@type": "Organization", "name": ctx.principal.rsplit("/", 1)[-1]}],
        "distribution": [
            {
                "@type": "cr:FileObject",
                "@id": f"polaris://{ctx.catalog}/{ds.source}",
                "name": ds.name,
                "contentUrl": ctx.metadata_uri(ds.source),
                "encodingFormat": "application/vnd.apache.iceberg.metadata+json",
            }
            for ds in model.datasets
        ],
        "recordSet": [_project_record_set(ds, model) for ds in model.datasets],
    }


def _project_cdif(ctx: PolarisContext, model: SemanticModel) -> dict[str, Any]:
    return {
        "@context": {
            "cdif": "https://cdif.codata.org/",
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@type": "dcat:Dataset",
        "@id": ctx.model_url(model.name),
        "cdif:profile": [
            "https://cdif.codata.org/profile/discovery",
            "https://cdif.codata.org/profile/data-access",
            "https://cdif.codata.org/profile/controlled-vocabularies",
            "https://cdif.codata.org/profile/data-integration",
            "https://cdif.codata.org/profile/universals",
        ],
        "dcat:landingPage": ctx.model_url(model.name),
        "dcat:accessService": {
            "@type": "dcat:DataService",
            "endpointURL": ctx.rest_endpoint(),
            "dct:conformsTo": "https://iceberg.apache.org/rest-catalog-open-api/",
        },
        "cdif:controlledVocabulary": [
            "https://schema.org/dateCreated",
            "https://schema.org/MonetaryAmount",
        ],
    }


def _project_did(ctx: PolarisContext, model: SemanticModel) -> dict[str, Any]:
    seed = f"polaris:{ctx.catalog}:{ctx.namespace}:{model.name}"
    did = _did_oyd(seed)
    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "controller": ctx.principal,
        "service_endpoint": ctx.model_url(model.name),
    }


def _project_odrl(ctx: PolarisContext, did_id: str, model: SemanticModel) -> dict[str, Any]:
    return {
        "@type": "odrl:Policy",
        "@id": f"{ctx.model_url(model.name)}/policy/default",
        "odrl:target": did_id,
        "odrl:assigner": ctx.principal,
        "odrl:permission": ctx.grants or [
            {
                "odrl:action": "odrl:read",
                "odrl:assignee": f"polaris://{ctx.catalog}/role/bi-tools",
                "odrl:constraint": "attribution required",
            }
        ],
        "odrl:prohibition": ctx.prohibitions or [
            {
                "odrl:action": "odrl:derive",
                "odrl:assignee": "public",
                "odrl:constraint": "no model training without separate agreement",
            }
        ],
    }


def _metric_catalog(model: SemanticModel) -> list[dict[str, Any]]:
    return [
        {
            "name": m.name,
            "description": m.description,
            "synonyms": list(m.synonyms),
            "dialects": [e.dialect for e in m.expressions],
        }
        for m in model.metrics
    ]


def build_bundle(ctx: PolarisContext, model: SemanticModel) -> dict[str, Any]:
    croissant = _project_croissant(ctx, model)
    cdif = _project_cdif(ctx, model)
    did_doc = _project_did(ctx, model)
    odrl = _project_odrl(ctx, did_doc["id"], model)

    return {
        "@context": _CONTEXT,
        "@type": "querygraph:AiNavigatorSemanticBundle",
        "generatedAt": _now(),
        "identity": did_doc,
        "layers": {
            "osi": model.raw,
            "semanticCroissant": croissant,
            "cdif": cdif,
            "did": did_doc,
            "odrl": odrl,
        },
        "querygraph:metricCatalog": _metric_catalog(model),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Project an OSI YAML into a Navigator bundle")
    parser.add_argument("osi_path", type=Path)
    parser.add_argument("--catalog", default="prod-catalog")
    parser.add_argument("--namespace", default="ecommerce")
    parser.add_argument(
        "--principal", default="polaris://prod-catalog/principal/analytics-team"
    )
    args = parser.parse_args(argv)

    model = load(args.osi_path)
    ctx = PolarisContext(
        catalog=args.catalog,
        namespace=args.namespace,
        principal=args.principal,
        iceberg_metadata={
            "ecommerce.public.orders":    "s3://lake/iceberg/ecommerce.db/orders/metadata/00142.json",
            "ecommerce.public.customers": "s3://lake/iceberg/ecommerce.db/customers/metadata/00078.json",
            "ecommerce.public.products":  "s3://lake/iceberg/ecommerce.db/products/metadata/00031.json",
        },
    )
    bundle = build_bundle(ctx, model)
    print(json.dumps(bundle, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
