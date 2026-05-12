"""Allow `python -m db ...` invocation (replaces `python src/db.py ...`)."""
from . import main

if __name__ == "__main__":
    main()
