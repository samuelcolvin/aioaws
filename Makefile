.DEFAULT_GOAL := all
isort = isort aioaws tests
black = black aioaws tests
ruff = ruff aioaws tests

.PHONY: install
install:
	python -m pip install -U setuptools pip
	pip install -U -r requirements.txt
	pip install -U -r tests/requirements-linting.txt
	pip install -e .

.PHONY: format
format:
	$(isort)
	$(black)
	$(ruff) --fix --exit-zero

.PHONY: lint
lint:
	$(ruff)
	$(isort) --check-only --df
	$(black) --check --diff

.PHONY: mypy
mypy:
	mypy --version
	mypy aioaws

.PHONY: test
test:
	coverage run -m pytest

.PHONY: testcov
testcov: test
	@echo "building coverage html"
	@coverage html

.PHONY: all
all: lint mypy testcov

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -rf dist
	rm -rf site
