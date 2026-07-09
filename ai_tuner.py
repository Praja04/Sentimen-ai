import json
import os
import threading

# Build parameter file path relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAM_FILE = os.path.join(BASE_DIR, "ai_parameters.json")

_param_lock = threading.Lock()

DEFAULT_PARAMS = {
    "time_window": 60,                # 60 seconds rolling window for velocity/momentum
    "velocity_threshold": 0.008,      # Minimum % velocity in window to confirm trend (realistic: 0.005-0.015)
    "momentum_threshold": 1.5,        # Minimum confidence change in the window
    "whipsaw_sd_threshold": 0.3,      # SD threshold for whipsaw (realistic: different instruments diverge naturally)
    "spam_cooldown": 60,              # Cooldown in seconds before re-entering same direction
    "deceleration_tolerance": 3,      # Number of ticks of decelerating confidence before EXIT WARNING
    "trailing_buffer_multiplier": 1.0, # Multiplier for ATR padding on Trailing Stop
    "csi_macro_threshold": 0.2,       # Baseline Currency Strength Index filter for major pairs
    "csi_oil_threshold": 0.3,         # Baseline Currency Strength Index filter for WTI Oil
    "xauusd_velocity_threshold": 0.010, # Dedicated velocity threshold for Gold
    "xauusd_macro_threshold": 0.15,     # Dedicated Currency Strength Index filter for Gold
    "xauusd_macro_min_divergence": 2    # Min difference between bulls/bears to trigger macro block
}

# Hard limits to prevent AI Tuner from over-tightening and blocking all signals
PARAM_LIMITS = {
    "time_window":           {"min": 30,    "max": 120},   # Max 2 min window, not 5 min
    "velocity_threshold":    {"min": 0.005, "max": 0.012}, # Max 0.012% - realistic market velocity
    "whipsaw_sd_threshold":  {"min": 0.15,  "max": 0.5},   # Min 0.15% SD - instruments naturally diverge
    "csi_macro_threshold":   {"min": 0.15,  "max": 0.3},
    "csi_oil_threshold":     {"min": 0.2,   "max": 0.4},
    "xauusd_velocity_threshold": {"min": 0.006, "max": 0.015},
    "xauusd_macro_threshold":    {"min": 0.10,  "max": 0.25},
    "xauusd_macro_min_divergence": {"min": 1,   "max": 4}
}

def _clamp_params(params):
    """Enforce hard limits on all parameters to prevent over-tightening."""
    for key, limits in PARAM_LIMITS.items():
        if key in params:
            params[key] = max(limits["min"], min(limits["max"], params[key]))
    return params

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
            
            # Always clamp to safe limits
            params = _clamp_params(params)
            
            if updated:
                _save_params_internal(params)
                
            return params
        except Exception as e:
            print(f"[AI Tuner] Error loading params, using defaults. {e}")
            return DEFAULT_PARAMS.copy()

def save_ai_params(params):
    """Save the updated parameters to disk."""
    with _param_lock:
        params = _clamp_params(params)
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
    Hard limits enforced via PARAM_LIMITS to prevent over-tightening.
    """
    params = load_ai_params()
    
    if current_winrate >= target_winrate:
        # Doing well — slightly relax parameters to capture more trades
        if params["time_window"] > 30:
            params["time_window"] -= 5
        if params["velocity_threshold"] > 0.005:
            params["velocity_threshold"] = round(params["velocity_threshold"] - 0.001, 4)
        if params.get("xauusd_velocity_threshold", 0.010) > 0.006:
            params["xauusd_velocity_threshold"] = round(params.get("xauusd_velocity_threshold", 0.010) - 0.001, 4)
        if params.get("csi_macro_threshold", 0.2) < 0.3:
            params["csi_macro_threshold"] = round(params.get("csi_macro_threshold", 0.2) + 0.01, 3)
        if params.get("xauusd_macro_threshold", 0.15) < 0.25:
            params["xauusd_macro_threshold"] = round(params.get("xauusd_macro_threshold", 0.15) + 0.01, 3)
        if params.get("xauusd_macro_min_divergence", 2) < 4:
            params["xauusd_macro_min_divergence"] = params.get("xauusd_macro_min_divergence", 2) + 1
        if params.get("csi_oil_threshold", 0.3) < 0.4:
            params["csi_oil_threshold"] = round(params.get("csi_oil_threshold", 0.3) + 0.01, 3)
        save_ai_params(params)
        return
        
    # Winrate dropping — tighten slightly but respect hard limits
    
    # 1. Widen the time window slightly (max 120s, NOT 300s)
    if params["time_window"] < PARAM_LIMITS["time_window"]["max"]:
        params["time_window"] += 5
        
    # 2. Increase velocity thresholds slightly (respect limits)
    if params["velocity_threshold"] < PARAM_LIMITS["velocity_threshold"]["max"]:
        params["velocity_threshold"] = round(params["velocity_threshold"] + 0.001, 4)
    if params.get("xauusd_velocity_threshold", 0.010) < PARAM_LIMITS["xauusd_velocity_threshold"]["max"]:
        params["xauusd_velocity_threshold"] = round(params.get("xauusd_velocity_threshold", 0.010) + 0.001, 4)
        
    # 3. Tighten whipsaw sensitivity — but keep floor at 0.15% so normal divergence doesn't trigger
    if params["whipsaw_sd_threshold"] > PARAM_LIMITS["whipsaw_sd_threshold"]["min"]:
        params["whipsaw_sd_threshold"] = round(params["whipsaw_sd_threshold"] - 0.01, 3)
        
    # 4. Tighten CSI thresholds slightly
    if params.get("csi_macro_threshold", 0.2) > PARAM_LIMITS["csi_macro_threshold"]["min"]:
        params["csi_macro_threshold"] = round(params.get("csi_macro_threshold", 0.2) - 0.01, 3)
    if params.get("xauusd_macro_threshold", 0.15) > PARAM_LIMITS["xauusd_macro_threshold"]["min"]:
        params["xauusd_macro_threshold"] = round(params.get("xauusd_macro_threshold", 0.15) - 0.01, 3)
    if params.get("xauusd_macro_min_divergence", 2) > 1:
        params["xauusd_macro_min_divergence"] = params.get("xauusd_macro_min_divergence", 2) - 1
    if params.get("csi_oil_threshold", 0.3) > PARAM_LIMITS["csi_oil_threshold"]["min"]:
        params["csi_oil_threshold"] = round(params.get("csi_oil_threshold", 0.3) - 0.01, 3)
        
    save_ai_params(params)
    print(f"[AI Tuner] Adaptive adjustment applied. New params: {params}")
