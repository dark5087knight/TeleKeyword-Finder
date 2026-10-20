from pathlib import Path
import asyncio
import sys


src_dir = str(Path(__file__).resolve().parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tgagent.main import main

if __name__ == "__main__":
    asyncio.run(main())
