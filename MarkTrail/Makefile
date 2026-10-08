PYTHON ?= python3

.PHONY: test solidity build run reset

test:
	$(PYTHON) -m unittest discover -s tests -v

solidity:
	forge test -vv

build:
	forge build

run:
	$(PYTHON) run.py

reset:
	$(PYTHON) run.py --reset
