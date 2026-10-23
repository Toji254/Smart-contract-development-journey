PYTHON ?= python3

.PHONY: test test-chain test-all solidity build run reset check

test:
	$(PYTHON) -m unittest discover -s tests -v

test-chain:
	$(PYTHON) -m unittest tests/test_chain_anvil.py -v

solidity:
	forge test -vv

test-all: test solidity

check: build test-all

build:
	forge build

run:
	$(PYTHON) run.py

reset:
	$(PYTHON) run.py --reset --seed-demo
