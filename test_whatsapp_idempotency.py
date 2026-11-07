import db
import database
import whatsapp_agent


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "whatsapp-idempotency.db"))
    db.init_db()
    database.init_database()


def _payload(message_id: str):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{
                        "wa_id": "201000000000",
                        "profile": {"name": "Test"},
                    }],
                    "messages": [{
                        "id": message_id,
                        "from": "201000000000",
                        "type": "text",
                        "text": {"body": "Hello Oracle"},
                    }],
                }
            }]
        }]
    }


def test_extract_messages_preserves_meta_message_id():
    messages = whatsapp_agent.extract_messages(_payload("wamid.test.1"))
    assert messages == [{
        "message_id": "wamid.test.1",
        "wa_id": "201000000000",
        "name": "Test",
        "text": "Hello Oracle",
    }]


def test_replayed_webhook_message_is_processed_only_once(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    monkeypatch.setenv("WA_AUTO_REPLY", "draft")
    monkeypatch.setattr(
        whatsapp_agent, "generate_reply", lambda text, contact, history=None: "Safe draft"
    )
    monkeypatch.setattr("income_hunter.is_buyer_intent", lambda text: False)

    first = whatsapp_agent.handle_incoming(_payload("wamid.replay.1"))
    second = whatsapp_agent.handle_incoming(_payload("wamid.replay.1"))

    assert first == [{"wa_id": "201000000000", "mode": "draft", "status": "draft"}]
    assert second == [{"wa_id": "201000000000", "mode": "draft", "status": "duplicate"}]
    assert len(db.list_wa_messages(status="received")) == 1
    assert len(db.list_wa_messages(status="draft")) == 1
    assert len(database.get_chat_history("201000000000", limit=20)) == 1


def test_different_meta_message_ids_are_processed_independently(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    monkeypatch.setenv("WA_AUTO_REPLY", "draft")
    monkeypatch.setattr(
        whatsapp_agent, "generate_reply", lambda text, contact, history=None: "Safe draft"
    )
    monkeypatch.setattr("income_hunter.is_buyer_intent", lambda text: False)

    first = whatsapp_agent.handle_incoming(_payload("wamid.unique.1"))
    second = whatsapp_agent.handle_incoming(_payload("wamid.unique.2"))

    assert first[0]["status"] == "draft"
    assert second[0]["status"] == "draft"
    assert len(db.list_wa_messages(status="received")) == 2
    assert len(database.get_chat_history("201000000000", limit=20)) == 2
