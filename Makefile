.PHONY: help report test clean venv install-hooks security

PY      ?= python3
INPUT   ?= analysis_report.json
OUTPUT  ?= report.html
VENV    := .venv
PY_VENV := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

help:
	@echo "Targets:"
	@echo "  report         Generate $(OUTPUT) from $(INPUT)"
	@echo "  test           Run unit tests"
	@echo "  venv           Create .venv and install dev dependencies"
	@echo "  install-hooks  Install git pre-commit security hook (requires venv)"
	@echo "  security       Run bandit security scan manually"
	@echo "  clean          Remove generated artifacts"

report:
	$(PY) codebase_analysis_html_report.py --input "$(INPUT)" --output "$(OUTPUT)"

test:
	$(PY) -m unittest discover -s tests -p "test_*.py" -v

venv: requirements-dev.txt
	python3 -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements-dev.txt
	@echo "venv ready: $(VENV)"

install-hooks: venv
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "pre-commit hook installed."

security: venv
	$(VENV)/bin/bandit -r codebase_analysis_html_report.py tests/ -ll

clean:
	rm -f "$(OUTPUT)"

