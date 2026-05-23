"""Wrap a Polaris Navigator bundle as an ODS data-product manifest.

Implements ARCHITECTURE.md §6: takes a bundle produced by
``navigator_from_osi.build_bundle`` plus a Polaris context and emits the
``ods.ipa.go.jp/v1alpha1`` manifest published at
``/.well-known/ods-data-product.yaml``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from osi_loader import load
from navigator_from_osi import PolarisContext, build_bundle


def _permission_summary(odrl: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"action": p["odrl:action"], "assignee": p["odrl:assignee"]}
        for p in odrl.get("odrl:permission", [])
    ]


def _prohibition_summary(odrl: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "action": p["odrl:action"],
            "assignee": p["odrl:assignee"],
            "reason": p.get("odrl:constraint", ""),
        }
        for p in odrl.get("odrl:prohibition", [])
    ]


def package(bundle: dict[str, Any], ctx: PolarisContext) -> dict[str, Any]:
    osi_doc = bundle["layers"]["osi"]
    model = osi_doc["semantic_model"][0]
    croissant = bundle["layers"]["semanticCroissant"]
    cdif = bundle["layers"]["cdif"]
    did = bundle["layers"]["did"]
    odrl = bundle["layers"]["odrl"]

    return {
        "apiVersion": "ods.ipa.go.jp/v1alpha1",
        "kind": "DataProduct",
        "metadata": {
            "name": model["name"],
            "namespace": f"{ctx.catalog}/{ctx.namespace}",
            "did": did["id"],
            "publisher": ctx.principal,
            "publishedAt": bundle["generatedAt"],
        },
        "governance": {
            # DAD — Data Addressability & Discoverability
            "dataAddressabilityAndDiscoverability": {
                "accessService": {
                    "type": "PolarisRESTCatalog",
                    "endpoint": ctx.rest_endpoint(),
                    "conformsTo": "https://iceberg.apache.org/rest-catalog-open-api/",
                },
                "catalogListing": f"/v1/{ctx.catalog}/namespaces/{ctx.namespace}/semantic-models",
                "discoveryProfile": {
                    "conformsTo": "https://cdif.codata.org/profile/discovery",
                    "landingPage": ctx.model_url(model["name"]),
                    "keywords": croissant.get("keywords", []),
                },
            },
            # ODS-OSI — Ontology & Semantic Interoperability
            "ontologyAndSemanticInteroperability": {
                "upperOntology": {
                    "assumption": "open-world",
                    "semanticInterchange": {
                        "spec": f"Open Semantic Interchange {osi_doc.get('version', '0.2.0.dev0')}",
                        "document": (
                            f"{ctx.model_url(model['name'])}/document"
                        ),
                        "metricCount": len(model.get("metrics", [])),
                        "synonyms": {
                            m["name"]: (m.get("ai_context") or {}).get("synonyms", [])
                            if isinstance(m.get("ai_context"), dict)
                            else []
                            for m in model.get("metrics", [])
                        },
                    },
                    "croissant": {
                        "spec": "MLCommons Croissant 1.0",
                        "document": f"{ctx.model_url(model['name'])}/navigator-bundle#layers.semanticCroissant",
                        "controlledVocabularies": cdif.get("cdif:controlledVocabulary", []),
                    },
                },
                "lowerDataProduct": {
                    "assumption": "closed-world",
                    "icebergSnapshots": [
                        {
                            "table": ds["source"],
                            "metadataLocation": ctx.metadata_uri(ds["source"]),
                        }
                        for ds in model.get("datasets", [])
                    ],
                    "contract": {
                        "conformsTo": f"{ctx.model_url(model['name'])}/navigator-bundle#layers.semanticCroissant.recordSet",
                    },
                },
            },
            # IUC — Identity & Usage Control
            "identityAndUsageControl": {
                "identity": {
                    "method": "did:oyd",
                    "document": f"{ctx.model_url(model['name'])}/navigator-bundle#identity",
                    "controller": did["controller"],
                },
                "usageControl": {
                    "spec": "ODRL 2.2",
                    "policy": f"{ctx.model_url(model['name'])}/navigator-bundle#layers.odrl",
                    "summary": {
                        "permittedActions": _permission_summary(odrl),
                        "prohibitedActions": _prohibition_summary(odrl),
                    },
                },
            },
        },
        "dpqm": {
            "upper": {"layerType": "ontology", "artifacts": ["osiDocument", "croissantRecordSet"]},
            "lower": {"layerType": "dataProduct", "artifacts": ["icebergTable", "openLineageEventStream"]},
        },
        "lineage": {
            "spec": "OpenLineage 1.0",
            "endpoint": f"{ctx.base_url}/openlineage/v1",
        },
    }


if __name__ == "__main__":
    import sys

    osi_path = Path(sys.argv[1])
    model = load(osi_path)
    ctx = PolarisContext(
        catalog="prod-catalog",
        namespace="ecommerce",
        principal="polaris://prod-catalog/principal/analytics-team",
        iceberg_metadata={
            ds.source: f"s3://lake/iceberg/{ds.source.replace('.', '/')}/metadata/latest.json"
            for ds in model.datasets
        },
    )
    bundle = build_bundle(ctx, model)
    print(json.dumps(package(bundle, ctx), indent=2, default=str))
