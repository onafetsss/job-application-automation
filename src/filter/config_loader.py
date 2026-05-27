"""Load and validate eligibility.yaml into a typed Pydantic v2 model."""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class RolesConfig(BaseModel):
    include: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)


class LocationConfig(BaseModel):
    allow_remote: bool = True
    allowed_locations: list[str] = Field(default_factory=list)
    blocked_phrases: list[str] = Field(default_factory=list)


class SalaryConfig(BaseModel):
    skip_if_no_data: bool = False
    min_annual_usd: int = 0


class KeywordsConfig(BaseModel):
    blocklist: list[str] = Field(default_factory=list)


class EligibilityConfig(BaseModel):
    roles: RolesConfig
    location: LocationConfig = Field(default_factory=LocationConfig)
    salary: SalaryConfig = Field(default_factory=SalaryConfig)
    keywords: KeywordsConfig = Field(default_factory=KeywordsConfig)

    @model_validator(mode="after")
    def check_at_least_one_role(self) -> "EligibilityConfig":
        if not self.roles.include:
            raise ValueError("eligibility.yaml must define at least one role in roles.include")
        return self


def load_eligibility_config(path: str | Path) -> EligibilityConfig:
    """Load and validate eligibility.yaml.

    Args:
        path: Path to the eligibility YAML config file.

    Returns:
        A validated EligibilityConfig Pydantic model.

    Raises:
        FileNotFoundError: If the config file does not exist.
        pydantic.ValidationError: If the YAML schema is invalid or violates constraints.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Eligibility config not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return EligibilityConfig.model_validate(raw)
