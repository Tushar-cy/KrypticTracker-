"""
Data Cleaning Service
Cleans old data while preserving training samples and metrics.
Strategy: Keep recent data + representative samples + aggregated metrics
"""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from pathlib import Path


class DataCleaner:
    """
    Smart data cleaning that preserves training data.
    
    Strategy:
    1. Keep all data from last N days (configurable, default 30)
    2. Archive old data but keep representative samples (1% sampling)
    3. Keep aggregated metrics/statistics forever
    4. Keep all insights and predictions
    5. Keep training-relevant patterns
    """
    
    def __init__(self, db_path: str, keep_days: int = 30, sample_rate: float = 0.01):
        self.db_path = db_path
        self.keep_days = keep_days
        self.sample_rate = sample_rate  # 1% of old data to keep
    
    def clean_old_actions(self, dry_run: bool = True) -> Dict:
        """
        Clean old actions while preserving training samples.
        
        Returns:
            Dict with stats about what would be/was cleaned
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = time.time() - (self.keep_days * 24 * 60 * 60)
        
        # Count old actions
        cursor.execute("""
            SELECT COUNT(*) FROM actions
            WHERE timestamp < ?
        """, (cutoff_time,))
        old_count = cursor.fetchone()[0]
        
        if old_count == 0:
            return {
                'status': 'no_cleanup_needed',
                'old_actions': 0,
                'kept_samples': 0,
                'deleted': 0
            }
        
        if dry_run:
            # Calculate what would be kept (1% sample)
            kept_samples = int(old_count * self.sample_rate)
            
            return {
                'status': 'dry_run',
                'old_actions': old_count,
                'kept_samples': kept_samples,
                'would_delete': old_count - kept_samples,
                'cutoff_date': datetime.fromtimestamp(cutoff_time).isoformat()
            }
        
        # Actually clean: Keep representative sample
        # Strategy: Keep every Nth action (where N = 1/sample_rate)
        step = int(1 / self.sample_rate)  # Keep every 100th action
        
        # Get IDs of actions to keep (sample)
        cursor.execute("""
            SELECT id FROM actions
            WHERE timestamp < ?
            ORDER BY timestamp
        """, (cutoff_time,))
        
        all_ids = [row[0] for row in cursor.fetchall()]
        ids_to_keep = set(all_ids[::step])  # Every Nth ID
        
        # Delete old actions except samples
        cursor.execute("""
            DELETE FROM actions
            WHERE timestamp < ? AND id NOT IN ({})
        """.format(','.join('?' * len(ids_to_keep))), 
            [cutoff_time] + list(ids_to_keep))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return {
            'status': 'cleaned',
            'old_actions': old_count,
            'kept_samples': len(ids_to_keep),
            'deleted': deleted,
            'cutoff_date': datetime.fromtimestamp(cutoff_time).isoformat()
        }
    
    def aggregate_metrics(self) -> Dict:
        """
        Create aggregated metrics from old data before cleaning.
        These metrics are kept forever.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = time.time() - (self.keep_days * 24 * 60 * 60)
        
        # Aggregate by source
        cursor.execute("""
            SELECT source, action_type, COUNT(*) as count
            FROM actions
            WHERE timestamp < ?
            GROUP BY source, action_type
        """, (cutoff_time,))
        
        source_metrics = {}
        for source, action_type, count in cursor.fetchall():
            if source not in source_metrics:
                source_metrics[source] = {}
            source_metrics[source][action_type] = count
        
        # Aggregate by hour of day
        cursor.execute("""
            SELECT 
                strftime('%H', datetime(timestamp, 'unixepoch')) as hour,
                COUNT(*) as count
            FROM actions
            WHERE timestamp < ?
            GROUP BY hour
            ORDER BY count DESC
        """, (cutoff_time,))
        
        hourly_patterns = {hour: count for hour, count in cursor.fetchall()}
        
        # Aggregate by day of week
        cursor.execute("""
            SELECT 
                strftime('%w', datetime(timestamp, 'unixepoch')) as day,
                COUNT(*) as count
            FROM actions
            WHERE timestamp < ?
            GROUP BY day
        """, (cutoff_time,))
        
        daily_patterns = {day: count for day, count in cursor.fetchall()}
        
        conn.close()
        
        return {
            'source_metrics': source_metrics,
            'hourly_patterns': hourly_patterns,
            'daily_patterns': daily_patterns,
            'aggregated_at': datetime.now().isoformat()
        }
    
    def save_aggregates(self, metrics: Dict):
        """Save aggregated metrics to a separate table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create aggregates table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aggregate_type TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        # Save metrics
        cursor.execute("""
            INSERT INTO data_aggregates (aggregate_type, data_json)
            VALUES (?, ?)
        """, ('old_data_metrics', json.dumps(metrics)))
        
        conn.commit()
        conn.close()
    
    def clean_with_preservation(self, dry_run: bool = True) -> Dict:
        """
        Main cleaning function that preserves training data.
        
        1. Aggregate metrics from old data
        2. Save aggregates
        3. Clean old data (keep samples)
        4. Keep all recent data, insights, predictions
        """
        print(f"🧹 Starting data cleaning (dry_run={dry_run})...")
        
        # Step 1: Aggregate metrics
        print("   📊 Aggregating metrics from old data...")
        metrics = self.aggregate_metrics()
        
        if not dry_run:
            # Step 2: Save aggregates
            print("   💾 Saving aggregated metrics...")
            self.save_aggregates(metrics)
            
            # Step 3: Clean old actions (keeps samples)
            print("   🗑️  Cleaning old actions (keeping samples)...")
            cleanup_result = self.clean_old_actions(dry_run=False)
            
            return {
                'status': 'success',
                'metrics_saved': True,
                'cleanup': cleanup_result,
                'aggregated_metrics': metrics
            }
        else:
            cleanup_result = self.clean_old_actions(dry_run=True)
            
            return {
                'status': 'dry_run',
                'cleanup': cleanup_result,
                'aggregated_metrics': metrics
            }


def create_cleanup_endpoint():
    """Create Flask blueprint for cleanup endpoint."""
    from flask import Blueprint, jsonify, request
    
    cleanup_bp = Blueprint('cleanup', __name__)
    
    @cleanup_bp.route('/cleanup', methods=['POST'])
    def cleanup_data():
        """Clean old data while preserving training samples."""
        try:
            data = request.get_json() or {}
            dry_run = data.get('dry_run', True)
            keep_days = data.get('keep_days', 30)
            
            # Get database path from app config
            from flask import current_app
            db = current_app.config.get('db')
            if not db:
                return jsonify({'error': 'Database not configured'}), 500
            
            db_path = db.db_path if hasattr(db, 'db_path') else 'data/kryptictrack.db'
            
            cleaner = DataCleaner(db_path, keep_days=keep_days)
            result = cleaner.clean_with_preservation(dry_run=dry_run)
            
            return jsonify(result), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return cleanup_bp




