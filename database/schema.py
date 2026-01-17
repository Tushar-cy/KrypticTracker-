"""Database schema definitions for KrypticTrack."""

def create_tables(db_connection):
    """Create all necessary tables for data collection."""
    cursor = db_connection.cursor()
    
    # Unified actions table (primary table for all sources)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            source TEXT NOT NULL,  -- 'vscode', 'chrome', 'system'
            action_type TEXT NOT NULL,
            context_json TEXT NOT NULL,  -- JSON string with action details
            state_vector BLOB,  -- Computed state vector (Phase 2)
            action_vector BLOB,  -- Computed action vector (Phase 2)
            session_id TEXT,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
    """)
    
    # Training runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            completed_at REAL,
            num_epochs INTEGER,
            final_loss REAL,
            accuracy REAL,
            model_path TEXT,
            notes TEXT,
            -- Data range tracking
            first_action_id INTEGER,
            last_action_id INTEGER,
            first_timestamp REAL,
            last_timestamp REAL,
            total_actions_used INTEGER,
            data_sources TEXT  -- JSON array of sources used
        )
    """)
    
    # Predictions log (for accuracy tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            state_json TEXT,
            predicted_action TEXT,
            confidence REAL,
            actual_action TEXT,  -- Filled in later when action occurs
            was_correct BOOLEAN,
            session_id TEXT
        )
    """)
    
    # Insights/patterns discovered
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discovered_at REAL NOT NULL,
            pattern_type TEXT,  -- 'preference', 'anomaly', 'trend', 'pattern'
            description TEXT,
            confidence REAL,
            evidence_json TEXT
        )
    """)
    
    # Sessions (daily/continuous tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            start_time REAL NOT NULL,
            end_time REAL,
            total_actions INTEGER DEFAULT 0,
            sources_used TEXT,  -- JSON array of sources
            context_summary TEXT  -- JSON object
        )
    """)
    
    # Work Sessions (automated session detection)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            duration_seconds REAL NOT NULL,
            action_count INTEGER NOT NULL,
            project TEXT,  -- Detected project name
            session_type TEXT,  -- 'coding', 'research', 'debugging', 'mixed'
            metadata TEXT,  -- JSON with full details (files, apps, commands, etc.)
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
    """)
    
    # Legacy tables (for backward compatibility with existing data collection)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keystrokes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            key_name TEXT,
            key_code INTEGER,
            is_press BOOLEAN,
            duration_ms REAL,
            active_window TEXT,
            session_id TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mouse_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            x INTEGER,
            y INTEGER,
            button TEXT,
            scroll_delta_x REAL,
            scroll_delta_y REAL,
            active_window TEXT,
            session_id TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            application_name TEXT,
            window_title TEXT,
            process_id INTEGER,
            duration_seconds REAL,
            session_id TEXT
        )
    """)
    
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actions(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_source ON actions(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type ON actions(action_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_session_id ON actions(session_id)")
    # Composite index for common query pattern: source + timestamp
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_source_timestamp ON actions(source, timestamp)")
    # Composite index for type + timestamp queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_type_timestamp ON actions(action_type, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_was_correct ON predictions(was_correct)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_discovered ON insights(discovered_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_training_runs_started ON training_runs(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_sessions_start_time ON work_sessions(start_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_sessions_project ON work_sessions(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_sessions_type ON work_sessions(session_type)")
    
    # User Goals tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_text TEXT NOT NULL,
            created_at REAL NOT NULL,
            target_date REAL,
            status TEXT DEFAULT 'active',
            keywords TEXT,
            category TEXT,
            metadata TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goal_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            relevant_actions INTEGER DEFAULT 0,
            total_actions INTEGER DEFAULT 0,
            time_spent_seconds REAL DEFAULT 0,
            summary TEXT,
            FOREIGN KEY (goal_id) REFERENCES user_goals(id)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_goals_status ON user_goals(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_goal_progress_date ON goal_progress(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_goal_progress_goal_id ON goal_progress(goal_id)")
    
    db_connection.commit()
    print("✅ Database tables created successfully")
    create_habit_tables(db_connection)


def create_habit_tables(conn):
    """Create tables for habit tracking."""
    cursor = conn.cursor()
    
    # User-defined habits
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            target_value REAL,
            unit TEXT,
            keywords TEXT,
            active BOOLEAN DEFAULT 1,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
    """)
    
    # Daily habit tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_name TEXT NOT NULL,
            date TEXT NOT NULL,
            completed BOOLEAN DEFAULT 0,
            value REAL,
            metadata TEXT,
            UNIQUE(habit_name, date)
        )
    """)
    
    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_habit_tracking_date ON habit_tracking(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_habit_tracking_name ON habit_tracking(habit_name)")
    
    conn.commit()
