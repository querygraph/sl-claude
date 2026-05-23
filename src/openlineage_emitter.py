"""Emit an OpenLineage RunEvent with the proposed OSIMetricFacet.

Demonstrates ARCHITECTURE.md §5: how a query that resolves an OSI metric
becomes a single OL job with the metric name, and how the resulting
event references the Navigator bundle by DID.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osi_loader import load, resolve_metric
from navigator_from_osi import PolarisContext, build_bundle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _column_lineage_for_revenue() -> dict[str, Any]:
    return {
        "_producer": "polaris-osi-emitter/0.1",
        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ColumnLineageDatasetFacet.json",
        "fields": {
            "q": {
                "inputFields": [
                    {
                        "namespace": "polaris://prod-catalog",
                        "name": "ecommerce.public.orders",
                        "field": "order_date",
                    }
                ]
            },
            "total_revenue": {
                "inputFields": [
                    {
                        "namespace": "polaris://prod-catalog",
                        "name": "ecommerce.public.orders",
                        "field": "amount",
                    }
                ],
                "transformationDescription": "OSI metric total_revenue: SUM(orders.amount)",
            },
        },
    }


def emit_metric_run(
    osi_path: Path,
    metric_name: str,
    dialect: str,
    *,
    catalog: str = "prod-catalog",
    namespace: str = "ecommerce",
    principal: str = "polaris://prod-catalog/principal/analytics-team",
) -> dict[str, Any]:
    model = load(osi_path)
    expression = resolve_metric(model, metric_name, dialect)

    ctx = PolarisContext(catalog=catalog, namespace=namespace, principal=principal)
    bundle = build_bundle(ctx, model)
    bundle_sha = hashlib.sha256(
        json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    run_id = str(uuid.uuid4())
    return {
        "eventType": "COMPLETE",
        "eventTime": _now(),
        "run": {"runId": run_id, "facets": {}},
        "job": {
            "namespace": f"polaris://{catalog}",
            "name": f"{model.name}.{metric_name}",
            "facets": {
                "sql": {
                    "_producer": "polaris-osi-emitter/0.1",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SQLJobFacet.json",
                    "query": (
                        f"SELECT DATE_TRUNC('quarter', order_date) AS q, {expression} "
                        f"AS {metric_name} FROM ecommerce.public.orders "
                        f"WHERE status = 'completed' GROUP BY 1"
                    ),
                },
                "osiMetric": {
                    "_producer": "polaris-osi-emitter/0.1",
                    "_schemaURL": "https://querygraph.ai/schemas/OSIMetricFacet.json",
                    "semanticModel": model.name,
                    "metricName": metric_name,
                    "dialect": dialect,
                    "expression": expression,
                    "polarisRef": {
                        "catalog": catalog,
                        "namespace": namespace,
                        "semanticModel": model.name,
                    },
                    "navigatorBundleDid": bundle["identity"]["id"],
                    "navigatorBundleSha256": bundle_sha,
                },
            },
        },
        "inputs": [
            {
                "namespace": f"polaris://{catalog}",
                "name": ds.source,
                "facets": {
                    "schema": {
                        "_producer": "polaris-osi-emitter/0.1",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SchemaDatasetFacet.json",
                        "fields": [
                            {"name": f.name, "type": "DATE" if f.is_time_dimension else "STRING"}
                            for f in ds.fields
                        ],
                    }
                },
            }
            for ds in model.datasets
            if ds.name == "orders"
        ],
        "outputs": [
            {
                "namespace": f"polaris://{catalog}",
                "name": f"ecommerce.bi.{metric_name}_by_quarter",
                "facets": {
                    "schema": {
                        "_producer": "polaris-osi-emitter/0.1",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SchemaDatasetFacet.json",
                        "fields": [
                            {"name": "q", "type": "DATE"},
                            {"name": metric_name, "type": "DECIMAL(18,2)"},
                        ],
                    },
                    "columnLineage": _column_lineage_for_revenue(),
                },
            }
        ],
        "producer": "polaris-osi-emitter/0.1",
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json",
    }


if __name__ == "__main__":
    import sys

    osi_path = Path(sys.argv[1])
    metric = sys.argv[2] if len(sys.argv) > 2 else "total_revenue"
    dialect = sys.argv[3] if len(sys.argv) > 3 else "SNOWFLAKE"
    print(json.dumps(emit_metric_run(osi_path, metric, dialect), indent=2))
