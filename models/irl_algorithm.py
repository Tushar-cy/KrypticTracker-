"""
Maximum Entropy Inverse Reinforcement Learning (MaxEnt IRL) implementation.
Learns reward function that explains expert behavior.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import List, Tuple, Dict
from tqdm import tqdm

from models.reward_model import RewardModel


class ExpertTrajectoryDataset(Dataset):
    """
    Dataset for expert trajectories (your observed behavior).
    Each trajectory is a sequence of (state, action) pairs.
    """
    
    def __init__(self, trajectories: List[List[Tuple[np.ndarray, np.ndarray]]], normalize: bool = True):
        """
        Initialize dataset.
        
        Args:
            trajectories: List of trajectories, each is list of (state, action) tuples
            normalize: Whether to normalize states and actions (recommended for stability)
        """
        self.states = []
        self.actions = []
        
        # Flatten trajectories
        for trajectory in trajectories:
            for state, action in trajectory:
                self.states.append(state)
                self.actions.append(action)
        
        self.states = np.array(self.states, dtype=np.float32)
        self.actions = np.array(self.actions, dtype=np.float32)
        
        # Normalize for better training stability
        if normalize and len(self.states) > 0:
            # Normalize states (zero mean, unit variance)
            self.state_mean = np.mean(self.states, axis=0, keepdims=True)
            self.state_std = np.std(self.states, axis=0, keepdims=True) + 1e-8
            self.states = (self.states - self.state_mean) / self.state_std
            
            # Normalize actions
            self.action_mean = np.mean(self.actions, axis=0, keepdims=True)
            self.action_std = np.std(self.actions, axis=0, keepdims=True) + 1e-8
            self.actions = (self.actions - self.action_mean) / self.action_std
        else:
            # Store identity normalization (no change)
            self.state_mean = np.zeros((1, self.states.shape[1])) if len(self.states) > 0 else np.zeros((1,))
            self.state_std = np.ones((1, self.states.shape[1])) if len(self.states) > 0 else np.ones((1,))
            self.action_mean = np.zeros((1, self.actions.shape[1])) if len(self.actions) > 0 else np.zeros((1,))
            self.action_std = np.ones((1, self.actions.shape[1])) if len(self.actions) > 0 else np.ones((1,))
    
    def __len__(self):
        return len(self.states)
    
    def __getitem__(self, idx):
        state = torch.FloatTensor(self.states[idx])
        action = torch.FloatTensor(self.actions[idx])
        return state, action


class MaxEntIRL:
    """
    Maximum Entropy IRL algorithm.
    
    Goal: Learn reward function R(s, a) such that your behavior
    is optimal under that reward function.
    
    Algorithm:
    1. Initialize reward model R(s, a)
    2. Compute optimal policy π*(a|s) given R
    3. Compare expert behavior vs policy behavior
    4. Update R to maximize likelihood of expert behavior
    5. Repeat until convergence
    """
    
    def __init__(
        self,
        state_dim: int = 192,
        action_dim: int = 48,
        learning_rate: float = 0.001,
        device: str = None
    ):
        """
        Initialize MaxEnt IRL.
        
        Args:
            state_dim: Dimension of state vector
            action_dim: Dimension of action vector
            learning_rate: Learning rate for optimization
            device: Device to use ('cuda' or 'cpu')
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate
        
        # Set device
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        print(f"Using device: {self.device}")
        
        # Initialize reward model
        self.reward_model = RewardModel(state_dim, action_dim).to(self.device)
        
        # Optimizer - Use AdamW (better weight decay) with optimized settings
        self.reward_optimizer = optim.AdamW(
            self.reward_model.parameters(),
            lr=learning_rate,
            weight_decay=1e-4,  # Better regularization
            betas=(0.9, 0.999),  # Standard Adam betas
            eps=1e-8,
            amsgrad=False
        )
        
        # Learning rate scheduler (will be initialized in train method)
        self.reward_scheduler = None
        
        # Loss function
        self.criterion = nn.MSELoss()
    
    def train(
        self,
        expert_trajectories: List[List[Tuple[np.ndarray, np.ndarray]]],
        num_epochs: int = 50,
        batch_size: int = 64,
        verbose: bool = True,
        callback: callable = None,
        early_stopping_patience: int = 10,
        min_loss_delta: float = 1e-6,
        validation_split: float = 0.1
    ) -> Dict:
        """
        Train reward model using Maximum Entropy IRL.
        
        Args:
            expert_trajectories: List of expert trajectories (your behavior)
            num_epochs: Number of training epochs (max)
            batch_size: Batch size for training
            verbose: Whether to print progress
            callback: Optional callback function for progress updates
            early_stopping_patience: Stop if loss doesn't improve for N epochs
            min_loss_delta: Minimum change in loss to count as improvement
            validation_split: Fraction of data to use for validation (0.0 to 0.3)
            
        Returns:
            Training history dictionary
        """
        # Create dataset with normalization (better training stability)
        dataset = ExpertTrajectoryDataset(expert_trajectories, normalize=True)
        
        # Split into train/validation if requested
        if validation_split > 0:
            from torch.utils.data import random_split
            val_size = int(len(dataset) * validation_split)
            train_size = len(dataset) - val_size
            train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
            print(f"📊 Split: {train_size:,} train, {val_size:,} validation ({validation_split*100:.1f}%)")
        else:
            train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
            val_loader = None
        
        history = {
            'loss': [],
            'reward_mean': [],
            'reward_std': [],
            'val_loss': [],
            'val_reward_mean': [],
            'val_reward_std': []
        }
        
        # Early stopping state
        best_loss = float('inf')
        patience_counter = 0
        best_model_state = None
        
        # Initialize learning rate scheduler
        # ReduceLROnPlateau - adaptive LR reduction when loss plateaus
        self.reward_scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.reward_optimizer, mode='min', factor=0.5, patience=5, min_lr=1e-7
        )
        
        print(f"\n🚀 Starting MaxEnt IRL Training (Optimized)")
        print(f"   Expert trajectories: {len(expert_trajectories)}")
        print(f"   Total state-action pairs: {len(dataset)}")
        print(f"   Max epochs: {num_epochs}")
        print(f"   Batch size: {batch_size}")
        print(f"   Early stopping: {early_stopping_patience} epochs patience")
        print(f"   LR scheduling: ReduceLROnPlateau (adaptive)")
        print(f"   Optimizer: AdamW (better weight decay)")
        print(f"   Reward model params: {self.reward_model.count_parameters():,}\n")
        
        for epoch in range(num_epochs):
            epoch_losses = []
            epoch_rewards = []
            
            self.reward_model.train()
            
            pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{num_epochs}") if verbose else train_loader
            
            for states, actions in pbar:
                states = states.to(self.device)
                actions = actions.to(self.device)
                
                # Forward pass: compute rewards
                predicted_rewards = self.reward_model(states, actions)
                
                # In MaxEnt IRL, we want to maximize likelihood of expert behavior
                # This means expert (state, action) pairs should have high rewards
                # compared to other possible actions
                
                # Compute rewards for expert actions
                expert_rewards = predicted_rewards
                
                # Sample random actions for comparison (negative examples)
                random_actions = torch.randn_like(actions)
                random_rewards = self.reward_model(states, random_actions)
                
                # Improved loss function: Margin ranking loss with temperature
                # Expert actions should have significantly higher rewards
                margin = 1.0
                temperature = 0.1  # Temperature scaling for sharper distinction
                
                # Margin ranking loss (Hinge loss)
                margin_loss = torch.mean(torch.clamp(
                    (random_rewards - expert_rewards) / temperature + margin,
                    min=0.0
                ))
                
                # L2 regularization on rewards (prevents extreme values)
                reward_l2 = torch.mean(predicted_rewards ** 2)
                
                # Entropy regularization (encourages diverse rewards, prevents collapse)
                reward_std = torch.std(predicted_rewards)
                entropy_reg = -reward_std * 0.01  # Small penalty for low variance
                
                # Combined loss
                loss = margin_loss + 0.01 * reward_l2 + entropy_reg
                
                # Gradient accumulation: accumulate over 4 steps for effective 4x batch size
                accumulation_steps = 4
                loss = loss / accumulation_steps
                
                # Backward pass
                loss.backward()
                
                # Update weights every accumulation_steps batches
                if (len(epoch_losses) + 1) % accumulation_steps == 0:
                    # Gradient clipping (prevents exploding gradients)
                    torch.nn.utils.clip_grad_norm_(self.reward_model.parameters(), max_norm=1.0)
                    self.reward_optimizer.step()
                    self.reward_optimizer.zero_grad()
                
                epoch_losses.append(loss.item())
                epoch_rewards.extend(predicted_rewards.cpu().detach().numpy().flatten())
            
            # Record epoch statistics
            avg_loss = np.mean(epoch_losses)
            avg_reward = np.mean(epoch_rewards)
            std_reward = np.std(epoch_rewards)
            
            history['loss'].append(avg_loss)
            history['reward_mean'].append(avg_reward)
            history['reward_std'].append(std_reward)
            
            # Validation
            val_loss = None
            val_reward_mean = None
            val_reward_std = None
            if val_loader is not None:
                self.reward_model.eval()
                val_losses = []
                val_rewards = []
                
                with torch.no_grad():
                    for states, actions in val_loader:
                        states = states.to(self.device)
                        actions = actions.to(self.device)
                        
                        predicted_rewards = self.reward_model(states, actions)
                        random_actions = torch.randn_like(actions)
                        random_rewards = self.reward_model(states, random_actions)
                        
                        margin = 1.0
                        loss = torch.mean(torch.clamp(
                            random_rewards - predicted_rewards + margin,
                            min=0.0
                        ))
                        reward_regularization = torch.mean(torch.abs(predicted_rewards))
                        loss += 0.01 * reward_regularization
                        
                        val_losses.append(loss.item())
                        val_rewards.extend(predicted_rewards.cpu().numpy().flatten())
                
                val_loss = np.mean(val_losses)
                val_reward_mean = np.mean(val_rewards)
                val_reward_std = np.std(val_rewards)
                
                history['val_loss'].append(val_loss)
                history['val_reward_mean'].append(val_reward_mean)
                history['val_reward_std'].append(val_reward_std)
            
            # Update learning rate scheduler
            current_loss = val_loss if val_loss is not None else avg_loss
            # ReduceLROnPlateau (adaptive based on loss)
            self.reward_scheduler.step(current_loss)
            
            # Get current learning rate for logging
            current_lr = self.reward_optimizer.param_groups[0]['lr']
            
            # Early stopping check
            loss_improved = (best_loss - current_loss) >= min_loss_delta
            
            if loss_improved:
                best_loss = current_loss
                patience_counter = 0
                # Save best model state (deep copy)
                import copy
                best_model_state = {
                    'reward_model': copy.deepcopy(self.reward_model.state_dict()),
                    'epoch': epoch + 1
                }
            else:
                patience_counter += 1
            
            # Call callback if provided
            if callback:
                callback(epoch + 1, num_epochs, avg_loss, avg_reward, std_reward)
            
            # Print progress
            if verbose:
                train_msg = f"Loss: {avg_loss:.6f} | Reward: {avg_reward:.4f} ± {std_reward:.4f}"
                if val_loss is not None:
                    train_msg += f" | Val Loss: {val_loss:.6f} | Val Reward: {val_reward_mean:.4f} ± {val_reward_std:.4f}"
                train_msg += f" | LR: {current_lr:.2e}"  # Show current learning rate
                if patience_counter > 0:
                    train_msg += f" | Patience: {patience_counter}/{early_stopping_patience}"
                print(f"Epoch {epoch+1}/{num_epochs} | {train_msg}")
            
            # Early stopping
            if patience_counter >= early_stopping_patience:
                print(f"\n⏹️  Early stopping triggered! No improvement for {early_stopping_patience} epochs.")
                print(f"   Best loss: {best_loss:.6f} at epoch {best_model_state['epoch']}")
                # Restore best model
                if best_model_state:
                    self.reward_model.load_state_dict(best_model_state['reward_model'])
                break
        
        if patience_counter < early_stopping_patience:
            print("\n✅ Training complete!")
        return history
    
    def predict_reward(self, state: np.ndarray, action: np.ndarray) -> float:
        """
        Predict reward for a state-action pair.
        
        Args:
            state: State vector
            action: Action vector
            
        Returns:
            Predicted reward value
        """
        self.reward_model.eval()
        
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_tensor = torch.FloatTensor(action).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            reward = self.reward_model(state_tensor, action_tensor)
            return reward.item()
    
    def save_model(self, path: str, dataset: ExpertTrajectoryDataset = None):
        """Save trained model with normalization parameters.
        
        Args:
            path: Path to save model checkpoint
            dataset: Optional dataset to extract normalization parameters from
        """
        checkpoint = {
            'reward_model_state_dict': self.reward_model.state_dict(),
            'state_dim': self.state_dim,
            'action_dim': self.action_dim,
        }
        
        # Save normalization parameters if dataset provided
        if dataset is not None:
            checkpoint['normalization'] = {
                'state_mean': dataset.state_mean,
                'state_std': dataset.state_std,
                'action_mean': dataset.action_mean,
                'action_std': dataset.action_std
            }
        
        torch.save(checkpoint, path)
        print(f"✅ Model saved to {path}")
    
    
    def load_model(self, path: str):
        """Load trained model.
        
        Args:
            path: Path to model checkpoint
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.reward_model.load_state_dict(checkpoint['reward_model_state_dict'])
        
        # Load normalization parameters if available
        if 'normalization' in checkpoint:
            self.normalization_params = checkpoint['normalization']
            print(f"✅ Model loaded from {path} (with normalization parameters)")
        else:
            self.normalization_params = None
            print(f"✅ Model loaded from {path} (no normalization parameters found)")
