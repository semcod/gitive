import sys
from .cli import main

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        sys.exit(1)
