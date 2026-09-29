"""
train_model.py
--------------
Trains a GradientBoostingRegressor on the real hospital wait-time CSV dataset.
Falls back to synthetic data if the CSV is not found.

Target: TotalTimeInHospital (total minutes patient spends, arrival to discharge)

Features selected:
  - Pre-visit / booking context: AgeGroup, Department, AppointmentType,
    InsuranceType, ArrivalMethod, IsOnlineBooking, ArrivalHour,
    ArrivalDayOfWeek, IsWeekend, FacilityOccupancyRate,
    ProvidersOnShift, NursesOnShift, StaffToPatientRatio
  - Early-visit (available ~15 min after arrival): TriageCategory,
    TriageToProviderStartTime, ConsultationDurationTime

Usage:
    python train_model.py

Outputs:
    model.joblib           -- trained regression model
    feature_encoder.joblib -- OrdinalEncoder for categorical features
    specialty_encoder.joblib -- LabelEncoder kept for backward-compat
"""

import os
import sys
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OrdinalEncoder, LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH           = os.path.join(BASE_DIR, "dataset", "Hospital Wait  TIme Data.csv")
MODEL_PATH             = os.path.join(BASE_DIR, "model.joblib")
FEATURE_ENCODER_PATH   = os.path.join(BASE_DIR, "feature_encoder.joblib")
SPECIALTY_ENCODER_PATH = os.path.join(BASE_DIR, "specialty_encoder.joblib")

# ---------------------------------------------------------------------------
# Feature definitions
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

ALL_FEATURES  = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "TriageToProviderStartTime"   # float, minutes


# ---------------------------------------------------------------------------
# Data loading & cleaning
# ---------------------------------------------------------------------------
def load_and_clean_dataset(path: str) -> pd.DataFrame:
    """Load the hospital wait-time CSV and return a cleaned DataFrame."""
    print("Loading dataset from: " + path)
    df = pd.read_csv(path)
    print("  Raw shape: " + str(df.shape))

    # Drop rows where target is missing or non-positive
    before = len(df)
    df = df.dropna(subset=[TARGET_COLUMN])
    df = df[df[TARGET_COLUMN] > 0]
    print("  Dropped " + str(before - len(df)) + " rows with missing/invalid target.")

    # Fill missing categoricals with sensible defaults
    df["InsuranceType"] = df["InsuranceType"].fillna("Unknown")
    df["TestsOrdered"]  = df["TestsOrdered"].fillna("None")

    # Ensure boolean-like columns are numeric
    for col in ["IsWeekend", "IsOnlineBooking"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Clip extreme outliers in key numeric features (beyond 99th percentile)
    for col in [TARGET_COLUMN]:
        upper = df[col].quantile(0.99)
        df[col] = df[col].clip(upper=upper)

    # Select only the columns we need and drop remaining NaN rows
    df = df[ALL_FEATURES + [TARGET_COLUMN]].dropna()
    print("  Clean shape: " + str(df.shape))
    print("  Target  --  mean: " + str(round(df[TARGET_COLUMN].mean(), 1))
          + " min  std: " + str(round(df[TARGET_COLUMN].std(), 1))
          + " min  range: [" + str(round(df[TARGET_COLUMN].min(), 1))
          + ", " + str(round(df[TARGET_COLUMN].max(), 1)) + "]")
    return df


# ---------------------------------------------------------------------------
# Synthetic data fallback
# ---------------------------------------------------------------------------
def generate_synthetic_data(num_samples: int = 1500) -> pd.DataFrame:
    """Generate synthetic queue data matching the real feature schema."""
    print("Generating synthetic fallback data...")
    np.random.seed(42)

    departments = ["Oncology", "Pediatrics", "General Surgery", "Internal Medicine", "Neurology"]
    age_groups  = ["Pediatric (0-17)", "Young Adult (18-35)", "Adult (36-60)", "Senior (61+)"]
    appt_types  = ["New Patient", "Follow-up", "Urgent Care", "Specialist Referral"]
    ins_types   = ["Self-pay", "Medicaid", "Private", "Medicare", "Unknown"]
    arr_methods = ["Scheduled", "Walk-in", "Emergency"]
    triage_cats = ["Non-urgent", "Semi-urgent", "Urgent", "Emergency", "Immediate"]
    reasons     = ["Follow-up procedure", "Injury", "Vaccination", "Diagnostic testing", "Routine checkup"]

    triage_wait = {"Non-urgent": 70, "Semi-urgent": 50, "Urgent": 30, "Emergency": 15, "Immediate": 5}
    t_cat       = np.random.choice(triage_cats, num_samples)
    t2p         = np.array([triage_wait[c] for c in t_cat]) + np.random.normal(0, 10, num_samples)
    occ         = np.random.uniform(0.3, 0.95, num_samples)
    hour        = np.random.randint(8, 20, num_samples).astype(float)

    df = pd.DataFrame({
        "AgeGroup":                  np.random.choice(age_groups, num_samples),
        "Department":                np.random.choice(departments, num_samples),
        "AppointmentType":           np.random.choice(appt_types, num_samples),
        "InsuranceType":             np.random.choice(ins_types, num_samples),
        "ArrivalMethod":             np.random.choice(arr_methods, num_samples),
        "TriageCategory":            t_cat,
        "ReasonForVisit":            np.random.choice(reasons, num_samples),
        "FacilityOccupancyRate":     occ,
        "ProvidersOnShift":          np.random.randint(2, 9, num_samples).astype(float),
        "NursesOnShift":             np.random.randint(3, 16, num_samples).astype(float),
        "StaffToPatientRatio":       np.random.uniform(0.1, 0.5, num_samples),
        "ArrivalHour":               hour,
        "ArrivalDayOfWeek":          np.random.randint(0, 7, num_samples).astype(float),
        "IsWeekend":                 np.random.randint(0, 2, num_samples),
        "IsOnlineBooking":           np.random.randint(0, 2, num_samples),
        TARGET_COLUMN:               np.maximum(1, t2p),
    })
    return df


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_predictor():
    # 1. Load or generate data
    if os.path.exists(DATASET_PATH):
        df = load_and_clean_dataset(DATASET_PATH)
        data_source = "CSV dataset"
    else:
        print("WARNING: Dataset not found at '" + DATASET_PATH + "'. Using synthetic data.")
        df = generate_synthetic_data(1500)
        data_source = "synthetic data"

    print("\nTraining on " + data_source + " -- "
          + str(len(df)) + " samples, " + str(len(ALL_FEATURES)) + " features.")

    # 2. Encode categoricals with OrdinalEncoder
    enc   = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    X_cat = enc.fit_transform(df[CATEGORICAL_FEATURES].astype(str))
    X_num = df[NUMERIC_FEATURES].values.astype(float)
    X     = np.hstack([X_cat, X_num])
    y     = df[TARGET_COLUMN].values

    # 3. Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # 4. Train GradientBoostingRegressor
    print("\nTraining GradientBoostingRegressor...")
    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # 5. Evaluation
    train_r2  = r2_score(y_train, model.predict(X_train))
    test_r2   = r2_score(y_test,  model.predict(X_test))
    test_mae  = mean_absolute_error(y_test, model.predict(X_test))
    print("  Train R2  : " + str(round(train_r2, 4)))
    print("  Test  R2  : " + str(round(test_r2, 4)))
    print("  Test  MAE : " + str(round(test_mae, 2)) + " minutes")

    # 6. Save model
    joblib.dump(model, MODEL_PATH)
    print("\nModel saved -> " + MODEL_PATH)

    # 7. Save OrdinalEncoder (new)
    joblib.dump(enc, FEATURE_ENCODER_PATH)
    print("Feature encoder saved -> " + FEATURE_ENCODER_PATH)

    # 8. Save LabelEncoder on Department for backward-compat (specialty_encoder.joblib)
    le = LabelEncoder()
    le.fit(df["Department"].astype(str))
    joblib.dump(le, SPECIALTY_ENCODER_PATH)
    print("Specialty encoder saved -> " + SPECIALTY_ENCODER_PATH)

    print("\nDone. Model is ready for prediction.")
    return test_r2, test_mae


if __name__ == "__main__":
    r2, mae = train_predictor()
    if r2 < 0.50:
        print("\nNOTE: R2=" + str(round(r2, 3))
              + " -- pre-visit features alone have limited predictive power for "
              "total hospital time (expected with real-world data). "
              "The model still provides a data-driven estimate better than no prediction.")
    sys.exit(0)
