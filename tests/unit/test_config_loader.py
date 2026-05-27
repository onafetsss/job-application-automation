"""Unit tests for src/filter/config_loader.py."""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.filter.config_loader import EligibilityConfig, load_eligibility_config


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write a dict as YAML to a temp file and return the path."""
    config_file = tmp_path / "eligibility.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


def test_loads_valid_yaml(tmp_path: Path) -> None:
    """A valid YAML file with roles.include loads into EligibilityConfig correctly."""
    config_file = _write_yaml(
        tmp_path,
        {
            "roles": {"include": ["Product Manager"]},
        },
    )
    result = load_eligibility_config(config_file)
    assert isinstance(result, EligibilityConfig)
    assert result.roles.include == ["Product Manager"]


def test_raises_on_missing_file() -> None:
    """Loading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_eligibility_config("nonexistent_config_file_xyz.yaml")


def test_raises_on_empty_roles_include(tmp_path: Path) -> None:
    """A config with an empty roles.include list must raise ValidationError."""
    config_file = _write_yaml(
        tmp_path,
        {
            "roles": {"include": []},
        },
    )
    with pytest.raises(ValidationError):
        load_eligibility_config(config_file)


def test_raises_on_missing_roles_key(tmp_path: Path) -> None:
    """A config that has no 'roles' key at all must raise ValidationError."""
    config_file = _write_yaml(
        tmp_path,
        {
            "location": {"allow_remote": True},
        },
    )
    with pytest.raises(ValidationError):
        load_eligibility_config(config_file)
