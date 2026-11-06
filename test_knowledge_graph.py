import pytest

import db
import knowledge_graph


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "knowledge-graph.db"))


def test_entities_are_deduplicated_per_scope_and_isolated(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    first = knowledge_graph.add_entity("owner:one", "AgriSmart", "project")
    duplicate = knowledge_graph.add_entity("owner:one", "  agrismart  ", "concept")
    other_scope = knowledge_graph.add_entity("owner:two", "AgriSmart", "project")

    assert duplicate.id == first.id
    assert duplicate.entity_type == "project"
    assert other_scope.id != first.id
    assert knowledge_graph.get_entity("owner:two", first.id) is None


def test_graph_rejects_secrets_invalid_types_and_oversized_attributes(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.add_entity("owner:one", "password=super-secret", "person")
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.add_entity("owner:one", "Project", "unknown")
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.add_entity(
            "owner:one", "Project", attributes={"notes": "x" * 9000}
        )
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.add_entity("owner:one", "Project", attributes={"password": "x"})


def test_relations_require_same_scope_and_are_idempotent(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "AgriSmart", "project")
    sensor = knowledge_graph.add_entity("owner:one", "ESP32 soil sensor", "tool")
    private = knowledge_graph.add_entity("owner:two", "Private project", "project")

    assert knowledge_graph.link_entities(
        "owner:one", project.id, sensor.id, "uses", evidence="Explicitly recorded by owner"
    ) is True
    assert knowledge_graph.link_entities(
        "owner:one", project.id, sensor.id, "uses", evidence="Duplicate"
    ) is False
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.link_entities("owner:one", project.id, private.id, "related_to")


def test_traversal_is_bounded_cycle_safe_and_scope_isolated(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    a = knowledge_graph.add_entity("owner:one", "A", "concept")
    b = knowledge_graph.add_entity("owner:one", "B", "concept")
    c = knowledge_graph.add_entity("owner:one", "C", "concept")
    knowledge_graph.link_entities("owner:one", a.id, b.id, "related_to")
    knowledge_graph.link_entities("owner:one", b.id, c.id, "related_to")
    knowledge_graph.link_entities("owner:one", c.id, a.id, "related_to")
    knowledge_graph.add_entity("owner:two", "Private", "concept")

    related = knowledge_graph.related_entities("owner:one", a.id, depth=3, limit=10)

    assert {item.entity.id for item in related} == {b.id, c.id}
    assert all(item.entity.scope == "owner:one" for item in related)


def test_graph_context_is_relevant_and_deletion_cleans_edges(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "AgriSmart", "project")
    device = knowledge_graph.add_entity("owner:one", "ESP32", "tool")
    knowledge_graph.link_entities("owner:one", project.id, device.id, "uses")

    context = knowledge_graph.retrieve_context("owner:one", "How does AgriSmart use ESP32?")

    assert "AgriSmart" in context
    assert "ESP32" in context
    assert "uses" in context
    assert knowledge_graph.retrieve_context("owner:two", "AgriSmart") == ""
    assert knowledge_graph.delete_entity("owner:one", device.id) is True
    assert knowledge_graph.related_entities("owner:one", project.id) == []


def test_graph_validates_bounds_and_query_types(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    entity = knowledge_graph.add_entity("owner:one", "Project", "project")
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.related_entities("owner:one", entity.id, depth=4)
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.search_entities("owner:one", None)
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.retrieve_context("owner:one", "Project", max_entities=11)
