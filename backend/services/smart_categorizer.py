"""
Smart Categorization Service

Uses LLM to automatically categorize sessions and actions.
"""

from datetime import datetime
from typing import Dict, List, Optional
import json


class SmartCategorizer:
    """Automatically categorizes sessions and actions using LLM."""
    
    CATEGORIZATION_PROMPT = """Analyze these work actions and categorize the session.

**ACTIONS:**
{action_summary}

**CONTEXT:**
- Duration: {duration} minutes
- Apps Used: {apps}
- Files: {files}
- Commands: {commands}
- URLs: {urls}

**Task:** Categorize this session into ONE primary category:
- **learning**: Educational content, tutorials, documentation reading
- **building**: Creating new features, writing code, implementing
- **debugging**: Fixing bugs, troubleshooting, testing
- **research**: Exploring solutions, comparing options, investigating
- **planning**: Design, architecture, task planning, meetings
- **maintenance**: Refactoring, code review, dependency updates

**Output JSON:**
```json
{{
  "category": "...",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "tags": ["tag1", "tag2", "tag3"]
}}
```

Only respond with valid JSON."""
    
    def __init__(self, db_connection):
        """Initialize smart categorizer."""
        self.db = db_connection
    
    def categorize_session(self, session_id: int) -> Dict:
        """
        Categorize a work session using LLM.
        
        Args:
            session_id: ID of the session to categorize
        
        Returns:
            {category, confidence, reasoning, tags}
        """
        from backend.services.llm_service import get_llm_service
        
        llm = get_llm_service(self.db)
        
        # Get session data
        session_data = self._get_session_data(session_id)
        
        if not session_data:
            return {'category': 'unknown', 'confidence': 0, 'reasoning': 'No data', 'tags': []}
        
        # Format prompt
        prompt = self._format_categorization_prompt(session_data)
        
        try:
            response = llm.chat(prompt, max_tokens=200)
            result = self._parse_llm_response(response.get('response', '{}'))
        except:
            # Fallback to rule-based categorization
            result = self._fallback_categorization(session_data)
        
        # Store categorization
        self._store_categorization(session_id, result)
        
        return result
    
    def _get_session_data(self, session_id: int) -> Optional[Dict]:
        """Get all data for a session."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            SELECT start_time, end_time, metadata
            FROM work_sessions
            WHERE id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        start_time, end_time, metadata_str = row
        metadata = json.loads(metadata_str) if metadata_str else {}
        
        duration = (end_time - start_time) / 60  # minutes
        
        # Get actions for this session
        cursor.execute("""
            SELECT action_type, source, context_json
            FROM actions
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        actions = []
        apps = set()
        files = set()
        commands = []
        urls = set()
        
        for action_row in cursor.fetchall():
            action_type = action_row[0]
            source = action_row[1]
            context = json.loads(action_row[2]) if action_row[2] else {}
            
            actions.append(f"{source}:{action_type}")
            apps.add(source)
            
            if 'file_path' in context:
                files.add(context['file_path'].split('/')[-1])  # Just filename
            if 'command' in context:
                commands.append(context['command'])
            if 'url' in context:
                urls.add(context['url'])
        
        return {
            'duration': duration,
            'actions': actions[:50],  # Limit to avoid token limits
            'apps': list(apps)[:10],
            'files': list(files)[:20],
            'commands': commands[:20],
            'urls': list(urls)[:20],
            'metadata': metadata
        }
    
    def _format_categorization_prompt(self, session_data: Dict) -> str:
        """Format the categorization prompt."""
        # Create action summary
        action_summary = "\n".join([f"- {action}" for action in session_data['actions'][:20]])
        
        return self.CATEGORIZATION_PROMPT.format(
            action_summary=action_summary,
            duration=f"{session_data['duration']:.0f}",
            apps=", ".join(session_data['apps']),
            files=", ".join(session_data['files'][:10]),
            commands="\n".join([f"  $ {cmd}" for cmd in session_data['commands'][:10]]),
            urls="\n".join([f"  - {url[:80]}" for url in session_data['urls'][:10]])
        )
    
    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM JSON response."""
        try:
            # Try to extract JSON from markdown code blocks
            if '```json' in response:
                json_str = response.split('```json')[1].split('```')[0].strip()
            elif '```' in response:
                json_str = response.split('```')[1].split('```')[0].strip()
            else:
                json_str = response.strip()
            
            result = json.loads(json_str)
            
           # Validate
            if 'category' in result and 'confidence' in result:
                return {
                    'category': result['category'],
                    'confidence': result['confidence'],
                    'reasoning': result.get('reasoning', ''),
                    'tags': result.get('tags', [])
                }
        except:
            pass
        
        return {'category': 'unknown', 'confidence': 0, 'reasoning': 'Parse error', 'tags': []}
    
    def _fallback_categorization(self, session_data: Dict) -> Dict:
        """Rule-based fallback categorization."""
        apps = ' '.join(session_data['apps']).lower()
        commands = ' '.join(session_data['commands']).lower()
        files = ' '.join(session_data['files']).lower()
        urls = ' '.join(session_data['urls']).lower()
        
        all_text = f"{apps} {commands} {files} {urls}"
        
        # Rule-based detection
        if any(kw in all_text for kw in ['git commit', 'git push', '.py', '.js', '.tsx', 'code', 'vim']):
            if 'test' in all_text or 'debug' in all_text:
                return {'category': 'debugging', 'confidence': 0.7, 'reasoning': 'Testing/debugging detected', 'tags': ['code', 'debug']}
            return {'category': 'building', 'confidence': 0.7, 'reasoning': 'Coding activity detected', 'tags': ['code']}
        
        if any(kw in all_text for kw in ['docs', 'documentation', 'tutorial', 'learn', 'course']):
            return {'category': 'learning', 'confidence': 0.7, 'reasoning': 'Educational content detected', 'tags': ['learning']}
        
        if any(kw in all_text for kw in ['search', 'google', 'stackoverflow', 'github', 'compare']):
            return {'category': 'research', 'confidence': 0.6, 'reasoning': 'Research activity detected', 'tags': ['research']}
        
        return {'category': 'unknown', 'confidence': 0.3, 'reasoning': 'No clear pattern', 'tags': []}
    
    def _store_categorization(self, session_id: int, result: Dict):
        """Store categorization result in metadata."""
        cursor = self.db.cursor()
        
        cursor.execute("""
            UPDATE work_sessions
            SET session_type = ?
            WHERE id = ?
        """, (result['category'], session_id))
        
        self.db.commit()
    
    def auto_detect_project(self, file_paths: List[str]) -> Optional[str]:
        """
        Infer project name from file paths.
        
        Args:
            file_paths: List of file paths
        
        Returns:
            Project name or None
        """
        if not file_paths:
            return None
        
        # Extract common directory
        from pathlib import Path
        
        paths = [Path(p) for p in file_paths if p]
        if not paths:
            return None
        
        # Find common ancestor
        common_parts = None
        for path in paths:
            parts = path.parts
            if common_parts is None:
                common_parts = parts
            else:
                # Find common prefix
                new_common = []
                for i, part in enumerate(parts):
                    if i < len(common_parts) and part == common_parts[i]:
                        new_common.append(part)
                    else:
                        break
                common_parts = tuple(new_common)
        
        if common_parts and len(common_parts) > 0:
            # Return the last directory name (likely project root)
            return common_parts[-1]
        
        return None


def get_smart_categorizer(db_connection):
    """Get smart categorizer instance."""
    return SmartCategorizer(db_connection)
