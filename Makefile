# One command: `make all`. On Windows without make, run the same lines by hand
# (each target is a single python call) or use `python -m studies.california.run_all`.
PY ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
PY = .venv/Scripts/python
endif

.PHONY: all env data test part_a part_b policy figures

all: data test part_a part_b policy figures

env:
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -r requirements.txt

data:
	$(PY) scripts/fetch.py all

test:
	$(PY) -m pytest -q tests

part_a:
	$(PY) -m studies.california.run_part_a snap
	$(PY) -m studies.california.run_part_a dimacs

part_b:
	$(PY) -m studies.california.part_b butte prepare
	$(PY) -m studies.california.part_b butte targets Paradise
	$(PY) -m studies.california.part_b butte rank
	$(PY) -m studies.california.part_b butte camp
	$(PY) -m studies.california.part_b la_foothills prepare
	$(PY) -m studies.california.part_b la_foothills rank
	$(PY) -m studies.california.part_b la_foothills retro

policy:
	$(PY) -m studies.california.policy butte extended
	$(PY) -m studies.california.policy butte run
	$(PY) -m studies.california.policy la_foothills extended
	$(PY) -m studies.california.policy la_foothills run

figures:
	$(PY) -m studies.california.figures a1 snap
	$(PY) -m studies.california.figures a1 dimacs
	$(PY) -m studies.california.figures hero butte
	$(PY) -m studies.california.figures_policy la_hero
	$(PY) -m studies.california.figures_policy camp_timeline
	$(PY) -m studies.california.figures_policy fixes
	$(PY) -m studies.california.figures_policy ladder
