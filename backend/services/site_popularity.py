"""
Site Popularity Tracker
Analyzes browser history to determine site popularity and usage patterns.
"""

import json
import sqlite3
from collections import defaultdict, Counter
from typing import Dict, List
from datetime import datetime, timedelta


class SitePopularityTracker:
    """Tracks and analyzes site popularity from browser history."""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def get_popular_sites(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """Get most popular sites from history."""
        cursor = self.db.cursor()
        
        # Get all history-related actions
        since = datetime.now().timestamp() - (days * 24 * 60 * 60)
        cursor.execute("""
            SELECT context_json, timestamp
            FROM actions
            WHERE (action_type = 'history_item' OR action_type = 'history_visit' 
                   OR action_type = 'tab_visit' OR action_type = 'page_load')
            AND timestamp > ?
            ORDER BY timestamp DESC
        """, (since,))
        
        rows = cursor.fetchall()
        site_stats = defaultdict(lambda: {
            'domain': '',
            'url': '',
            'visit_count': 0,
            'total_time': 0,
            'last_visit': 0,
            'titles': set(),
            'typed_count': 0
        })
        
        for row in rows:
            try:
                context = json.loads(row[0]) if row[0] else {}
                timestamp = row[1]
                
                # Extract domain
                url = context.get('url', '')
                if not url or not url.startswith('http'):
                    continue
                
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc
                except:
                    continue
                
                if not domain:
                    continue
                
                # Update stats
                stats = site_stats[domain]
                stats['domain'] = domain
                stats['url'] = url
                stats['visit_count'] += 1
                stats['last_visit'] = max(stats['last_visit'], timestamp)
                if context.get('title'):
                    stats['titles'].add(context['title'])
                if context.get('typed_count'):
                    stats['typed_count'] += context['typed_count']
                if context.get('visit_count'):
                    stats['visit_count'] += context.get('visit_count', 0) - 1
                    
            except Exception as e:
                continue
        
        # Convert to list and sort
        popular_sites = []
        for domain, stats in site_stats.items():
            popular_sites.append({
                'domain': domain,
                'url': stats['url'],
                'visit_count': stats['visit_count'],
                'last_visit': stats['last_visit'],
                'titles': list(stats['titles'])[:3],  # Top 3 titles
                'typed_count': stats['typed_count'],
                'popularity_score': stats['visit_count'] * 1.0 + stats['typed_count'] * 2.0
            })
        
        # Sort by popularity score
        popular_sites.sort(key=lambda x: x['popularity_score'], reverse=True)
        
        return popular_sites[:limit]
    
    def get_site_categories(self) -> Dict[str, List[str]]:
        """Categorize sites by type."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT DISTINCT context_json
            FROM actions
            WHERE action_type IN ('history_item', 'history_visit', 'tab_visit', 'page_load')
            AND context_json IS NOT NULL
        """)
        
        categories = defaultdict(list)
        
        for row in cursor.fetchall():
            try:
                context = json.loads(row[0]) if row[0] else {}
                url = context.get('url', '')
                domain = context.get('domain', '')
                
                if not domain:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        domain = parsed.netloc
                    except:
                        continue
                
                # Categorize
                if any(x in domain.lower() for x in ['github', 'gitlab', 'bitbucket']):
                    categories['Development'].append(domain)
                elif any(x in domain.lower() for x in ['stackoverflow', 'stackexchange', 'reddit', 'quora']):
                    categories['Q&A'].append(domain)
                elif any(x in domain.lower() for x in ['youtube', 'vimeo', 'twitch']):
                    categories['Video'].append(domain)
                elif any(x in domain.lower() for x in ['twitter', 'facebook', 'instagram', 'linkedin']):
                    categories['Social'].append(domain)
                elif any(x in domain.lower() for x in ['gmail', 'outlook', 'mail']):
                    categories['Email'].append(domain)
                elif any(x in domain.lower() for x in ['docs.google', 'notion', 'confluence']):
                    categories['Productivity'].append(domain)
                else:
                    categories['Other'].append(domain)
                    
            except:
                continue
        
        # Deduplicate
        for cat in categories:
            categories[cat] = list(set(categories[cat]))
        
        return dict(categories)


def get_popular_sites(db_connection, days: int = 7, limit: int = 20) -> List[Dict]:
    """Get popular sites from database."""
    tracker = SitePopularityTracker(db_connection)
    return tracker.get_popular_sites(days, limit)



