import json
import os
import threading

# Build parameter file path relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAM_FILE = os.path.join(BASE_DIR, "ai_parameters.json")

_param_lock = threading.Lock()

DEFAULT_PARAMS = {
    "time_window": 60,                # 60 seconds rolling window for velocity/momentum
    "velocity_threshold": 0.02,       # Minimum price % change in the window to confirm trend
    "momentum_threshold": 1.5,        # Minimum confidence change in the window
    "whipsaw_sd_threshold": 0.015,    # Standard deviation threshold above which it's considered a whipsaw
    "spam_cooldown": 60,              # Cooldown in seconds before re-entering same direction
    "deceleration_tolerance": 3,      # Number of ticks of decelerating confidence before EXIT WARNING
    "trailing_buffer_multiplier": 1.0 # Multiplier for ATR padding on Trailing Stop
}

def load_ai_params():
    """Load adaptive parameters from disk or initialize defaults."""
    with _param_lock:
        if not os.path.exists(PARAM_FILE):
            _save_params_internal(DEFAULT_PARAMS)
            return DEFAULT_PARAMS.copy()
            
        try:
            with open(PARAM_FILE, "r", encoding="utf-8") as f:
                params = json.load(f)
                
            # Ensure all keys exist (in case of updates)
            updated = False
            for k, v in DEFAULT_PARAMS.items():
                if k not in params:
                    params[k] = v
                    updated = True
            
            if updated:
                _save_params_internal(params)
                
            return params
        except Exception as e:
            print(f"[AI Tuner] Error loading params, using defaults. {e}")
            return DEFAULT_PARAMS.copy()

def save_ai_params(params):
    """Save the updated parameters to disk."""
    with _param_lock:
        _save_params_internal(params)

def _save_params_internal(params):
    try:
        with open(PARAM_FILE, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)
    except Exception as e:
        print(f"[AI Tuner] Error saving params: {e}")

def tune_parameters_for_winrate(current_winrate, target_winrate=90.0):
    """
    Self-learning function to adjust thresholds if winrate drops below target.
    This will be called periodically by the background thread.
    """
    params = load_ai_params()
    
    if current_winrate >= target_winrate:
        # If we are doing great, we might slightly relax parameters to capture more trades
        if params["time_window"] > 30:
            params["time_window"] -= 5
        if params["velocity_threshold"] > 0.01:
            params["velocity_threshold"] = round(params["velocity_threshold"] - 0.002, 4)
        save_ai_params(params)
        return
        
    
    # If winrate is dropping, the market is likely getting choppier or we are entering false breakouts.
    # We tighten the parameters to filter out more noise.
    
    # 1. Widen the time window to require longer sustained momentum (max 300s)
    if params["time_window"] < 300:
        params["time_window"] += 15
        
    # 2. Increase velocity threshold to require stronger moves (max 0.10%)
    if params["velocity_threshold"] < 0.10:
        params["velocity_threshold"] = round(params["velocity_threshold"] + 0.005, 4)
        
    # 3. Increase whipsaw sensitivity (lower the threshold so we detect it earlier)
    if params["whipsaw_sd_threshold"] > 0.005:
        params["whipsaw_sd_threshold"] = round(params["whipsaw_sd_threshold"] - 0.001, 4)
        
    save_ai_params(params)
    print(f"[AI Tuner] Adaptive adjustment applied: tightened parameters to recover winrate. New params: {params}")
