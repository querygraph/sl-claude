# Architecture: QueryGraph AI Navigator in Apache Polaris, aligned with OSI

This document expands [`REPORT.md` §5](REPORT.md#5-proposal-querygraph-ai-navigator-inside-apache-polaris-aligned-with-osi-and-ods) with implementation-level detail. It is intentionally close to executable: every name here corresponds to either an existing Polaris object, an OSI field, an OpenLineage facet, or one of the four QueryGraph bundle layers.

## 1. Object model

```
Polaris (existing)
  Catalog
    Namespace                                  (existing)
      Table                                    (existing — Iceberg)
      View                                     (existing — Iceberg)
      SemanticModel                            (NEW)
        spec_version:   "OSI 0.2.0.dev0"
        document:       <opaque OSI YAML/JSON blob>
        index:          extracted (name, datasets[].source, metrics[].name)
        grants:         reuses Polaris principal/role/privilege model

Navigator extension (NEW, in-process or sidecar)
  bundle_builder(SemanticModel, Namespace, Principal) -> NavigatorBundle
  NavigatorBundle = {
    osi:        <verbatim OSI document>,
    croissant:  <projected from OSI fields + Polaris table metadata>,
    cdif:       <projected from Polaris namespace metadata>,
    did:        <derived from Polaris principal identity>,
    odrl:       <projected from Polaris grants on the SemanticModel>,
  }
```

## 2. New REST surface

All under the existing Polaris `/v1/{catalog}` mount.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/namespaces/{ns}/semantic-models` | List models in a namespace |
| `POST` | `/namespaces/{ns}/semantic-models` | Create (body = OSI YAML or JSON) |
| `GET` | `/namespaces/{ns}/semantic-models/{name}` | Fetch the raw OSI document + metadata |
| `PUT` | `/namespaces/{ns}/semantic-models/{name}` | Replace |
| `DELETE` | `/namespaces/{ns}/semantic-models/{name}` | Remove |
| `GET` | `/namespaces/{ns}/semantic-models/{name}/metrics` | List metrics with `ai_context` |
| `GET` | `/namespaces/{ns}/semantic-models/{name}/metrics/{m}?dialect=…` | Get one resolved metric expression |
| `GET` | `/namespaces/{ns}/semantic-models/{name}/navigator-bundle` | **NEW** — return the four-layer JSON-LD bundle |
| `POST` | `/namespaces/{ns}/semantic-models/{name}/navigator-bundle/verify` | Verify a signed inbound bundle against this catalog |

The navigator-bundle endpoint sets `Content-Type: application/ld+json` and includes the bundle's DID in the `Link` header for downstream verification.

## 3. New privileges

| Privilege | Verb |
|---|---|
| `USE_SEMANTIC_MODEL` | `GET` on the model and its metrics |
| `MANAGE_SEMANTIC_MODEL` | `POST` / `PUT` / `DELETE` |
| `EXPORT_NAVIGATOR_BUNDLE` | `GET /navigator-bundle` (separately granted because ODRL exposes more than the raw OSI) |
| `FEDERATE_SEMANTIC_MODEL` | accept external bundles into the federated namespace (phase 4) |

Polaris policies on these privileges become ODRL `permission`/`prohibition` rules in the bundle. A principal with `USE_SEMANTIC_MODEL` becomes the `odrl:assignee` of a `Rule(action=odrl:read, ...)`. A revoked grant becomes a `prohibition`. The mapping is mechanical and reproducible.

## 4. The OSI → Bundle projection

Implemented in [`src/navigator_from_osi.py`](src/navigator_from_osi.py). Pseudocode of the load-bearing transformation:

```
def build_bundle(osi, polaris_ctx, principal):
    croissant = {
        "@type": "cr:Dataset",
        "name": osi.semantic_model.name,
        "description": osi.semantic_model.description,
        "keywords": flatten(synonyms(osi)),
        "distribution": [
            FileObject(
                contentUrl=polaris_ctx.table_metadata_uri(ds.source),
                encodingFormat="application/vnd.apache.iceberg.metadata+json",
            )
            for ds in osi.datasets
        ],
        "recordSet": [record_set_from(ds) for ds in osi.datasets],
    }
    cdif = {
        "@type": "dcat:Dataset",
        "cdif:profile": [DISCOVERY, DATA_ACCESS, CONTROLLED_VOCABULARIES,
                         DATA_INTEGRATION, UNIVERSALS],
        "dcat:landingPage": polaris_ctx.namespace_url(),
        "dcat:accessService": polaris_ctx.rest_endpoint(),
        "cdif:controlledVocabulary": vocab_links(osi),
    }
    did = DidDocument.new_oyd(
        seed=f"polaris:{polaris_ctx.catalog}:{osi.semantic_model.name}",
        controller=principal.id,
    ).with_service_endpoint(polaris_ctx.namespace_url())
    odrl = Policy.from_polaris_grants(
        target=did.id,
        assigner=principal.id,
        grants=polaris_ctx.grants_on(osi.semantic_model.name),
    )
    return {
        "@context": QUERYGRAPH_CONTEXT,
        "@type": "querygraph:AiNavigatorSemanticBundle",
        "generatedAt": now_utc_iso(),
        "identity": did.to_json(),
        "layers": {
            "osi": osi.to_dict(),
            "semanticCroissant": croissant,
            "cdif": cdif,
            "did": did.to_json(),
            "odrl": odrl.to_json_ld(),
        },
    }
```

The structure of `qg-python`'s `AiNavigator.build()` is preserved verbatim — only the *sources* of the inputs change (Polaris context replaces CLI flags).

## 5. OpenLineage facet

A new community facet, proposed under the existing OL extension mechanism:

```json
{
  "_producer": "polaris-osi-emitter/0.1",
  "_schemaURL": "https://querygraph.ai/schemas/OSIMetricFacet.json",
  "semanticModel": "ecommerce_analytics",
  "metricName": "total_revenue",
  "dialect": "SNOWFLAKE",
  "expression": "SUM(orders.amount)",
  "navigatorBundleDid": "did:oyd:z..."
}
```

It attaches at the `Job` level (the query is identified by *which OSI metric* it computes, not just which SQL it executed). Inputs and outputs are the underlying Iceberg datasets, exactly as today.

The combination of (a) `SchemaDatasetFacet` on each input, (b) `ColumnLineageDatasetFacet` between input and output, and (c) the new `OSIMetricFacet` on the job, gives a complete picture: *which physical columns flowed where, and which semantic metric they were computing*. This is what makes "if I change the definition of `total_revenue`, which dashboards break?" answerable.

## 6. ODS conformance

To advertise a Polaris catalog as an ODS data-space node, the navigator extension publishes a per-catalog **ODS data product manifest** (see [`examples/08_ods_data_product_manifest.yaml`](examples/08_ods_data_product_manifest.yaml)) at `/.well-known/ods-data-product.yaml`. The manifest:

- declares the three governance pillars and points each at concrete artifacts:
  - **DAD** → the Polaris `/semantic-models` listing and CDIF dataset profile of each bundle;
  - **OSI** → the Polaris-hosted OSI document plus Croissant JSON-LD;
  - **IUC** → the bundle's DID + ODRL policy;
- declares **DPQM** layers: upper = OSI + Croissant (OWA), lower = Iceberg snapshot (CWA);
- enumerates federation peers (other Polaris/ODS nodes whose bundles may be accepted).

## 7. Phasing (from `REPORT.md` §5.7, with API hooks)

| Phase | Polaris-side work | External work | Ships when |
|---|---|---|---|
| 1 — OSI as data | Add `SemanticModel` object, schema validation, REST CRUD | None | OSI v0.2 spec settles |
| 2 — Navigator projection | `/navigator-bundle` endpoint, in-process projector | `qg-python` becomes a library dependency or is re-implemented in JVM | Phase 1 + projector tests |
| 3 — OL emitter | `OSIMetricFacet` schema; engines wired in | OL community accepts facet | Phase 2 + at least one engine integration |
| 4 — ODS adapter | `__federated` namespace, inbound bundle verifier, manifest at `/.well-known/...` | Inter-org agreements | Phase 3 + ODS RAM lockdown |

Each phase is independently shippable. Phases 2–4 do not touch the Iceberg catalog API; they layer above it.

## 8. Non-goals

- Polaris does **not** become a metric *execution* engine. The OSI document remains declarative; engines (Spark, Trino, …) still compute the metric. The proposed extension only stores, projects, signs, and emits lineage.
- Polaris does **not** subsume Cube/MetricFlow/Honeydew. Those tools may produce or consume OSI; Polaris is the system of record.
- The Navigator bundle does **not** replace OL. They carry complementary information: OL is the verb stream, the bundle is the noun envelope.
- The Navigator extension does **not** require ODS. ODS conformance is an opt-in publishing layer above it.
