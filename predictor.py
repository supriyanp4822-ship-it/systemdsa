"""
predictor.py
------------
Loads model.joblib + feature_encoder.joblib (trained on the real hospital
wait-time CSV) and exposes two prediction APIs:

  predict_wait_time(queue_length, specialty, experience, hour_of_day)
      Backward-compatible call used by all existing Flask routes.

  predict_wait_time_full(feature_dict)
      Full-featured call when callers can supply the complete feature set.

Falls back to a rule-based estimate if model files are absent.
"""

import os
import numpy as np
import pandas as pd
import joblib

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH           = os.path.join(_HERE, "model.joblib")
FEATURE_ENCODER_PATH = os.path.join(_HERE, "feature_encoder.joblib")
SPECIALTY_ENCODER_PATH = os.path.join(_HERE, "specialty_encoder.joblib")  # legacy compat

# ---------------------------------------------------------------------------
# Feature schema (must match train_model.py)
# ---------------------------------------------------------------------------
CATEGORICAL_FEATURES = [
    "AgeGroup",
    "Department",
    "AppointmentType",
    "InsuranceType",
    "ArrivalMethod",
    "TriageCategory",
    "ReasonForVisit",
]

NUMERIC_FEATURES = [
    "FacilityOccupancyRate",
    "ProvidersOnShift",
    "NursesOnShift",
    "StaffToPatientRatio",
    "ArrivalHour",
    "ArrivalDayOfWeek",
    "IsWeekend",
    "IsOnlineBooking",
]

# Default values for features not always supplied by callers
_DEFAULTS = {
    "AgeGroup": "Adult (36-60)",
    "Department": "Internal Medicine",
    "AppointmentType": "New Patient",
    "InsuranceType": "Unknown",
    "ArrivalMethod": "Scheduled",
    "TriageCategory": "Non-urgent",
    "ReasonForVisit": "Routine checkup",
    "FacilityOccupancyRate": 0.63,
    "ProvidersOnShift": 5.0,
    "NursesOnShift": 9.0,
    "StaffToPatientRatio": 0.30,
    "ArrivalHour": 10.0,
    "ArrivalDayOfWeek": 1.0,
    "IsWeekend": 0,
    "IsOnlineBooking": 1,
}

# Specialty string → Department mapping (for backward-compat calls)
_SPECIALTY_TO_DEPT = {
    "Cardiologist":  "Cardiology",
    "Neurologist":   "Neurology",
    "Orthopedic":    "Orthopedics",
    "Pediatrician":  "Pediatrics",
    "Oncologist":    "Oncology",
    "Cardiology":    "Cardiology",
    "Neurology":     "Neurology",
    "Orthopedics":   "Orthopedics",
    "Pediatrics":    "Pediatrics",
    "Emergency":     "Emergency",
    "Radiology":     "Radiology",
    "Obstetrics":    "Obstetrics",
    "General Surgery": "General Surgery",
    "Internal Medicine": "Internal Medicine",
}

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------
_model   = None
_enc     = None  # OrdinalEncoder (feature_encoder.joblib)
_loaded  = False


def _load_assets():
    """Load model and encoder once; silently skip if files are missing."""
    global _model, _enc, _loaded
    if _loaded:
        return
    _loaded = True

    if os.path.exists(MODEL_PATH) and os.path.exists(FEATURE_ENCODER_PATH):
        try:
            _model = joblib.load(MODEL_PATH)
            _enc   = joblib.load(FEATURE_ENCODER_PATH)
            print("ML prediction assets loaded successfully.")
        except Exception as exc:
            print(f"Error loading ML assets: {exc}. Falling back to rule-based estimation.")
            _model = None
            _enc   = None
    else:
        print("ML model files not found. Falling back to rule-based estimation.")


# ---------------------------------------------------------------------------
# Public API – backward-compatible signature
# ---------------------------------------------------------------------------
def predict_wait_time(queue_length: int, specialty: str,
                      experience: int, hour_of_day: int) -> int:
    """
    Predict wait time (minutes) using the existing call signature.

    Parameters
    ----------
    queue_length : number of patients ahead in the queue
    specialty    : doctor specialty string (e.g. 'Cardiologist')
    experience   : doctor's years of experience
    hour_of_day  : current hour (0-23)
    """
    _load_assets()

    if _model is not None and _enc is not None:
        try:
            dept = _SPECIALTY_TO_DEPT.get(specialty, "Internal Medicine")

            # Build feature dict from available info + defaults
            fdict = dict(_DEFAULTS)
            fdict["Department"]      = dept
            fdict["ArrivalHour"]     = float(hour_of_day)
            fdict["ProvidersOnShift"] = max(2.0, min(8.0, float(experience) / 3.0 + 2.0))
            # Use queue_length to nudge occupancy rate (proxy)
            fdict["FacilityOccupancyRate"] = min(0.95, 0.40 + queue_length * 0.04)

            return _predict_from_dict(fdict)
        except Exception as exc:
            print(f"ML prediction failed: {exc}. Falling back to rule-based.")

    return _rule_based(queue_length, experience, hour_of_day)


# ---------------------------------------------------------------------------
# Public API – full feature set
# ---------------------------------------------------------------------------
def predict_wait_time_full(feature_dict: dict) -> int:
    """
    Predict wait time using a full feature dictionary.

    Keys should match the schema defined in CATEGORICAL_FEATURES +
    NUMERIC_FEATURES.  Missing keys are filled from _DEFAULTS.

    Returns predicted minutes (integer, ≥ 0).
    """
    _load_assets()

    if _model is not None and _enc is not None:
        try:
            fdict = dict(_DEFAULTS)
            fdict.update(feature_dict)
            return _predict_from_dict(fdict)
        except Exception as exc:
            print(f"Full ML prediction failed: {exc}. Falling back to rule-based.")

    # Rule-based fallback using whatever we can extract
    queue_length = int(feature_dict.get("queue_length", 3))
    experience   = int(feature_dict.get("experience", 10))
    hour_of_day  = int(feature_dict.get("ArrivalHour", _DEFAULTS["ArrivalHour"]))
    return _rule_based(queue_length, experience, hour_of_day)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _predict_from_dict(fdict: dict) -> int:
    """Encode features and run model.predict, returning a rounded integer."""
    cat_df   = pd.DataFrame([[str(fdict[c]) for c in CATEGORICAL_FEATURES]],
                            columns=CATEGORICAL_FEATURES)
    num_vals = [[float(fdict[c]) for c in NUMERIC_FEATURES]]

    cat_enc  = _enc.transform(cat_df)
    features = np.hstack([cat_enc, np.array(num_vals)])

    prediction = _model.predict(features)[0]
    return max(0, int(round(prediction)))


def _rule_based(queue_length: int, experience: int, hour_of_day: int) -> int:
    """Simple rule-based estimation used as a fallback."""
    base_time          = queue_length * 15
    experience_discount = max(0.0, experience * 0.2)
    rush_hour_penalty  = 10 if 11 <= hour_of_day <= 13 else (8 if 14 <= hour_of_day <= 16 else 0)
    estimated = base_time - experience_discount + rush_hour_penalty
    return max(0, int(round(estimated)))
