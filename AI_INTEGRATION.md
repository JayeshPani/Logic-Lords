```markdown
# InfraGuard AI Integration Specification

## Overview

This document defines the complete AI architecture for InfraGuard.
It specifies:

- Data pipeline structure
- LSTM model for 72-hour failure prediction
- Isolation Forest for anomaly detection
- Fuzzy Logic inference engine for final risk scoring
- End-to-end integration flow

This file serves as implementation guidance for backend AI integration.

---

# 1. Data Pipeline Specification

## 1.1 Sensor Inputs (Raw)

Each timestamped record must contain:

- strain_value (float)
- vibration_rms (float)
- temperature (float)
- humidity (float)
- traffic_density (float, optional)
- rainfall_intensity (float, optional)
- timestamp (datetime)

All values must be normalized to 0–1 range before model input.

---

# 2. LSTM Model – Failure Prediction

## 2.1 Purpose

Predict failure probability within the next 72 hours.

## 2.2 Input

Time window sequence of last 48 hours.

Shape:
(samples, time_steps, features)

Example:
(1, 2880, 4)  # if sampling every minute for 48 hours

Features:
- normalized strain
- normalized vibration
- normalized temperature
- normalized humidity

## 2.3 Output

- failure_probability (float between 0 and 1)

## 2.4 Model Architecture

```

Input Layer
LSTM (64 units, return_sequences=True)
Dropout (0.2)
LSTM (32 units)
Dense (16 units, relu)
Dense (1 unit, sigmoid)

```

Loss:
- Binary Crossentropy (if classification)
or
- MSE (if regression)

Optimizer:
- Adam

---

# 3. Isolation Forest – Anomaly Detection

## 3.1 Purpose

Detect sudden abnormal structural behavior:
- Earthquake-like vibration spikes
- Sudden strain increase
- Sensor malfunction

## 3.2 Input Features

- current strain
- current vibration
- temperature
- humidity

## 3.3 Output

- anomaly_score
- anomaly_flag (0 = normal, 1 = anomaly)

Recommended configuration:

```

IsolationForest(
n_estimators=100,
contamination=0.02,
random_state=42
)

```

If anomaly_score < threshold → flag anomaly.

---

# 4. Fuzzy Logic Risk Inference System

## 4.1 Purpose

Convert ML outputs and sensor values into
interpretable Infrastructure Risk Level.

Inference Type:
Mamdani Fuzzy Inference

Defuzzification:
Centroid method

---

# 5. Fuzzy Input Variables

## 5.1 Strain

- Low: triangular (0.0, 0.0, 0.3)
- Moderate: triangular (0.2, 0.5, 0.7)
- High: triangular (0.6, 0.8, 0.9)
- Critical: trapezoidal (0.85, 0.9, 1.0, 1.0)

## 5.2 Vibration

- Stable: triangular (0.0, 0.0, 0.3)
- Elevated: triangular (0.2, 0.5, 0.7)
- Severe: trapezoidal (0.6, 0.8, 1.0, 1.0)

## 5.3 Temperature

- Normal: triangular (0.0, 0.0, 0.4)
- Warm: triangular (0.3, 0.5, 0.7)
- Hot: triangular (0.6, 0.8, 0.9)
- Extreme: trapezoidal (0.85, 0.9, 1.0, 1.0)

## 5.4 Rainfall

- None: triangular (0.0, 0.0, 0.2)
- Light: triangular (0.1, 0.4, 0.6)
- Heavy: trapezoidal (0.5, 0.7, 1.0, 1.0)

## 5.5 Traffic Density

- Low: triangular (0.0, 0.0, 0.3)
- Medium: triangular (0.2, 0.5, 0.7)
- High: trapezoidal (0.6, 0.8, 1.0, 1.0)

## 5.6 Failure Probability (from LSTM)

- Low: triangular (0.0, 0.0, 0.4)
- Medium: triangular (0.3, 0.5, 0.7)
- High: trapezoidal (0.6, 0.8, 1.0, 1.0)

## 5.7 Anomaly Score

- Normal: triangular (0.0, 0.0, 0.4)
- Abnormal: triangular (0.3, 0.6, 0.8)
- Severe: trapezoidal (0.7, 0.85, 1.0, 1.0)

---

# 6. Fuzzy Output Variable

Infrastructure Risk Level

- Very Low (0.0–0.2)
- Low (0.2–0.4)
- Moderate (0.4–0.6)
- High (0.6–0.8)
- Critical (0.8–1.0)

---

# 7. Fuzzy Rule Base

Examples:

R1:
IF Strain IS Low AND Vibration IS Stable
THEN Risk IS Low

R2:
IF Strain IS Moderate AND Temperature IS Warm
THEN Risk IS Moderate

R3:
IF Strain IS High AND Traffic IS High
THEN Risk IS High

R4:
IF Rainfall IS Heavy AND Fatigue IS High
THEN Risk IS Critical

R5:
IF Failure Probability IS High
THEN Risk IS Critical

R6:
IF Anomaly Score IS Severe
THEN Risk IS Critical

R7:
IF Temperature IS Extreme AND Strain IS High
THEN Risk IS Critical

Minimum recommended rule count: 10–20 rules.

---

# 8. Final Risk Computation Pipeline

Step 1:
Collect and normalize sensor data

Step 2:
Feed time-window data to LSTM
→ get failure_probability

Step 3:
Run current data through Isolation Forest
→ get anomaly_flag

Step 4:
Feed:
- strain
- vibration
- temperature
- rainfall
- traffic
- failure_probability
- anomaly_score

into fuzzy inference engine

Step 5:
Defuzzify output
→ final_risk_score (0–1)

Step 6:
Store:
- final_risk_score
- failure_probability
- anomaly_flag

Send to dashboard and blockchain layer.

---

# 9. Expected Output Format

```

{
"health_score": 0.73,
"failure_probability_72h": 0.65,
"anomaly_flag": 0,
"risk_level": "High",
"timestamp": "ISO8601"
}

```

---

# 10. Deployment Notes

- Train LSTM offline
- Save model as .h5
- Load model in FastAPI backend
- Run inference in API endpoint
- Isolation Forest can run in real-time
- Fuzzy engine must execute in under 50ms

---

# End of AI Integration Specification
```