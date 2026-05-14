.PHONY: help lint test audit check clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

lint: ## Shellcheck bash + byte-compile python.
	shellcheck bin/kiki lib/*.sh
	python3 -m py_compile mcp/kiki-mcp.py lib/stream-claude.py

test: ## Run bats smoke tests.
	bats tests/

audit: ## brew style + audit. Stages formula in a transient throwaway tap.
	@brew style Formula/kiki.rb
	@ns_dir="$$(brew --repository)/Library/Taps/kiki-audit"; \
		trap 'rm -rf "$$ns_dir"' EXIT; \
		mkdir -p "$$ns_dir/homebrew-audit/Formula"; \
		cp Formula/kiki.rb "$$ns_dir/homebrew-audit/Formula/"; \
		brew audit --formula --strict kiki-audit/audit/kiki

check: lint test audit ## All local checks.

clean: ## Remove pyc caches.
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
