# Comparison matrix

| Aspect | Iceberg | Unity Catalog | Gravitino | OpenLineage | OSI | QueryGraph Navigator | ODS |
|---|---|---|---|---|---|---|---|
| **Layer (see [two_semantic_layers](two_semantic_layers.md))** | A | A | A | A | B | B | A+B (architecture) |
| Primary object | Table | Securable | Metalake entity | RunEvent | semantic_model | AiNavigatorSemanticBundle | Data space + product |
| Spec license | Apache 2.0 | Apache 2.0 (OSS UC) | Apache 2.0 | Apache 2.0 | Apache 2.0 + CC-BY | Apache 2.0 | open |
| Carries physical schema | ✓ | ✓ | ✓ | ✓ (facet) | indirect (`source`) | indirect (Croissant) | n/a |
| Carries metrics | ✗ | partial (tags) | ✗ | ✗ | **✓** | ✓ (via OSI) | ✓ (OSI pillar) |
| Multi-dialect expressions | ✗ | ✗ | ✗ | ✗ | **✓** | ✓ | n/a |
| AI-context / synonyms | ✗ | comments | comments | ✗ | **✓** | ✓ | ✓ (ontology) |
| Identity | ✗ | principals | principals | ✗ | ✗ | **✓ DID** | ✓ IUC |
| Usage policy | ✗ | grants | grants | ✗ | ✗ | **✓ ODRL** | ✓ IUC |
| Discoverability profile | ✗ | partial | partial | ✗ | ✗ | **✓ CDIF** | ✓ DAD |
| Row-level lineage | partial (snapshots) | ✓ | partial | **✓** | ✗ | ✗ | n/a |
| Cross-org first-class | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** | **✓** |
| Open World Assumption | ✗ | ✗ | ✗ | ✗ | partial (`ai_context`) | ✓ | ✓ (DPQM upper) |
| Closed World Assumption | ✓ | ✓ | ✓ | ✓ | ✓ (schema) | ✓ (validated) | ✓ (DPQM lower) |

**Bold** marks where a system is the *primary* place to look for that concern.

## Reading guide

- Look at any column. Where it has gaps, look across the row for who fills them.
- The gap pattern in **OSI** (identity / usage / discoverability / lineage all empty) is exactly what **QueryGraph Navigator** and **OpenLineage** fill. That's not a coincidence — it's why they compose.
- The gap pattern in **Polaris-today** (Iceberg only) is metric semantics, AI context, and cross-org identity. [`polaris#4522`](https://github.com/apache/polaris/issues/4522) addresses the first; the Navigator extension in [`ARCHITECTURE.md`](../ARCHITECTURE.md) addresses the rest.
