"""Profile configuration loader — parses profile.yaml into a typed Pydantic model."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class KeyProject(BaseModel):
    """A single key project entry from profile.yaml."""

    name: str
    impact: str


class ProfileConfig(BaseModel):
    """Typed model for config/profile.yaml.

    All fields are required — the profile must be fully populated before deploy.
    """

    summary: str
    target_roles: list[str]
    key_projects: list[KeyProject]
    skills: list[str]
    location_preference: str
    availability: str


def load_profile_config(path: str | Path) -> ProfileConfig:
    """Load and validate profile.yaml into a ProfileConfig model.

    Args:
        path: Path to the profile YAML config file.

    Returns:
        A validated ProfileConfig Pydantic model.

    Raises:
        FileNotFoundError: If the config file does not exist.
        pydantic.ValidationError: If the YAML schema is invalid.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Profile config not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return ProfileConfig.model_validate(raw)
