.PHONY: test pack check

test:
	python3 -m unittest discover -s tests -v

check: test
	python3 -m compileall -q intuition

pack: check
	./pack.sh
