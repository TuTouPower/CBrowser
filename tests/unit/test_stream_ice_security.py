"""Rejected ICE configuration must not disclose credentials in errors."""

import pytest
from cbrowser.stream_agent.ice_transport import validate_ice_servers


@pytest.mark.parametrize(
    "url",
    [
        "http://private_user_947:private_password_947@example.invalid",
        "invalid:private_password_947",
    ],
)
def test_rejected_ice_url_error_hides_private_input(url: str) -> None:
    with pytest.raises(ValueError) as error:
        validate_ice_servers([{"urls": url}])
    assert "private_user_947" not in str(error.value)
    assert "private_password_947" not in str(error.value)
