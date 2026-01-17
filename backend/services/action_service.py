"""Service layer for action operations with batch insert support."""

import time
import json
from typing import List, Dict, Any, Optional
from backend.utils.logger import get_logger
from backend.utils.exceptions import DatabaseError

logger = get_logger("action_service")


class ActionService:
    """Service for managing actions with optimized batch operations."""
    
    def __init__(self, db_connection):
        """
        Initialize action service.
        
        Args:
            db_connection: Database connection
        """
        self.db = db_connection
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_size = 100  # Insert in batches of 100
    
    def log_action(
        self,
        source: str,
        action_type: str,
        context: Dict[str, Any],
        session_id: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> int:
        """
        Log a single action (buffered for batch insert).
        
        Args:
            source: Action source
            action_type: Type of action
            context: Action context
            session_id: Optional session ID
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Action ID (after batch flush)
        """
        action_data = {
            'timestamp': timestamp or time.time(),
            'source': source,
            'action_type': action_type,
            'context_json': json.dumps(context) if isinstance(context, dict) else (context or '{}'),
            'session_id': session_id
        }
        
        self._batch_buffer.append(action_data)
        
        # Flush if buffer is full
        if len(self._batch_buffer) >= self._batch_size:
            self.flush_batch()
        
        # Return a placeholder ID (actual ID assigned on flush)
        return len(self._batch_buffer)
    
    def flush_batch(self) -> int:
        """
        Flush buffered actions to database in a single transaction.
        
        Returns:
            Number of actions inserted
        """
        if not self._batch_buffer:
            return 0
        
        try:
            cursor = self.db.cursor()
            inserted_count = 0
            
            # Batch insert
            cursor.executemany("""
                INSERT INTO actions 
                (timestamp, source, action_type, context_json, session_id)
                VALUES (?, ?, ?, ?, ?)
            """, [
                (
                    action['timestamp'],
                    action['source'],
                    action['action_type'],
                    action['context_json'],
                    action['session_id']
                )
                for action in self._batch_buffer
            ])
            
            inserted_count = len(self._batch_buffer)
            self._batch_buffer.clear()
            
            self.db.commit()
            
            logger.debug("Batch insert completed", count=inserted_count)
            
            return inserted_count
            
        except Exception as e:
            self.db.rollback()
            logger.error("Batch insert failed", error=str(e))
            raise DatabaseError(f"Failed to insert actions: {str(e)}")
    
    def batch_insert_actions(self, actions: List[Dict[str, Any]]) -> int:
        """
        Insert multiple actions in a single transaction.
        
        Args:
            actions: List of action dictionaries with keys:
                - source, action_type, context, session_id (optional), timestamp (optional)
                
        Returns:
            Number of actions inserted
        """
        try:
            cursor = self.db.cursor()
            
            # Prepare data
            insert_data = []
            for action in actions:
                context = action.get('context', action.get('context_json', {}))
                insert_data.append((
                    action.get('timestamp', time.time()),
                    action['source'],
                    action['action_type'],
                    json.dumps(context) if isinstance(context, dict) else (context or '{}'),
                    action.get('session_id')
                ))
            
            # Batch insert
            cursor.executemany("""
                INSERT INTO actions 
                (timestamp, source, action_type, context_json, session_id)
                VALUES (?, ?, ?, ?, ?)
            """, insert_data)
            
            count = len(insert_data)
            self.db.commit()
            
            logger.info("Batch insert completed", count=count)
            
            return count
            
        except Exception as e:
            self.db.rollback()
            logger.error("Batch insert failed", error=str(e))
            raise DatabaseError(f"Failed to batch insert actions: {str(e)}")
    
    def get_actions(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        source: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get actions with optimized query (specific columns, not *).
        
        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            source: Source filter
            action_type: Action type filter
            limit: Maximum number of results
            
        Returns:
            List of action dictionaries
        """
        try:
            cursor = self.db.cursor()
            
            # Build query with specific columns
            query = """
                SELECT 
                    id, timestamp, source, action_type, context_json, session_id
                FROM actions
                WHERE 1=1
            """
            params = []
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            if source:
                query += " AND source = ?"
                params.append(source)
            
            if action_type:
                query += " AND action_type = ?"
                params.append(action_type)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            actions = []
            for row in cursor.fetchall():
                try:
                    context = json.loads(row[4]) if row[4] else {}
                except:
                    context = {}
                
                actions.append({
                    'id': row[0],
                    'timestamp': row[1],
                    'source': row[2],
                    'action_type': row[3],
                    'context': context,
                    'session_id': row[5]
                })
            
            return actions
            
        except Exception as e:
            logger.error("Failed to get actions", error=str(e))
            raise DatabaseError(f"Failed to get actions: {str(e)}")

