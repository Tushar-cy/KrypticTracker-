#!/usr/bin/env python3
"""Main entry point for data collection service."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_collection.service import DataCollectionService

if __name__ == "__main__":
    try:
        service = DataCollectionService()
        service.start()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)




