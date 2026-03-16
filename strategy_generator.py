#!/usr/bin/env python3
"""
Strategy Generator - Auto-Learning System
Generates parameter combinations for testing
"""

import random
import json
from typing import List, Dict, Any
from pathlib import Path

class StrategyGenerator:
    def __init__(self, learning_db_path: str = "/root/ethbot/logs/learning.db"):
        self.db_path = Path(learning_db_path)
        self.parameter_ranges = {
            'ml_threshold': (0.45, 0.70),      # Tightened: higher confidence = better WR
            'risk_per_trade': (0.005, 0.020),
            'tp_min': (0.010, 0.030),
            'tp_max': (0.015, 0.050),
            'stop_floor': (0.012, 0.025),  # Min 1.2% SL (backtest enforces 1% floor)
            'max_trades_per_day': (5, 25),
            # Expanded params for broader search
            'rsi_oversold': (25, 45),
            'rsi_overbought': (60, 85),
            'entry_score_min': (0.10, 0.30),
            'breakout_pct': (0.00001, 0.001)
        }
        
        # Conservative ranges biased toward high win rates
        self.high_wr_ranges = {
            'ml_threshold': (0.55, 0.70),      # High confidence only
            'risk_per_trade': (0.005, 0.012),   # Lower risk = fewer blowups
            'tp_min': (0.010, 0.020),           # Tighter TP = more frequent wins
            'tp_max': (0.015, 0.035),           # Not too greedy
            'stop_floor': (0.015, 0.025),       # Wider SL = fewer stop-outs
            'max_trades_per_day': (5, 15),      # Fewer, more selective trades
            'rsi_oversold': (28, 40),           # Conservative RSI entries
            'rsi_overbought': (65, 80),
            'entry_score_min': (0.18, 0.30),    # Higher entry bar
            'breakout_pct': (0.0001, 0.0008)
        }
    
    def generate_random_strategy(self) -> Dict[str, Any]:
        """Generate completely random strategy"""
        return {
            'ml_threshold': random.uniform(*self.parameter_ranges['ml_threshold']),
            'risk_per_trade': random.uniform(*self.parameter_ranges['risk_per_trade']),
            'tp_min': random.uniform(*self.parameter_ranges['tp_min']),
            'tp_max': random.uniform(*self.parameter_ranges['tp_max']),
            'stop_floor': random.uniform(*self.parameter_ranges['stop_floor']),
            'max_trades_per_day': random.randint(*self.parameter_ranges['max_trades_per_day']),
            'rsi_oversold': random.uniform(*self.parameter_ranges['rsi_oversold']),
            'rsi_overbought': random.uniform(*self.parameter_ranges['rsi_overbought']),
            'entry_score_min': random.uniform(*self.parameter_ranges['entry_score_min']),
            'breakout_pct': random.uniform(*self.parameter_ranges['breakout_pct'])
        }
    
    def generate_high_winrate_strategy(self) -> Dict[str, Any]:
        """Generate a conservative strategy optimized for high win rate.
        Uses tighter parameters: high ML confidence, lower risk, realistic TPs."""
        return {
            'ml_threshold': random.uniform(*self.high_wr_ranges['ml_threshold']),
            'risk_per_trade': random.uniform(*self.high_wr_ranges['risk_per_trade']),
            'tp_min': random.uniform(*self.high_wr_ranges['tp_min']),
            'tp_max': random.uniform(*self.high_wr_ranges['tp_max']),
            'stop_floor': random.uniform(*self.high_wr_ranges['stop_floor']),
            'max_trades_per_day': random.randint(*self.high_wr_ranges['max_trades_per_day']),
            'rsi_oversold': random.uniform(*self.high_wr_ranges['rsi_oversold']),
            'rsi_overbought': random.uniform(*self.high_wr_ranges['rsi_overbought']),
            'entry_score_min': random.uniform(*self.high_wr_ranges['entry_score_min']),
            'breakout_pct': random.uniform(*self.high_wr_ranges['breakout_pct'])
        }
    
    def mutate_strategy(self, strategy: Dict[str, Any], mutation_rate: float = 0.20) -> Dict[str, Any]:
        """Mutate strategy by small random changes"""
        mutated = strategy.copy()
        
        for param, (min_val, max_val) in self.parameter_ranges.items():
            if random.random() < mutation_rate:
                if param == 'max_trades_per_day':
                    # Integer parameter
                    change = random.randint(-3, 3)
                    mutated[param] = max(min_val, min(max_val, strategy[param] + change))
                else:
                    # Float parameter
                    change = random.uniform(-0.05, 0.05)
                    mutated[param] = max(min_val, min(max_val, strategy[param] * (1 + change)))
        
        return mutated
    
    def crossover(self, parent1: Dict[str, Any], parent2: Dict[str, Any]) -> Dict[str, Any]:
        """Combine two strategies"""
        child = {}
        
        for param in self.parameter_ranges.keys():
            # Randomly pick from parent1 or parent2
            if random.random() < 0.5:
                child[param] = parent1[param]
            else:
                child[param] = parent2[param]
        
        return child
    
    def generate_strategies(self, count: int = 10, best_strategies: List[Dict] = None) -> List[Dict[str, Any]]:
        """
        Generate mix of strategies (v2 — win-rate optimized):
        - 40% Random exploration
        - 20% High win-rate focused (conservative params)
        - 25% Mutation of best
        - 15% Crossover
        """
        strategies = []
        
        # Random exploration (40%)
        random_count = int(count * 0.4)
        for _ in range(random_count):
            strategies.append(self.generate_random_strategy())
        
        # High win-rate focused (20%)
        high_wr_count = int(count * 0.2)
        for _ in range(high_wr_count):
            strategies.append(self.generate_high_winrate_strategy())
        
        # If we have best strategies, use them for mutation and crossover
        if best_strategies and len(best_strategies) >= 2:
            # Mutation (25%)
            mutation_count = int(count * 0.25)
            for _ in range(mutation_count):
                parent = random.choice(best_strategies)
                mutated = self.mutate_strategy(parent['params'], mutation_rate=0.15)
                strategies.append(mutated)
            
            # Crossover (15%)
            crossover_count = count - len(strategies)
            for _ in range(crossover_count):
                parent1 = random.choice(best_strategies)
                parent2 = random.choice(best_strategies)
                child = self.crossover(parent1['params'], parent2['params'])
                strategies.append(child)
        else:
            # Fill remaining with mix of random + high WR
            while len(strategies) < count:
                if random.random() < 0.4:
                    strategies.append(self.generate_high_winrate_strategy())
                else:
                    strategies.append(self.generate_random_strategy())
        
        return strategies
    
    def generate_focused_strategies(self, best_strategy: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """Generate strategies focused around the best one"""
        strategies = []
        
        for _ in range(count):
            # Small mutations around best
            mutated = self.mutate_strategy(best_strategy, mutation_rate=0.05)
            strategies.append(mutated)
        
        return strategies

if __name__ == "__main__":
    # Test
    gen = StrategyGenerator()
    
    # Generate random strategies
    strategies = gen.generate_strategies(10)
    
    print("Generated 10 strategies:")
    for i, s in enumerate(strategies, 1):
        print(f"\nStrategy {i}:")
        print(f"  ML Threshold: {s['ml_threshold']:.3f}")
        print(f"  Risk: {s['risk_per_trade']:.4f}")
        print(f"  TP: {s['tp_min']:.3f} - {s['tp_max']:.3f}")
        print(f"  SL: {s['stop_floor']:.3f}")
        print(f"  Max Trades: {s['max_trades_per_day']}")
