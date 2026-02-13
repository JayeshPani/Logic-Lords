# Risk Model Strategy

## Inputs

- Strain
- Vibration
- Temperature
- Humidity
- Tilt
- Optional contextual feeds (weather, traffic)

## Components

- Fuzzy risk component for uncertain states
- LSTM forecast component for temporal trend
- Weighted fusion for unified health score [0,1]

## Output Semantics

- `0.00 - 0.30`: Healthy
- `0.31 - 0.60`: Watch
- `0.61 - 0.80`: Warning
- `0.81 - 1.00`: Critical
