.PHONY: test test-glm53 test-gpt6 test-opus5 test-benchmark check

test: test-glm53 test-gpt6 test-opus5 test-benchmark test-loop

test-glm53:
	$(MAKE) -C glm53 test

test-gpt6:
	python3 gpt6/scripts/test_all.py

test-opus5:
	python3 opus5/tools/offline_test_runner.py

check: test

test-benchmark:
	python3 -m unittest discover -s benchmark/tests -v

.PHONY: test-native-repair
test-native-repair:
	python3 benchmark/native_checks.py --solution glm53
	python3 benchmark/native_checks.py --solution opus5

.PHONY: start stop status shell
start:
	python3 src/gitive/launch.py
stop:
	docker compose -f src/gitive/compose.yaml stop
status:
	./gitive status
shell:
	./gitive shell

.PHONY: test-loop
test-loop:
	PYTHONPATH="$(CURDIR)/src:$(PYTHONPATH)" python3 -m unittest discover -s src/gitive/tests -v

.PHONY: test-contracts
test-contracts:
	PYTHONPATH="$(CURDIR)/src:$(PYTHONPATH)" python3 -m unittest discover -s src/gitive/tests -p test_contracts.py -v
