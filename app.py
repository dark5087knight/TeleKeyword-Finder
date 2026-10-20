"""Direct script entry point for TeleKeyword Finder.

Allows running directly with:
    python app.py
or
    python main.py
"""

import asyncio
from pathlib import Path
import sys

# Ensure 'src' directory is in sys.path when running app.py directly
src_dir = str(Path(__file__).resolve().parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tgagent.main import main

if __name__ == "__main__":
    asyncio.run(main())
