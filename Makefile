.DEFAULT_GOAL := all

.PHONY: install
install:
	pip install -U pip pre-commit pip-tools
	pip install -r requirements/all.txt
	pre-commit install

.PHONY: refresh-lockfiles
refresh-lockfiles:
	@echo "Replacing requirements/*.txt files using pip-compile"
	find requirements/ -name '*.txt' ! -name 'all.txt' -type f -delete
	make update-lockfiles

.PHONY: update-lockfiles
update-lockfiles:
	@echo "Updating requirements/*.txt files using pip-compile"
	pip-compile --strip-extras -q -o requirements/linting.txt requirements/linting.in
	pip-compile --strip-extras -q -o requirements/tests.txt -c requirements/linting.txt requirements/tests.in
	pip-compile --strip-extras -q -o requirements/pyproject.txt \
		-c requirements/linting.txt -c requirements/tests.txt \
		pyproject.toml
	pip install --dry-run -r requirements/all.txt

.PHONY: format
format:
	ruff check --fix-only aioaws tests
	ruff format aioaws tests

.PHONY: lint
lint:
	ruff check aioaws tests
	ruff format --check aioaws tests

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
