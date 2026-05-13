.PHONY: help lint test audit check clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

lint: ## Shellcheck bash + byte-compile python.
	shellcheck bin/kiki lib/*.sh
	python3 -m py_compile mcp/kiki-mcp.py

test: ## Run bats smoke tests.
	bats tests/

audit: ## brew style + audit. Requires the formula staged in a local tap.
	@brew style Formula/kiki.rb
	@tap_dir="$$(brew --repository)/Library/Taps/plarotta/homebrew-tap"; \
		mkdir -p "$$tap_dir/Formula"; \
		cp Formula/kiki.rb "$$tap_dir/Formula/"; \
		brew audit --formula --strict plarotta/tap/kiki

check: lint test audit ## All local checks.

clean: ## Remove pyc caches.
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
