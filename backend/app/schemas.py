from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SensorReading(BaseModel):
    """One machine snapshot, using the AI4I column names (aliases) or snake_case.

    Strict mode: text in a numeric field (even "42") is rejected rather than coerced,
    as are NaN/Infinity and unknown fields.
    """
    model_config = ConfigDict(
        populate_by_name=True, strict=True, extra="forbid", allow_inf_nan=False,
        json_schema_extra={"example": {
            "type": "M", "air_temperature": 298.1, "process_temperature": 308.6,
            "rotational_speed": 1551, "torque": 42.8, "tool_wear": 10}})

    type: Literal["L", "M", "H"] = Field(alias="Type", description="Product quality variant")
    air_temperature: float = Field(alias="Air temperature", ge=250, le=350, description="K")
    process_temperature: float = Field(alias="Process temperature", ge=250, le=360, description="K")
    rotational_speed: float = Field(alias="Rotational speed", gt=0, le=5000, description="rpm")
    torque: float = Field(alias="Torque", gt=0, le=150, description="Nm")
    tool_wear: float = Field(alias="Tool wear", ge=0, le=400, description="min")

    def to_raw(self) -> dict:
        return self.model_dump(by_alias=True)


class Mechanism(BaseModel):
    mode: str
    label: str
    value: float
    limit: str
    unit: str
    utilisation: float = Field(description="0 = far from limit, >=1 = limit breached")
    breached: bool


class Driver(BaseModel):
    feature: str
    value: float
    contribution: float


class Prediction(BaseModel):
    alarm: bool
    status: Literal["ok", "advisory", "alarm"]
    failure_probability: float
    predicted_failure: str
    most_likely_failure: str
    class_probabilities: dict[str, float]
    rul_minutes: float
    tool_replacement_advised: bool
    threshold: float
    mechanisms: list[Mechanism]
    drivers: list[Driver] = []


class BatchRow(BaseModel):
    row: int
    alarm: bool
    status: str
    failure_probability: float
    predicted_failure: str
    rul_minutes: float
    tool_replacement_advised: bool


class BatchResponse(BaseModel):
    n_rows: int
    n_alarms: int
    n_advisories: int
    by_failure: dict[str, int]
    rows: list[BatchRow]


class ErrorDetail(BaseModel):
    field: str
    message: str
    row: int | None = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str | None = None


class SensorDrift(BaseModel):
    sensor: str
    psi: float
    status: Literal["stable", "moderate", "significant"]
    reference_mean: float
    current_mean: float


class DriftResponse(BaseModel):
    status: Literal["insufficient_data", "stable", "moderate", "significant"]
    n_samples: int
    min_samples: int
    sensors: list[SensorDrift] = []
