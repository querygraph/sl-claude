PY ?= python3.13
SRC := src
OSI := examples/01_osi_model_ecommerce.yaml

.PHONY: demo bundle event ods polaris install clean help pdf

help:
	@echo "Targets:"
	@echo "  make demo     — full OSI -> Polaris -> Navigator -> OL -> ODS pipeline"
	@echo "  make bundle   — print the QueryGraph Navigator bundle for the OSI model"
	@echo "  make polaris  — print the proposed Polaris SemanticModel REST resource"
	@echo "  make event    — print an OpenLineage RunEvent carrying OSIMetricFacet"
	@echo "  make ods      — print the ODS data-product manifest"
	@echo "  make pdf      — render semantic-layer-report.md to semantic-layer-report.pdf via pandoc + typst"
	@echo "  make install  — install PyYAML (optional; demo falls back without it)"

pdf: semantic-layer-report.pdf

semantic-layer-report.pdf: semantic-layer-report.md
	pandoc semantic-layer-report.md -o semantic-layer-report.pdf \
	  --pdf-engine=typst \
	  --toc --toc-depth=3 \
	  -V title='Semantic Layers, OSI, and QueryGraph AI Navigator in Apache Polaris' \
	  -V subtitle='A comprehensive review with reference implementation' \
	  -V date='$(shell date -u +%Y-%m-%d)'

install:
	$(PY) -m pip install --user pyyaml

demo:
	cd $(SRC) && $(PY) demo.py

bundle:
	cd $(SRC) && $(PY) navigator_from_osi.py ../$(OSI)

polaris:
	cd $(SRC) && $(PY) polaris_osi_plugin.py ../$(OSI)

event:
	cd $(SRC) && $(PY) openlineage_emitter.py ../$(OSI) total_revenue SNOWFLAKE

ods:
	cd $(SRC) && $(PY) ods_packager.py ../$(OSI)

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
