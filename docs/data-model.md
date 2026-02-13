# Data Model Overview

## Core Entities

- Asset
- SensorNode
- SensorReading
- RiskAssessment
- FailureForecast
- InspectionTicket
- MaintenanceAction
- VerificationRecord

## Key Relationships

- Asset has many SensorNodes
- SensorNode emits many SensorReadings
- RiskAssessment references one Asset and one time window
- FailureForecast references one Asset and forecast horizon
- MaintenanceAction links to InspectionTicket
- VerificationRecord links to MaintenanceAction and evidence hash
