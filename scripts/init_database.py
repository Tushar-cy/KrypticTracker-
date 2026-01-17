#!/usr/bin/env python3
"""Initialize the database with schema."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager
from database.schema import create_tables
from utils.helpers import load_config

def main():
    """Initialize database."""
    print("🗄️  Initializing KrypticTrack database...")
    
    try:
        config = load_config()
        db_config = config['database']
        
        db = DatabaseManager(
            db_path=db_config['path'],
            encrypted=db_config['encrypted']
        )
        db.connect()
        
        print(f"📁 Database path: {db_config['path']}")
        print(f"🔒 Encryption: {db_config['encrypted']}")
        
        create_tables(db.connection)
        
        db.close()
        print("✅ Database initialized successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()




