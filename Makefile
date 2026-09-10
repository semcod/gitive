.PHONY: test test-glm53 test-gpt6 test-opus5 test-benchmark check

test: test-glm53 test-gpt6 test-opus5 test-benchmark

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
