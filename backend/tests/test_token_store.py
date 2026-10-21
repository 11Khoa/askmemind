from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError

from app.core.security import create_access_token, decode_access_token
from app.services.token_store import TokenStore, TokenStoreUnavailable


def test_blacklist_sets_expiry_to_remaining_access_lifetime():
    client = Mock()
    store = TokenStore(client)
    payload = decode_access_token(create_access_token("user"))
    store.revoke_access(payload)
    args, kwargs = client.set.call_args
    assert args == (f"auth:revoked:{payload.jti}", "1")
    remaining = (payload.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert remaining <= kwargs["ex"] <= remaining + 2


def test_blacklist_checks_identifier():
    client = Mock()
    client.exists.return_value = 1
    assert TokenStore(client).is_revoked("identifier")
    client.exists.assert_called_once_with("auth:revoked:identifier")


def test_blacklist_connection_failure_is_not_treated_as_valid_token():
    client = Mock()
    client.exists.side_effect = ConnectionError("offline")
    with pytest.raises(TokenStoreUnavailable):
        TokenStore(client).is_revoked("identifier")
