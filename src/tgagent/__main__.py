"""CLI entry point for tgagent."""

import asyncio
from tgagent.main import main

if __name__ == "__main__":
    asyncio.run(main())
