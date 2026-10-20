"""Direct script entry point for TeleKeyword Finder.

Allows running directly with:
    python app.py
or
    python main.py
"""

import asyncio
from tgagent.main import main

if __name__ == "__main__":
    asyncio.run(main())
