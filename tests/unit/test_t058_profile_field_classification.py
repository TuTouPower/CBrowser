"""t058 A24: the generated frontend field classification must match the
backend constants, and the three classes must partition ProfileConfig.
"""

from pathlib import Path

from cbrowser.adapters.database.repository import (
    CONFIG_VERSION_FIELDS,
    INSTANT_FIELDS,
    METADATA_FIELDS,
)
from cbrowser.domain.models import ProfileConfig
from scripts.export_profile_field_classification import (
    export_profile_field_classification,
    render_profile_field_classification,
)


def test_generated_classification_matches_backend(tmp_path: Path):
    """Regenerating from the live backend constants reproduces the
    checked-in generated file byte for byte."""
    generated = tmp_path / "profile_field_classification.ts"
    export_profile_field_classification(generated)
    checked_in = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "frontend"
        / "src"
        / "shared"
        / "api"
        / "generated"
        / "profile_field_classification.ts"
    )
    assert generated.read_text(encoding="utf-8") == checked_in.read_text(
        encoding="utf-8"
    )


def test_classification_partitions_profile_config_fields():
    """metadata / instant / runtime are disjoint and cover every
    ProfileConfig field, so the frontend can never silently drop a field
    into the wrong submission path."""
    rendered = render_profile_field_classification()
    assert "capture_preview" in rendered
    assert set(METADATA_FIELDS).isdisjoint(INSTANT_FIELDS)
    assert set(METADATA_FIELDS).isdisjoint(CONFIG_VERSION_FIELDS)
    assert set(INSTANT_FIELDS).isdisjoint(CONFIG_VERSION_FIELDS)
    assert (
        set(METADATA_FIELDS)
        | set(INSTANT_FIELDS)
        | set(CONFIG_VERSION_FIELDS)
    ) == set(ProfileConfig.model_fields)
    assert INSTANT_FIELDS == frozenset({"capture_preview"})
