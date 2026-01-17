"""
Feature extraction pipeline for IRL training.
Converts raw actions → State vectors (128-256 dim) + Action vectors (32-64 dim)
"""

import json
import time
from typing import Dict, List, Tuple, Optional
import numpy as np
from datetime import datetime
from collections import deque, defaultdict


class FeatureExtractor:
    """
    Extracts state and action features from raw action logs.
    
    State Vector Components (128-256 dim):
    - Temporal: hour_of_day, day_of_week, time_since_last_action, session_duration
    - Context: current_app, current_language, current_domain, current_file_type
    - Activity: typing_speed, mouse_activity, context_switches, actions_in_last_hour
    - Behavioral: stuck_indicator, focus_indicator, energy_indicator
    - History: last_5_actions (sequence embedding), last_action_type
    
    Action Vector Components (32-64 dim):
    - action_type (one-hot)
    - target_app (one-hot/embedding)
    - action_duration
    - productivity_score (heuristic)
    """
    
    def __init__(self, state_dim: int = 192, action_dim: int = 48):
        """
        Initialize feature extractor.
        
        Args:
            state_dim: Dimension of state vector (default 192)
            action_dim: Dimension of action vector (default 48)
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Action history (last 5 actions for sequence context)
        self.action_history = deque(maxlen=5)
        
        # Session tracking
        self.session_start_time = time.time()
        self.last_action_time = time.time()
        
        # Activity counters (sliding window)
        self.recent_actions = deque(maxlen=3600)  # Last hour (assuming ~1 action/sec)
        self.recent_5min_actions = deque(maxlen=300)  # Last 5 minutes
        
        # Context tracking
        self.current_app = None
        self.current_domain = None
        self.current_language = None
        self.current_file_type = None
        
        # Activity metrics
        self.typing_speed_wpm = 0.0
        self.mouse_clicks_per_min = 0.0
        self.context_switches = 0
        self.last_context_switch_time = time.time()
        
        # Action type vocabulary (built dynamically)
        self.action_types = set()
        self.sources = set()
        
        # One-hot encodings
        self.action_type_to_idx = {}
        self.source_to_idx = {}
        self.next_action_idx = 0
        self.next_source_idx = 0
        
    def update_from_action(self, action_data: Dict) -> None:
        """
        Update internal state from a new action.
        Called before extracting features for the NEXT action.
        
        Args:
            action_data: Raw action data from database
        """
        timestamp = action_data.get('timestamp', time.time())
        source = action_data.get('source', 'unknown')
        action_type = action_data.get('action_type', 'unknown')
        context = action_data.get('context', {})
        
        # Update action history
        self.action_history.append({
            'type': action_type,
            'source': source,
            'timestamp': timestamp
        })
        
        # Update activity windows
        self.recent_actions.append(timestamp)
        self.recent_5min_actions.append(timestamp)
        
        # Update last action time
        time_since_last = timestamp - self.last_action_time
        self.last_action_time = timestamp
        
        # Track action types and sources
        self.action_types.add(action_type)
        self.sources.add(source)
        
        # Update action type mapping
        if action_type not in self.action_type_to_idx:
            self.action_type_to_idx[action_type] = self.next_action_idx
            self.next_action_idx += 1
        
        if source not in self.source_to_idx:
            self.source_to_idx[source] = self.next_source_idx
            self.next_source_idx += 1
        
        # Update context based on action
        self._update_context(source, action_type, context)
        
        # Update activity metrics
        self._update_activity_metrics(action_type, context, time_since_last)
    
    def _update_context(self, source: str, action_type: str, context: Dict) -> None:
        """Update current context (app, domain, language, file type)."""
        if source == 'chrome':
            if 'domain' in context:
                self.current_domain = context['domain']
            if 'url' in context:
                # Extract domain from URL if not already set
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(context['url'])
                    self.current_domain = parsed.hostname
                except:
                    pass
        
        elif source == 'vscode':
            self.current_app = 'vscode'
            if 'language' in context:
                self.current_language = context['language']
            if 'file' in context:
                # Extract file extension
                file_path = context['file']
                if '.' in file_path:
                    self.current_file_type = file_path.split('.')[-1]
        
        elif source == 'system':
            if 'application' in context:
                self.current_app = context['application']
        
        # Track context switches
        if action_type in ['tab_switch', 'app_switch', 'window_focus']:
            self.context_switches += 1
            self.last_context_switch_time = time.time()
    
    def _update_activity_metrics(self, action_type: str, context: Dict, time_since_last: float) -> None:
        """Update activity metrics (typing speed, mouse activity, etc.)."""
        # Update typing speed
        if action_type == 'keystroke' and 'typingSpeed' in context:
            self.typing_speed_wpm = context.get('typingSpeed', 0.0)
        elif action_type == 'activity_summary' and 'typingSpeed' in context:
            self.typing_speed_wpm = context.get('typingSpeed', 0.0)
        
        # Update mouse activity (clicks per minute)
        if action_type == 'mouse_click':
            # Calculate clicks per minute from recent actions
            now = time.time()
            recent_clicks = sum(1 for a in self.recent_actions 
                              if (now - a) < 60 and 
                              self._get_action_type_at_time(a) == 'mouse_click')
            self.mouse_clicks_per_min = recent_clicks
    
    def _get_action_type_at_time(self, timestamp: float) -> Optional[str]:
        """Helper to get action type at a specific timestamp (simplified)."""
        # This is a placeholder - in real implementation, we'd query the database
        return None
    
    def extract_state_vector(self) -> np.ndarray:
        """
        Extract current state vector (192 dim by default).
        
        Returns:
            State vector as numpy array
        """
        now = time.time()
        dt = datetime.fromtimestamp(now)
        
        state = np.zeros(self.state_dim, dtype=np.float32)
        idx = 0
        
        # === TEMPORAL FEATURES (8 dims) ===
        # Hour of day (0-1 normalized)
        state[idx] = dt.hour / 24.0
        idx += 1
        
        # Day of week (one-hot, 7 dims)
        day_of_week = dt.weekday()  # 0=Monday, 6=Sunday
        state[idx + day_of_week] = 1.0
        idx += 7
        
        # Time since last action (normalized, max 1 hour)
        time_since_last = min(now - self.last_action_time, 3600) / 3600.0
        state[idx] = time_since_last
        idx += 1
        
        # Session duration (normalized, max 8 hours)
        session_duration = min(now - self.session_start_time, 28800) / 28800.0
        state[idx] = session_duration
        idx += 1
        
        # === CONTEXT FEATURES (variable) ===
        # Current app (one-hot, max 10 apps)
        if self.current_app:
            app_hash = hash(self.current_app) % 10
            state[idx + app_hash] = 1.0
        idx += 10
        
        # Current language (one-hot, max 20 languages)
        if self.current_language:
            lang_hash = hash(self.current_language) % 20
            state[idx + lang_hash] = 1.0
        idx += 20
        
        # Current domain (one-hot, max 30 domains)
        if self.current_domain:
            domain_hash = hash(self.current_domain) % 30
            state[idx + domain_hash] = 1.0
        idx += 30
        
        # Current file type (one-hot, max 15 types)
        if self.current_file_type:
            file_hash = hash(self.current_file_type) % 15
            state[idx + file_hash] = 1.0
        idx += 15
        
        # === ACTIVITY FEATURES (8 dims) ===
        # Typing speed (WPM, normalized to max 120 WPM)
        state[idx] = min(self.typing_speed_wpm / 120.0, 1.0)
        idx += 1
        
        # Mouse clicks per minute (normalized to max 60/min)
        state[idx] = min(self.mouse_clicks_per_min / 60.0, 1.0)
        idx += 1
        
        # Context switches in last hour (normalized)
        recent_switches = sum(1 for a in self.recent_actions 
                            if (now - a) < 3600)
        state[idx] = min(recent_switches / 100.0, 1.0)  # Max 100 switches/hour
        idx += 1
        
        # Actions in last hour (normalized)
        actions_last_hour = len([a for a in self.recent_actions if (now - a) < 3600])
        state[idx] = min(actions_last_hour / 1000.0, 1.0)  # Max 1000 actions/hour
        idx += 1
        
        # Actions in last 5 minutes (normalized)
        actions_last_5min = len([a for a in self.recent_5min_actions if (now - a) < 300])
        state[idx] = min(actions_last_5min / 100.0, 1.0)  # Max 100 actions/5min
        idx += 1
        
        # Time in current context (normalized, max 1 hour)
        time_in_context = min(now - self.last_context_switch_time, 3600) / 3600.0
        state[idx] = time_in_context
        idx += 1
        
        # === BEHAVIORAL INDICATORS (3 dims) ===
        # Stuck indicator (no activity for long time)
        stuck_threshold = 300  # 5 minutes
        state[idx] = 1.0 if (now - self.last_action_time) > stuck_threshold else 0.0
        idx += 1
        
        # Focus indicator (low context switches = high focus)
        # Inverse: more time since last switch = more focus
        focus_score = min(time_in_context, 1.0)
        state[idx] = focus_score
        idx += 1
        
        # Energy indicator (based on activity rate)
        # High activity rate = high energy
        activity_rate = actions_last_5min / 5.0  # actions per minute
        state[idx] = min(activity_rate / 20.0, 1.0)  # Max 20 actions/min
        idx += 1
        
        # === HISTORY FEATURES (variable) ===
        # Last 5 actions (sequence embedding, 5 * 10 = 50 dims)
        for i, action in enumerate(self.action_history):
            if i < 5:
                # Simple embedding: hash action type to 10 dims
                action_hash = hash(action['type']) % 10
                state[idx + (i * 10) + action_hash] = 1.0
        idx += 50
        
        # Last action type (one-hot, max 50 types)
        if self.action_history:
            last_action = self.action_history[-1]['type']
            action_idx = self.action_type_to_idx.get(last_action, 0)
            if action_idx < 50:
                state[idx + action_idx] = 1.0
        idx += 50
        
        # === PADDING TO REACH state_dim ===
        # If we haven't filled all dimensions, pad with zeros
        # (This ensures consistent vector size)
        while idx < self.state_dim:
            state[idx] = 0.0
            idx += 1
        
        return state[:self.state_dim]
    
    def extract_action_vector(self, action_data: Dict) -> np.ndarray:
        """
        Extract action vector from action data.
        
        Args:
            action_data: Raw action data
            
        Returns:
            Action vector as numpy array
        """
        action = np.zeros(self.action_dim, dtype=np.float32)
        idx = 0
        
        action_type = action_data.get('action_type', 'unknown')
        source = action_data.get('source', 'unknown')
        context = action_data.get('context', {})
        timestamp = action_data.get('timestamp', time.time())
        
        # === ACTION TYPE (one-hot, max 30 types) ===
        action_type_idx = self.action_type_to_idx.get(action_type, 0)
        if action_type_idx < 30:
            action[idx + action_type_idx] = 1.0
        idx += 30
        
        # === TARGET APP/SOURCE (one-hot, max 5 sources) ===
        source_idx = self.source_to_idx.get(source, 0)
        if source_idx < 5:
            action[idx + source_idx] = 1.0
        idx += 5
        
        # === ACTION DURATION (1 dim) ===
        # For sustained actions, calculate duration
        duration = context.get('duration', 0.0)
        if duration == 0:
            # Estimate from context
            if 'timeOnPage' in context:
                duration = context['timeOnPage']
            elif 'duration_on_previous' in context:
                duration = context['duration_on_previous']
        
        # Normalize duration (max 1 hour)
        action[idx] = min(duration / 3600.0, 1.0)
        idx += 1
        
        # === PRODUCTIVITY SCORE (heuristic, 1 dim) ===
        productivity = self._calculate_productivity_score(action_type, context)
        action[idx] = productivity
        idx += 1
        
        # === ADDITIONAL CONTEXT (remaining dims) ===
        # Scroll depth (if applicable)
        if 'scroll_percentage' in context:
            action[idx] = context['scroll_percentage'] / 100.0
        idx += 1
        
        # Typing speed at time of action
        if 'typingSpeed' in context:
            action[idx] = min(context['typingSpeed'] / 120.0, 1.0)
        idx += 1
        
        # Fill remaining dimensions with zeros
        while idx < self.action_dim:
            action[idx] = 0.0
            idx += 1
        
        return action[:self.action_dim]
    
    def _calculate_productivity_score(self, action_type: str, context: Dict) -> float:
        """
        Calculate heuristic productivity score (0-1).
        
        Higher score = more productive action.
        """
        # Productive actions
        productive_actions = {
            'file_edit': 0.9,
            'file_save': 0.8,
            'git_commit': 0.95,
            'test_run': 0.85,
            'search': 0.6,  # Learning/research
            'tab_visit': 0.4,  # Browsing
            'scroll': 0.2,  # Passive
            'mouse_move': 0.1,  # Idle
        }
        
        base_score = productive_actions.get(action_type, 0.5)
        
        # Adjust based on context
        if action_type == 'file_edit' and 'linesChanged' in context:
            # More lines changed = more productive
            lines = context['linesChanged']
            base_score = min(0.9 + (lines / 100.0), 1.0)
        
        if action_type == 'tab_visit':
            # Productive domains
            domain = context.get('domain', '')
            if any(d in domain for d in ['github', 'stackoverflow', 'docs', 'wikipedia']):
                base_score = 0.7
        
        return base_score



