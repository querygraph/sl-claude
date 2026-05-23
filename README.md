# querygraph/semantic/claude

Reference materials for the **QueryGraph AI Navigator + Apache Polaris + Open Semantic Interchange** alignment proposal.

- Full report: [`semantic-layer-report.md`](semantic-layer-report.md)
- Architecture detail: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- The two-semantic-layers thesis: [`docs/two_semantic_layers.md`](docs/two_semantic_layers.md)
- Side-by-side matrix: [`docs/comparison_matrix.md`](docs/comparison_matrix.md)

## Quick map

| Topic | Where |
|---|---|
| What "semantic layer" means for Iceberg / Unity / Gravitino / OpenLineage | [`semantic-layer-report.md` §2](semantic-layer-report.md#2-how-each-system-defines-its-semantic-layer) |
| Full OSI v0.2 spec walk-through with object graph | [`semantic-layer-report.md` §3](semantic-layer-report.md#3-open-semantic-interchange-osi--what-the-v02-spec-actually-says) |
| Plain-language read of [`polaris#4522`](https://github.com/apache/polaris/issues/4522) | [`semantic-layer-report.md` §4](semantic-layer-report.md#4-apache-polaris-and-polaris4522) |
| Concrete OSI + Navigator integration design | [`semantic-layer-report.md` §5](semantic-layer-report.md#5-proposal-querygraph-ai-navigator-inside-apache-polaris-aligned-with-osi-and-ods) |
| How QueryGraph maps to IPA Open Data Spaces (DAD/OSI/IUC) | [`semantic-layer-report.md` §2.6](semantic-layer-report.md#26-open-data-spaces-ipa-japan--semantics-across-organizational-and-national-boundaries) and [§5.4](semantic-layer-report.md#54-ods-alignment) |
| Migration path / phasing | [`semantic-layer-report.md` §5.7](semantic-layer-report.md#57-migration-path) |

## Code & examples

```text
examples/   eight artifacts showing the same e-commerce dataset across every spec
src/        end-to-end Python: OSI -> Navigator bundle -> OpenLineage -> ODS product
```

Run the full demo:

```bash
cd ~/src/querygraph/semantic/claude
make demo
```

This loads `examples/01_osi_model_ecommerce.yaml`, projects it through
`src/navigator_from_osi.py` into a four-layer Navigator bundle (matching
`examples/06_querygraph_navigator_bundle.json`), emits an OpenLineage
`RunEvent` with the proposed `OSIMetricFacet`, and finally wraps the whole
thing as an ODS data-product manifest.

## Status

This is research, not production: a runnable sketch that proves the
data-model in §5 round-trips and that no part of the OSI / Polaris / OL /
QueryGraph / ODS overlap requires either of them to redefine the others.

## License

Code Apache-2.0, prose CC-BY-4.0 (matching the OSI repository's split).
