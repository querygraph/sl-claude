"""End-to-end demo: OSI -> Navigator bundle -> Polaris resource -> OL event -> ODS manifest.

Run via the top-level Makefile: ``make demo``.
"""

from __future__ import annotations

import json
from pathlib import Path

from osi_loader import load, resolve_metric
from navigator_from_osi import PolarisContext, build_bundle
from polaris_osi_plugin import PolarisSemanticModelService
from openlineage_emitter import emit_metric_run
from ods_packager import package


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OSI_PATH = ROOT / "examples" / "01_osi_model_ecommerce.yaml"


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _pretty(obj, limit: int = 1400) -> str:
    text = json.dumps(obj, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more bytes)"


def main() -> int:
    section("1. Parse the OSI v0.2 document")
    model = load(OSI_PATH)
    print(f"semantic_model.name        = {model.name}")
    print(f"description                = {model.description}")
    print(f"datasets                   = {[d.name for d in model.datasets]}")
    print(f"metrics                    = {[m.name for m in model.metrics]}")
    print(f"relationships              = {[r.name for r in model.relationships]}")

    section("2. Resolve a multi-dialect OSI metric")
    for dialect in ("ANSI_SQL", "SNOWFLAKE", "DATABRICKS"):
        print(f"  total_revenue [{dialect}] = {resolve_metric(model, 'total_revenue', dialect)}")

    section("3. PUT into Polaris (proposed SemanticModel REST resource)")
    service = PolarisSemanticModelService()
    entity = service.put(
        catalog="prod-catalog",
        namespace="ecommerce",
        name="ecommerce_analytics",
        document_path=OSI_PATH,
        principal="polaris://prod-catalog/principal/analytics-team",
    )
    print(_pretty(entity.to_resource()))

    section("4. GET /navigator-bundle (QueryGraph projection)")
    ctx = PolarisContext(
        catalog="prod-catalog",
        namespace="ecommerce",
        principal="polaris://prod-catalog/principal/analytics-team",
        iceberg_metadata={
            "ecommerce.public.orders":    "s3://lake/iceberg/ecommerce.db/orders/metadata/00142.json",
            "ecommerce.public.customers": "s3://lake/iceberg/ecommerce.db/customers/metadata/00078.json",
            "ecommerce.public.products":  "s3://lake/iceberg/ecommerce.db/products/metadata/00031.json",
        },
    )
    bundle = build_bundle(ctx, model)
    print("Navigator bundle DID =", bundle["identity"]["id"])
    print("Layers present       =", sorted(bundle["layers"].keys()))
    print(_pretty(bundle, limit=2000))

    section("5. Emit an OpenLineage RunEvent with OSIMetricFacet")
    event = emit_metric_run(OSI_PATH, "total_revenue", "SNOWFLAKE")
    print("OL job.name          =", event["job"]["name"])
    print("OSIMetricFacet keys  =", sorted(event["job"]["facets"]["osiMetric"].keys()))
    print(_pretty(event, limit=1800))

    section("6. Package as an ODS data-product manifest")
    manifest = package(bundle, ctx)
    print("ODS DID              =", manifest["metadata"]["did"])
    print("ODS pillars present  =", sorted(manifest["governance"].keys()))
    print(_pretty(manifest, limit=2000))

    section("Done")
    print("OSI -> Croissant+CDIF+DID+ODRL -> Polaris -> OpenLineage -> ODS round-trip OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
