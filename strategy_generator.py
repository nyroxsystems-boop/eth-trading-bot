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
    def __init__(self, learning_db_path: str = None):
        if learning_db_path is None:
            import pathlib
            learning_db_path = str(pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent))) / "logs" / "learning.db")
        self.db_path = Path(learning_db_path)
        self.parameter_ranges = {
            'ml_threshold': (0.50, 0.70),      # Higher confidence only (was 0.45)
            'risk_per_trade': (0.005, 0.015),   # Tighter risk (was 0.020)
            'tp_min': (0.008, 0.020),           # Tighter TPs for more frequent wins
            'tp_max': (0.012, 0.030),           # Not too greedy (was 0.050)
            'stop_floor': (0.010, 0.030),       # Aligned with live bot clamp 0.8-3.5%
            'max_trades_per_day': (3, 15),      # Fewer trades (was 5-25)
            'rsi_oversold': (28, 42),           # Tighter RSI (was 25-45)
            'rsi_overbought': (62, 78),         # Tighter RSI (was 60-85)
            'entry_score_min': (0.20, 0.35),    # Floor raised to 0.20 (was 0.18)
            'breakout_pct': (0.00005, 0.0008),  # Tighter breakout (was 0.00001)
            'adx_min': (8, 25),                 # ADX trend filter — dynamic (was fixed 14)
            'sentiment_gate': (-0.40, 0.10),    # Sentiment threshold — dynamic (was fixed -0.20)
        }
        
        # Conservative ranges biased toward high win rates
        self.high_wr_ranges = {
            'ml_threshold': (0.58, 0.70),      # Only high confidence trades
            'risk_per_trade': (0.005, 0.010),   # Very low risk
            'tp_min': (0.008, 0.015),           # Quick, achievable TPs
            'tp_max': (0.012, 0.025),           # Realistic maxima
            'stop_floor': (0.012, 0.028),       # Match live bot range
            'max_trades_per_day': (3, 10),      # Quality over quantity
            'rsi_oversold': (30, 40),           # Conservative entries
            'rsi_overbought': (65, 75),         # Exit before overbought
            'entry_score_min': (0.22, 0.35),    # HIGH entry quality bar
            'breakout_pct': (0.0001, 0.0005),
            'adx_min': (12, 22),                # Moderate trend filter
            'sentiment_gate': (-0.25, 0.05),    # Slightly stricter sentiment
        }
        
        # Ultra-conservative: maximum selectivity for peak WR
        self.ultra_conservative_ranges = {
            'ml_threshold': (0.62, 0.70),      # Only very high confidence
            'risk_per_trade': (0.005, 0.008),   # Minimal risk
            'tp_min': (0.006, 0.012),           # Very tight TPs — almost always hit
            'tp_max': (0.010, 0.018),           # Small but consistent gains
            'stop_floor': (0.015, 0.035),       # Wide stops — rarely stopped out (within clamp)
            'max_trades_per_day': (2, 6),       # Very few, very selective trades
            'rsi_oversold': (32, 38),           # Narrow oversold window
            'rsi_overbought': (68, 75),         # Narrow overbought window
            'entry_score_min': (0.25, 0.40),    # Very high entry bar
            'breakout_pct': (0.0002, 0.0006),
            'adx_min': (14, 20),                # Conservative — needs clear trend
            'sentiment_gate': (-0.15, 0.05),    # Strict sentiment — no negative news
        }
    
    def generate_random_strategy(self) -> Dict[str, Any]:
        """Generate random strategy within tightened ranges"""
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
            'breakout_pct': random.uniform(*self.parameter_ranges['breakout_pct']),
            'adx_min': random.uniform(*self.parameter_ranges['adx_min']),
            'sentiment_gate': random.uniform(*self.parameter_ranges['sentiment_gate']),
        }
    
    def generate_high_winrate_strategy(self) -> Dict[str, Any]:
        """Generate a conservative strategy optimized for high win rate."""
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
            'breakout_pct': random.uniform(*self.high_wr_ranges['breakout_pct']),
            'adx_min': random.uniform(*self.high_wr_ranges['adx_min']),
            'sentiment_gate': random.uniform(*self.high_wr_ranges['sentiment_gate']),
        }
    
    def generate_ultra_conservative_strategy(self) -> Dict[str, Any]:
        """Generate ultra-conservative strategy for maximum win rate.
        Tight TPs, wide SLs, very high entry quality — few trades but almost all winners."""
        return {
            'ml_threshold': random.uniform(*self.ultra_conservative_ranges['ml_threshold']),
            'risk_per_trade': random.uniform(*self.ultra_conservative_ranges['risk_per_trade']),
            'tp_min': random.uniform(*self.ultra_conservative_ranges['tp_min']),
            'tp_max': random.uniform(*self.ultra_conservative_ranges['tp_max']),
            'stop_floor': random.uniform(*self.ultra_conservative_ranges['stop_floor']),
            'max_trades_per_day': random.randint(*self.ultra_conservative_ranges['max_trades_per_day']),
            'rsi_oversold': random.uniform(*self.ultra_conservative_ranges['rsi_oversold']),
            'rsi_overbought': random.uniform(*self.ultra_conservative_ranges['rsi_overbought']),
            'entry_score_min': random.uniform(*self.ultra_conservative_ranges['entry_score_min']),
            'breakout_pct': random.uniform(*self.ultra_conservative_ranges['breakout_pct']),
            'adx_min': random.uniform(*self.ultra_conservative_ranges['adx_min']),
            'sentiment_gate': random.uniform(*self.ultra_conservative_ranges['sentiment_gate']),
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
        Generate mix of strategies (v4 — win-rate ULTRA-DOMINANT):
        - 15% Random exploration (reduced from 40%)
        - 30% High win-rate focused (increased from 20%)
        - 20% Ultra-conservative (NEW — maximum WR pursuit)
        - 20% Mutation of best (slightly reduced)
        - 15% Crossover
        """
        strategies = []
        
        # Random exploration (15% — reduced)
        random_count = max(1, int(count * 0.15))
        for _ in range(random_count):
            strategies.append(self.generate_random_strategy())
        
        # High win-rate focused (30%)
        high_wr_count = max(1, int(count * 0.30))
        for _ in range(high_wr_count):
            strategies.append(self.generate_high_winrate_strategy())
        
        # Ultra-conservative (20% — NEW)
        ultra_count = max(1, int(count * 0.20))
        for _ in range(ultra_count):
            strategies.append(self.generate_ultra_conservative_strategy())
        
        # If we have best strategies, use them for mutation and crossover
        if best_strategies and len(best_strategies) >= 2:
            # Mutation (20%)
            mutation_count = max(1, int(count * 0.20))
            for _ in range(mutation_count):
                parent = random.choice(best_strategies)
                mutated = self.mutate_strategy(parent['params'], mutation_rate=0.15)
                strategies.append(mutated)
            
            # Crossover (fill remaining)
            crossover_count = count - len(strategies)
            for _ in range(max(0, crossover_count)):
                parent1 = random.choice(best_strategies)
                parent2 = random.choice(best_strategies)
                child = self.crossover(parent1['params'], parent2['params'])
                strategies.append(child)
        else:
            # Fill remaining with high WR + ultra-conservative
            while len(strategies) < count:
                if random.random() < 0.5:
                    strategies.append(self.generate_high_winrate_strategy())
                else:
                    strategies.append(self.generate_ultra_conservative_strategy())
        
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
