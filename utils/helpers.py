"""Helper utility functions."""

import time
import uuid
import yaml
from pathlib import Path
from typing import Dict, Any

def get_active_window() -> str:
    """Get current active window name (platform-specific)."""
    try:
        import subprocess
        # Linux: try xdotool
        try:
            result = subprocess.run(
                ['xdotool', 'getactivewindow', 'getwindowname'],
                capture_output=True,
                text=True,
                timeout=0.1
            )
            return result.stdout.strip() or "Unknown"
        except:
            # Fallback: try wmctrl
            try:
                result = subprocess.run(
                    ['wmctrl', '-a'],
                    capture_output=True,
                    text=True,
                    timeout=0.1
                )
                return "Active"  # Simplified
            except:
                return "Unknown"
    except:
        return "Unknown"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    Automatically finds project root by looking for config/config.yaml.
    """
    config_file = Path(config_path)
    
    # If path is relative, try to find project root
    if not config_file.is_absolute():
        # Try current directory first
        if config_file.exists():
            pass  # Found it
        else:
            # Look for project root by searching for config/config.yaml
            # Start from current directory and go up
            current = Path.cwd()
            found = False
            
            # Check up to 5 levels up
            for _ in range(5):
                potential_config = current / config_path
                if potential_config.exists():
                    config_file = potential_config
                    found = True
                    break
                parent = current.parent
                if parent == current:  # Reached filesystem root
                    break
                current = parent
            
            if not found:
                # Last resort: try relative to this file's location
                utils_dir = Path(__file__).parent
                project_root = utils_dir.parent
                potential_config = project_root / config_path
                if potential_config.exists():
                    config_file = potential_config
                else:
                    raise FileNotFoundError(
                        f"Config file not found: {config_path}\n"
                        f"Searched from: {Path.cwd()}\n"
                        f"Tried: {potential_config}"
                    )
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config




