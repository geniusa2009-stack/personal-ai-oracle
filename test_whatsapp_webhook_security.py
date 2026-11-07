import hashlib
import hmac
import json

import whatsapp_agent


def _signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def test_meta_signature_verification_uses_exact_body_and_secret():
    body = b'{"entry":[]}'
    secret = "test-meta-app-secret"

    assert whatsapp_agent.verify_meta_signature(body, _signature(body, secret), secret)
    assert not whatsapp_agent.verify_meta_signature(body + b" ", _signature(body, secret), secret)
    assert not whatsapp_agent.verify_meta_signature(body, _signature(body, secret), "wrong-secret")
    assert not whatsapp_agent.verify_meta_signature(body, "sha1=invalid", secret)
    assert not whatsapp_agent.verify_meta_signature(body, "", secret)
    assert not whatsapp_agent.verify_meta_signature(body, _signature(body, secret), "")


def test_webhook_rejects_missing_or_invalid_signature_before_processing(monkeypatch):
    secret = "test-meta-app-secret"
    body = json.dumps({"entry": []}).encode("utf-8")
    handled = []
    monkeypatch.setenv("WA_APP_SECRET", secret)
    monkeypatch.setattr(
        whatsapp_agent, "handle_incoming", lambda payload: handled.append(payload) or []
    )
    client = whatsapp_agent.create_app().test_client()

    missing = client.post("/webhook", data=body, content_type="application/json")
    invalid = client.post(
        "/webhook", data=body, content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64},
    )

    assert missing.status_code == 403
    assert invalid.status_code == 403
    assert handled == []


def test_webhook_accepts_valid_signed_json(monkeypatch):
    secret = "test-meta-app-secret"
    body = b'{"entry":[]}'
    handled = []
    monkeypatch.setenv("WA_APP_SECRET", secret)
    monkeypatch.setattr(
        whatsapp_agent, "handle_incoming", lambda payload: handled.append(payload) or []
    )
    client = whatsapp_agent.create_app().test_client()

    response = client.post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": _signature(body, secret)},
    )

    assert response.status_code == 200
    assert response.get_json() == {"received": True, "actions": []}
    assert handled == [{"entry": []}]


def test_webhook_verification_rejects_unconfigured_or_wrong_token(monkeypatch):
    client = whatsapp_agent.create_app().test_client()
    monkeypatch.delenv("WA_VERIFY_TOKEN", raising=False)

    missing = client.get("/webhook?hub.mode=subscribe&hub.challenge=abc")
    assert missing.status_code == 403

    monkeypatch.setenv("WA_VERIFY_TOKEN", "configured-token")
    wrong = client.get(
        "/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc"
    )
    assert wrong.status_code == 403

    valid = client.get(
        "/webhook?hub.mode=subscribe&hub.verify_token=configured-token&hub.challenge=abc"
    )
    assert valid.status_code == 200
    assert valid.data == b"abc"
