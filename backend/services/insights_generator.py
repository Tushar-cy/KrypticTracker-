"""
Insights Generator Service
Analyzes behavior patterns and generates actionable insights.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict, Counter
import statistics


class InsightsGenerator:
    """Generates behavioral insights from collected data."""
    
    def __init__(self, db_connection, llm_service=None):
        self.db = db_connection
        self.llm_service = llm_service
    
    def generate_all_insights(self) -> List[Dict]:
        """Generate all available insights."""
        insights = []
        
        # Time-based patterns
        insights.extend(self._analyze_time_patterns())
        
        # Application/domain patterns
        insights.extend(self._analyze_domain_patterns())
        
        # Action sequence patterns
        insights.extend(self._analyze_action_sequences())
        
        # Productivity patterns
        insights.extend(self._analyze_productivity_patterns())
        
        # Behavioral trends
        insights.extend(self._analyze_behavioral_trends())
        
        # Enhance insights with LLM if available
        if self.llm_service and self.llm_service.is_available():
            insights = self._enhance_insights_with_llm(insights)
        
        return insights
    
    def _enhance_insights_with_llm(self, insights: List[Dict]) -> List[Dict]:
        """Enhance insight descriptions using LLM for more human-friendly language."""
        if not self.llm_service or not self.llm_service.is_available():
            return insights
        
        enhanced = []
        for insight in insights:
            try:
                # Create a prompt to enhance the insight
                prompt = f"""Rewrite this behavioral insight to be more conversational, engaging, and human-friendly while keeping all the facts accurate:

Original: {insight['description']}
Pattern Type: {insight.get('pattern_type', 'Unknown')}
Confidence: {insight.get('confidence', 0.5):.0%}

Rules:
- Keep all numbers and facts exactly the same
- Make it sound more natural and conversational
- Use second person ("you")
- Keep it to 1-2 sentences
- Make it feel personal and insightful

Enhanced version:"""
                
                response = self.llm_service.chat(prompt)
                if response and not response.startswith("Error"):
                    insight['description'] = response.strip()
                    insight['llm_enhanced'] = True
            except Exception as e:
                # If LLM fails, keep original description
                pass
            
            enhanced.append(insight)
        
        return enhanced
    
    def _analyze_time_patterns(self) -> List[Dict]:
        """Analyze time-based behavior patterns."""
        insights = []
        cursor = self.db.cursor()
        
        # Get actions with timestamps
        cursor.execute("""
            SELECT timestamp, source, action_type
            FROM actions
            ORDER BY timestamp DESC
            LIMIT 10000
        """)
        
        rows = cursor.fetchall()
        if len(rows) < 100:
            return insights
        
        # Analyze by hour of day
        hour_activity = defaultdict(int)
        for timestamp, source, action_type in rows:
            dt = datetime.fromtimestamp(timestamp)
            hour_activity[dt.hour] += 1
        
        if hour_activity:
            peak_hour = max(hour_activity.items(), key=lambda x: x[1])
            low_hour = min(hour_activity.items(), key=lambda x: x[1])
            
            if peak_hour[1] > low_hour[1] * 1.5:  # Significant difference
                insights.append({
                    'pattern_type': 'Peak Productivity Hours',
                    'description': f'You are most active between {peak_hour[0]}:00-{peak_hour[0]+1}:00 ({peak_hour[1]} actions). Consider scheduling important work during this time.',
                    'confidence': min(0.9, peak_hour[1] / (sum(hour_activity.values()) / len(hour_activity))),
                    'evidence': {
                        'peak_hour': peak_hour[0],
                        'peak_actions': peak_hour[1],
                        'low_hour': low_hour[0],
                        'low_actions': low_hour[1]
                    },
                    'category': 'productivity',
                    'actionable': True
                })
        
        # Analyze by day of week
        day_activity = defaultdict(int)
        for timestamp, source, action_type in rows:
            dt = datetime.fromtimestamp(timestamp)
            day_activity[dt.strftime('%A')] += 1
        
        if day_activity:
            most_active_day = max(day_activity.items(), key=lambda x: x[1])
            avg_activity = sum(day_activity.values()) / len(day_activity)
            
            if most_active_day[1] > avg_activity * 1.3:
                insights.append({
                    'pattern_type': 'Weekly Activity Pattern',
                    'description': f'{most_active_day[0]} is your most productive day ({most_active_day[1]} actions). You might want to plan important tasks for this day.',
                    'confidence': 0.75,
                    'evidence': dict(day_activity),
                    'category': 'productivity',
                    'actionable': True
                })
        
        return insights
    
    def _analyze_domain_patterns(self) -> List[Dict]:
        """Analyze domain/application usage patterns."""
        insights = []
        cursor = self.db.cursor()
        
        # Get actions with context
        cursor.execute("""
            SELECT source, action_type, context_json
            FROM actions
            WHERE context_json IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5000
        """)
        
        rows = cursor.fetchall()
        if len(rows) < 50:
            return insights
        
        # Analyze domains
        domains = defaultdict(int)
        domain_sources = defaultdict(set)
        
        for source, action_type, context_json in rows:
            try:
                context = json.loads(context_json) if context_json else {}
                domain = context.get('domain') or context.get('to_domain') or context.get('url', '').split('/')[2] if context.get('url') else None
                
                if domain:
                    domains[domain] += 1
                    domain_sources[domain].add(source)
            except:
                continue
        
        if domains:
            top_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]
            
            for domain, count in top_domains:
                if count > 50:  # Significant usage
                    sources = list(domain_sources[domain])
                    insight = {
                        'pattern_type': 'Frequent Domain Usage',
                        'description': f'You frequently visit {domain} ({count} actions). This might indicate a key resource in your workflow.',
                        'confidence': min(0.85, count / 200),
                        'evidence': {
                            'domain': domain,
                            'action_count': count,
                            'sources': sources
                        },
                        'category': 'usage',
                        'actionable': False
                    }
                    insights.append(insight)
        
        # Analyze source distribution
        source_counts = defaultdict(int)
        for source, _, _ in rows:
            source_counts[source] += 1
        
        if source_counts:
            total = sum(source_counts.values())
            dominant_source = max(source_counts.items(), key=lambda x: x[1])
            
            if dominant_source[1] / total > 0.7:  # >70% from one source
                insights.append({
                    'pattern_type': 'Source Concentration',
                    'description': f'{dominant_source[0].upper()} accounts for {dominant_source[1]/total*100:.1f}% of your activity. Consider diversifying data sources for better insights.',
                    'confidence': 0.8,
                    'evidence': dict(source_counts),
                    'category': 'data_quality',
                    'actionable': True
                })
        
        return insights
    
    def _analyze_action_sequences(self) -> List[Dict]:
        """Analyze common action sequences."""
        insights = []
        cursor = self.db.cursor()
        
        # Get recent actions in sequence
        cursor.execute("""
            SELECT source, action_type
            FROM actions
            ORDER BY timestamp ASC
            LIMIT 1000
        """)
        
        rows = cursor.fetchall()
        if len(rows) < 20:
            return insights
        
        # Find common 2-action sequences
        sequences = defaultdict(int)
        for i in range(len(rows) - 1):
            seq = f"{rows[i][1]} → {rows[i+1][1]}"
            sequences[seq] += 1
        
        if sequences:
            top_sequences = sorted(sequences.items(), key=lambda x: x[1], reverse=True)[:3]
            
            for seq, count in top_sequences:
                if count > 10:  # Significant pattern
                    insights.append({
                        'pattern_type': 'Action Sequence Pattern',
                        'description': f'You frequently do: {seq.replace("_", " ").title()} ({count} times). This suggests a common workflow pattern.',
                        'confidence': min(0.75, count / 50),
                        'evidence': {
                            'sequence': seq,
                            'frequency': count
                        },
                        'category': 'workflow',
                        'actionable': False
                    })
        
        return insights
    
    def _analyze_productivity_patterns(self) -> List[Dict]:
        """Analyze productivity-related patterns."""
        insights = []
        cursor = self.db.cursor()
        
        # Get actions with timing
        cursor.execute("""
            SELECT timestamp, action_type, source
            FROM actions
            ORDER BY timestamp DESC
            LIMIT 5000
        """)
        
        rows = cursor.fetchall()
        if len(rows) < 100:
            return insights
        
        # Calculate action rate (actions per hour)
        if len(rows) > 1:
            time_span = rows[0][0] - rows[-1][0]  # seconds
            hours = time_span / 3600
            actions_per_hour = len(rows) / hours if hours > 0 else 0
            
            if actions_per_hour > 500:
                insights.append({
                    'pattern_type': 'High Activity Level',
                    'description': f'You average {actions_per_hour:.0f} actions per hour, indicating very high engagement with your system.',
                    'confidence': 0.9,
                    'evidence': {
                        'actions_per_hour': actions_per_hour,
                        'total_actions': len(rows),
                        'time_span_hours': hours
                    },
                    'category': 'productivity',
                    'actionable': False
                })
        
        # Analyze action type distribution
        action_types = Counter(row[1] for row in rows)
        total_actions = len(rows)
        
        if action_types:
            top_action = action_types.most_common(1)[0]
            if top_action[1] / total_actions > 0.3:  # >30% of actions
                insights.append({
                    'pattern_type': 'Dominant Action Type',
                    'description': f'{top_action[0].replace("_", " ").title()} accounts for {top_action[1]/total_actions*100:.1f}% of your activity. This is your primary interaction type.',
                    'confidence': 0.8,
                    'evidence': {
                        'action_type': top_action[0],
                        'percentage': top_action[1] / total_actions,
                        'count': top_action[1]
                    },
                    'category': 'behavior',
                    'actionable': False
                })
        
        return insights
    
    def _analyze_behavioral_trends(self) -> List[Dict]:
        """Analyze behavioral trends over time."""
        insights = []
        cursor = self.db.cursor()
        
        # Get actions grouped by day (SQLite doesn't have DATE function, use strftime)
        cursor.execute("""
            SELECT 
                strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch')) as day,
                COUNT(*) as count
            FROM actions
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
        """)
        
        rows = cursor.fetchall()
        if len(rows) < 7:  # Need at least a week
            return insights
        
        daily_counts = [row[1] for row in rows]
        
        # Check for increasing trend
        if len(daily_counts) >= 7:
            recent_avg = statistics.mean(daily_counts[:7])
            older_avg = statistics.mean(daily_counts[7:14]) if len(daily_counts) >= 14 else recent_avg
            
            if recent_avg > older_avg * 1.2:  # 20% increase
                insights.append({
                    'pattern_type': 'Increasing Activity Trend',
                    'description': f'Your activity has increased by {(recent_avg/older_avg - 1)*100:.0f}% in the last week. You might be entering a more productive phase.',
                    'confidence': 0.7,
                    'evidence': {
                        'recent_avg': recent_avg,
                        'older_avg': older_avg,
                        'trend': 'increasing'
                    },
                    'category': 'trend',
                    'actionable': False
                })
            elif recent_avg < older_avg * 0.8:  # 20% decrease
                insights.append({
                    'pattern_type': 'Decreasing Activity Trend',
                    'description': f'Your activity has decreased by {(1 - recent_avg/older_avg)*100:.0f}% in the last week. Consider reviewing your workflow.',
                    'confidence': 0.7,
                    'evidence': {
                        'recent_avg': recent_avg,
                        'older_avg': older_avg,
                        'trend': 'decreasing'
                    },
                    'category': 'trend',
                    'actionable': True
                })
        
        return insights
    
    def save_insights(self, insights: List[Dict]):
        """Save insights to database with deduplication."""
        cursor = self.db.cursor()
        
        # First, clear old insights to prevent duplicates
        cursor.execute("DELETE FROM insights")
        
        # Insert new insights
        for insight in insights:
            cursor.execute("""
                INSERT INTO insights 
                (discovered_at, pattern_type, description, confidence, evidence_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().timestamp(),
                insight['pattern_type'],
                insight['description'],
                insight.get('confidence', 0.5),
                json.dumps(insight.get('evidence', {}))
            ))
        
        self.db.commit()


def generate_insights(db_connection) -> List[Dict]:
    """Generate and save insights."""
    generator = InsightsGenerator(db_connection)
    insights = generator.generate_all_insights()
    generator.save_insights(insights)
    return insights

