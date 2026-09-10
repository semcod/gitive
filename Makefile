.PHONY: test test-glm53 test-gpt6 test-opus5 check

test: test-glm53 test-gpt6 test-opus5

test-glm53:
	$(MAKE) -C glm53 test

test-gpt6:
	python3 gpt6/scripts/test_all.py

test-opus5:
	python3 opus5/tools/offline_test_runner.py

check: test
