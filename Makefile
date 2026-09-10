.PHONY: test test-glm53 test-opus5 check

test: test-glm53 test-opus5

test-glm53:
	$(MAKE) -C glm53 test

test-opus5:
	python3 opus5/tools/offline_test_runner.py

check: test
