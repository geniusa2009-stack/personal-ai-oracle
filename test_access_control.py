import access_control


def test_app_password_requires_a_strong_configured_secret():
    assert access_control.verify_app_password("short", "short") is False
    assert access_control.verify_app_password("correct horse battery staple", "") is False


def test_app_password_matches_exactly():
    expected = "a-long-owner-passphrase-with-entropy"
    assert access_control.verify_app_password(expected, expected) is True
    assert access_control.verify_app_password(expected + "x", expected) is False
    assert access_control.verify_app_password(expected.upper(), expected) is False


def test_app_password_uses_environment_when_expected_is_omitted(monkeypatch):
    monkeypatch.setenv("ORACLE_APP_PASSWORD", "another-long-owner-passphrase")
    assert access_control.verify_app_password("another-long-owner-passphrase") is True
    monkeypatch.delenv("ORACLE_APP_PASSWORD")
    assert access_control.verify_app_password("another-long-owner-passphrase") is False
