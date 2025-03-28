.PHONY: version/get
version/get: ## Set version.
	@uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version
	
.PHONY: version/set
version/set: ## Set version.
	@uvx --from=toml-cli toml set --toml-path=pyproject.toml project.version ${v}
	@git add pyproject.toml
	@git commit -m "chore: bump v$$(make version/get)"
	@make install

.PHONY: publish
publish: ## Push git tag and publish version to PyPI.
	@git tag v$$(make version/get)
	@git tag latest -f
	@git push -f --tags
	
.PHONY: run
run: ## Run the project.
	uv run griptape-nodes
	
.PHONY: install
install: ## Install all dependencies.
	@make install/all

.PHONY: install/core
install/core: ## Install core dependencies.
	@uv sync

.PHONY: install/all
install/all: ## Install all dependencies.
	@uv sync --all-groups --all-extras

.PHONY: install/dev
install/dev: ## Install dev dependencies.
	@uv sync --group dev

.PHONY: install/test
install/test: ## Install test dependencies.
	@uv sync --group test

.PHONY: lint
lint: ## Lint project.
	@uv run ruff check --fix

.PHONY: format
format: ## Format project.
	@uv run ruff format
	@uv run mdformat .

.PHONY: fix
fix: ## Fix project.
	@make format
	@uv run ruff check --fix --unsafe-fixes

.PHONY: check
check: check/format check/lint check/types check/spell ## Run all checks.

.PHONY: check/format
check/format:
	@uv run ruff format --check
	@uv run mdformat --check .

.PHONY: check/lint
check/lint:
	@uv run ruff check

.PHONY: check/types
check/types:
	@uv run pyright .
	
.PHONY: check/spell
check/spell:
	@uv run typos 

.PHONY: test  ## Run all tests.
test: test/unit test/integration

.PHONY: test/unit
test/unit: ## Run unit tests.
	@uv run pytest -n auto tests/unit

.PHONY: test/integration
test/integration: ## Run integration tests.
	@uv run pytest -n auto tests/integration

.PHONY: test/integration/%
test/integration/%: ## Run specific integration tests.
	@uv run pytest -n auto tests/integration -k $*

.PHONY: docs
docs: ## Build documentation.
	@uv run python -m mkdocs build --clean --strict 

.PHONY: docs/serve
docs/serve: ## Serve documentation.
	@uv run python -m mkdocs serve
	
.DEFAULT_GOAL := help
.PHONY: help
help: ## Print Makefile help text.
	@# Matches targets with a comment in the format <target>: ## <comment>
	@# then formats help output using these values.
	@grep -E '^[a-zA-Z_\/-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; \
		{printf "\033[36m%-12s\033[0m%s\n", $$1, $$2}'
