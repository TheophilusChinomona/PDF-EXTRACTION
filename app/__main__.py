"""
Entry point for running the app as a module: python -m app
"""

import sys
from app.cli import main

if __name__ == "__main__":
    sys.exit(main())
