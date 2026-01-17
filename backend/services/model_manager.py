"""
Model Manager Service
Handles loading and using trained IRL models for predictions.
"""

import torch
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import json
import time

from models.irl_algorithm import MaxEntIRL
from encoding.feature_extractor import FeatureExtractor


class ModelManager:
    """Manages IRL model loading and predictions."""
    
    def __init__(self):
        self.model: Optional[MaxEntIRL] = None
        self.feature_extractor: Optional[FeatureExtractor] = None
        self.model_path: Optional[str] = None
        self.model_loaded = False
        self.load_time = None
    
    def load_latest_model(self, checkpoint_dir: str = "models/checkpoints") -> bool:
        """
        Load the latest trained model from checkpoint directory.
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            checkpoint_path = Path(checkpoint_dir)
            if not checkpoint_path.exists():
                return False
            
            # Find latest model
            models = sorted(
                checkpoint_path.glob('reward_model_*.pt'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not models:
                return False
            
            latest_model = models[0]
            return self.load_model(str(latest_model))
            
        except Exception as e:
            print(f"Error loading latest model: {e}")
            return False
    
    def load_model(self, model_path: str) -> bool:
        """
        Load a specific model from path.
        
        Args:
            model_path: Path to model checkpoint
            
        Returns:
            True if loaded successfully
        """
        try:
            if not Path(model_path).exists():
                return False
            
            # Load checkpoint to get dimensions
            checkpoint = torch.load(model_path, map_location='cpu')
            state_dim = checkpoint.get('state_dim', 192)
            action_dim = checkpoint.get('action_dim', 48)
            
            # Initialize IRL model
            self.model = MaxEntIRL(
                state_dim=state_dim,
                action_dim=action_dim,
                learning_rate=0.001  # Not used for inference
            )
            
            # Load weights
            self.model.load_model(model_path)
            
            # Initialize feature extractor
            self.feature_extractor = FeatureExtractor(
                state_dim=state_dim,
                action_dim=action_dim
            )
            
            self.model_path = model_path
            self.model_loaded = True
            self.load_time = time.time()
            
            print(f"✅ Model loaded: {model_path}")
            return True
            
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def predict_next_action(self, recent_actions: List[Dict], use_llm: bool = False, llm_service=None) -> Dict:
        """
        Predict the next likely action based on recent behavior.
        
        Args:
            recent_actions: List of recent actions (last 10-20)
            use_llm: Whether to generate LLM explanation
            llm_service: LLMService instance for explanations
            
        Returns:
            Dict with predicted action, confidence, and optional LLM explanation
        """
        if not self.model_loaded or not self.model or not self.feature_extractor:
            return {
                'predicted_action': None,
                'confidence': 0.0,
                'message': 'Model not loaded'
            }
        
        try:
            # Update feature extractor with recent actions
            for action in recent_actions[-10:]:  # Use last 10 actions
                self.feature_extractor.update_from_action(action)
            
            # Get current state
            current_state = self.feature_extractor.extract_state_vector()
            
            # Common action types to evaluate
            common_actions = [
                'tab_switch', 'tab_visit', 'page_load', 'scroll',
                'keystroke', 'mouse_click', 'file_edit', 'file_save'
            ]
            
            # Evaluate rewards for different actions
            action_rewards = []
            for action_type in common_actions:
                # Create action vector for this action type
                action_data = {
                    'action_type': action_type,
                    'source': recent_actions[-1].get('source', 'chrome') if recent_actions else 'chrome',
                    'timestamp': time.time(),
                    'context': recent_actions[-1].get('context', {}) if recent_actions else {}
                }
                
                action_vector = self.feature_extractor.extract_action_vector(action_data)
                
                # Predict reward
                reward = self.model.predict_reward(current_state, action_vector)
                action_rewards.append({
                    'action_type': action_type,
                    'reward': reward
                })
            
            # Sort by reward (higher = more likely)
            action_rewards.sort(key=lambda x: x['reward'], reverse=True)
            
            if not action_rewards:
                return {
                    'predicted_action': None,
                    'confidence': 0.0,
                    'message': 'No predictions available'
                }
            
            # Get top prediction
            top_prediction = action_rewards[0]
            
            # Calculate confidence (normalize rewards)
            rewards = [ar['reward'] for ar in action_rewards]
            if len(rewards) > 1:
                reward_range = max(rewards) - min(rewards)
                if reward_range > 0:
                    confidence = (top_prediction['reward'] - min(rewards)) / reward_range
                else:
                    confidence = 0.5
            else:
                confidence = 0.5
            
            result = {
                'predicted_action': top_prediction['action_type'],
                'confidence': min(max(confidence, 0.0), 1.0),  # Clamp to [0, 1]
                'reward': top_prediction['reward'],
                'top_3': action_rewards[:3],
                'message': 'Prediction successful',
                'current_state': self._get_current_state(recent_actions),
                'recent_history': self._format_recent_history(recent_actions),
                'time_estimate': self._estimate_time(recent_actions),
                'countdown_seconds': self._estimate_seconds(recent_actions)
            }
            
            # Add LLM explanation if requested
            if use_llm and llm_service:
                try:
                    explanation = llm_service.explain_prediction({
                        'current_state': result['current_state'],
                        'predicted_action': result['predicted_action'],
                        'confidence': result['confidence'],
                        'recent_history': result['recent_history'],
                        'time_estimate': result['time_estimate']
                    })
                    result['explanation'] = explanation
                except Exception as e:
                    result['explanation'] = f"Prediction: {result['predicted_action']} ({result['confidence']:.0%} confident)"
            
            return result
            
        except Exception as e:
            print(f"Error predicting next action: {e}")
            return {
                'predicted_action': None,
                'confidence': 0.0,
                'message': f'Prediction error: {str(e)}'
            }
    
    def _get_current_state(self, recent_actions: List[Dict]) -> Dict:
        """Extract current state information."""
        if not recent_actions:
            return {'app': 'Unknown', 'duration_minutes': 0, 'context': 'Unknown'}
        
        last_action = recent_actions[-1]
        source = last_action.get('source', 'unknown')
        
        # Calculate duration on current app
        duration_minutes = 0
        if len(recent_actions) > 1:
            current_time = time.time()
            first_action_time = recent_actions[0].get('timestamp', current_time)
            duration_minutes = (current_time - first_action_time) / 60
        
        return {
            'app': source,
            'duration_minutes': round(duration_minutes, 1),
            'context': last_action.get('action_type', 'unknown')
        }
    
    def _format_recent_history(self, recent_actions: List[Dict]) -> List[Dict]:
        """Format recent actions for LLM context."""
        formatted = []
        current_time = time.time()
        
        for action in recent_actions[-5:]:  # Last 5 actions
            action_time = action.get('timestamp', current_time)
            time_ago = current_time - action_time
            
            if time_ago < 60:
                time_str = f"{int(time_ago)}s ago"
            elif time_ago < 3600:
                time_str = f"{int(time_ago/60)}m ago"
            else:
                time_str = f"{int(time_ago/3600)}h ago"
            
            formatted.append({
                'action': action.get('action_type', 'unknown'),
                'source': action.get('source', 'unknown'),
                'time_ago': time_str
            })
        
        return formatted
    
    def _estimate_time(self, recent_actions: List[Dict]) -> str:
        """Estimate when next action will occur."""
        if not recent_actions:
            return "soon"
        
        # Get average time between actions
        if len(recent_actions) > 1:
            times = [a.get('timestamp', 0) for a in recent_actions]
            intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
            avg_interval = sum(intervals) / len(intervals) if intervals else 60
            
            if avg_interval < 30:
                return "very soon"
            elif avg_interval < 120:
                return "in 1-3 minutes"
            elif avg_interval < 300:
                return "in 3-5 minutes"
            else:
                return "in 5-10 minutes"
        
        return "soon"
    
    def _estimate_seconds(self, recent_actions: List[Dict]) -> int:
        """Estimate seconds until next action (for countdown)."""
        if not recent_actions:
            return 120  # Default 2 minutes
        
        # Get average time between actions
        if len(recent_actions) > 1:
            times = [a.get('timestamp', 0) for a in recent_actions]
            intervals = [times[i+1] - times[i] for i in range(len(times)-1)]
            avg_interval = sum(intervals) / len(intervals) if intervals else 120
            
            # Return average interval, clamped to reasonable range
            return int(min(max(avg_interval, 30), 600))  # 30s to 10min
        
        return 120
    
    def evaluate_model(self, test_actions: List[Dict]) -> Dict:
        """
        Evaluate model performance on test actions.
        
        Args:
            test_actions: List of actions to evaluate
            
        Returns:
            Dict with evaluation metrics
        """
        if not self.model_loaded or not self.model:
            return {
                'accuracy': 0.0,
                'avg_reward': 0.0,
                'message': 'Model not loaded'
            }
        
        try:
            rewards = []
            correct_predictions = 0
            total_predictions = 0
            
            for i in range(1, len(test_actions)):
                # Get recent actions up to this point
                recent = test_actions[:i]
                
                # Predict next action
                prediction = self.predict_next_action(recent)
                
                if prediction['predicted_action']:
                    total_predictions += 1
                    actual_action = test_actions[i].get('action_type')
                    
                    if prediction['predicted_action'] == actual_action:
                        correct_predictions += 1
                    
                    rewards.append(prediction.get('reward', 0.0))
            
            accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0.0
            avg_reward = np.mean(rewards) if rewards else 0.0
            
            return {
                'accuracy': accuracy,
                'avg_reward': avg_reward,
                'correct_predictions': correct_predictions,
                'total_predictions': total_predictions,
                'message': 'Evaluation complete'
            }
            
        except Exception as e:
            print(f"Error evaluating model: {e}")
            return {
                'accuracy': 0.0,
                'avg_reward': 0.0,
                'message': f'Evaluation error: {str(e)}'
            }
    
    def get_model_info(self) -> Dict:
        """Get information about loaded model."""
        if not self.model_loaded:
            return {
                'loaded': False,
                'message': 'No model loaded'
            }
        
        return {
            'loaded': True,
            'model_path': self.model_path,
            'load_time': self.load_time,
            'state_dim': self.model.state_dim if self.model else None,
            'action_dim': self.model.action_dim if self.model else None
        }


# Global model manager instance
_model_manager = None

def get_model_manager() -> ModelManager:
    """Get or create global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager

