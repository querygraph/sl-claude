# The two semantic layers

The phrase "semantic layer" is overloaded. Most arguments about it are really arguments about *which* of two distinct layers people are talking about.

## Layer A — Physical / catalog semantics

Owned by the data plane. Tells engines what bytes mean.

- **Apache Iceberg** — table schema, partition spec, snapshots, manifests.
- **Apache Polaris** — REST catalog over Iceberg + principals/roles/grants.
- **Unity Catalog** — `catalog.schema.object` securables, lineage, tags.
- **Apache Gravitino** — federated metalake over many backends.
- **OpenLineage** — the lineage event stream over the above.

Layer A answers questions of the form *"what column, what type, what file, what snapshot, who can read it, where did it come from?"*

## Layer B — Business / metric semantics

Owned by the analytics plane. Tells humans, BI tools, and LLMs what the data *means in our business*.

- **dbt MetricFlow** — metrics, entities, dimensions, measures.
- **Cube** — cubes, measures, dimensions, segments.
- **OSI** — `semantic_model.datasets.fields` + `metrics`, with multi-dialect expressions and `ai_context`.
- **QueryGraph Navigator** — wraps the above with identity, policy, discoverability.

Layer B answers questions of the form *"what is `monthly_recurring_revenue`? in what dialect? what synonyms? who is allowed to use this metric for what?"*

## Why the layers must stay distinct

1. **Different cadence of change.** Iceberg tables evolve with the data plane (new partitions, new columns) on hours-to-days timescales. Business metrics evolve with business definitions on days-to-quarters timescales, often *across* table revisions. Coupling them locks the business layer to physical-layer release cycles.
2. **Different consumers.** Layer A is consumed by engines; Layer B by humans/agents/BI. Engines want stability and types; humans want synonyms, descriptions, examples.
3. **Different identity model.** Layer A identifies things by namespace+name *within* an organization. Layer B increasingly needs cross-organizational identity (DIDs) so AI agents can verify the source of a metric definition.
4. **Different policy model.** Layer A policies are about read/write on rows. Layer B policies are about *what can be derived* (training, indexing, redistribution). ODRL belongs at Layer B.

## Where OSI fits

OSI is unambiguously **Layer B**. Its `dataset.source` is a *pointer* into Layer A (any catalog). Its `expression.dialects[]` is the engine-binding glue. Its `ai_context` is the surface for agents. It deliberately omits identity, lineage, and policy — those belong elsewhere.

## Where QueryGraph fits

QueryGraph is **Layer B with batteries included**. It wraps the metric semantics (provided by OSI, or its own Croissant `RecordSet`) with the three things OSI omits: identity (DID), policy (ODRL), and discoverability (CDIF). That bundle is the unit of cross-organizational exchange.

## Where Polaris is being asked to go

[`polaris#4522`](https://github.com/apache/polaris/issues/4522) proposes that Polaris — historically Layer A — also host Layer B objects. This is good: Polaris already has the namespace, identity, and grant primitives Layer B needs to ride on. The interesting question is whether to host Layer B as *just YAML* (vanilla OSI) or as *full Navigator bundles* (OSI + Croissant + CDIF + DID + ODRL). The argument for the bundle form is in [`REPORT.md` §5](../REPORT.md#5-proposal-querygraph-ai-navigator-inside-apache-polaris-aligned-with-osi-and-ods).
