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

    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.add_entity(
            "owner:one", "Project", attributes={"metadata": {"private_key": "hidden"}}
        )


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


def test_graph_context_is_injected_into_ai_prompt_with_scope_isolation(monkeypatch, tmp_path):
    import ai_core

    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "Personal AI Oracle", "project")
    agent = knowledge_graph.add_entity("owner:one", "Researcher agent", "tool")
    knowledge_graph.link_entities("owner:one", project.id, agent.id, "contains")
    knowledge_graph.add_entity("owner:two", "Private unrelated data", "concept")

    messages = [
        {"role": "system", "content": "You are Oracle."},
        {"role": "user", "content": "Explain Personal AI Oracle and its researcher agent."},
    ]
    enriched = ai_core._messages_with_memory(messages, "owner:one")
    other_scope = ai_core._messages_with_memory(messages, "owner:two")

    assert "<personal_knowledge_graph>" in enriched[0]["content"]
    assert "Personal AI Oracle" in enriched[0]["content"]
    assert "Researcher agent" in enriched[0]["content"]
    assert "<personal_knowledge_graph>" not in other_scope[0]["content"]
    assert "Private unrelated data" not in other_scope[0]["content"]


def test_list_entities_and_relations_are_scope_filtered_and_bounded(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "Oracle", "project")
    agent = knowledge_graph.add_entity("owner:one", "Researcher", "tool")
    private = knowledge_graph.add_entity("owner:two", "Private", "project")
    knowledge_graph.link_entities("owner:one", project.id, agent.id, "contains")
    knowledge_graph.link_entities("owner:two", private.id, knowledge_graph.add_entity(
        "owner:two", "Other", "concept"
    ).id, "related_to")

    assert {item.name for item in knowledge_graph.list_entities("owner:one")} == {"Oracle", "Researcher"}
    relations = knowledge_graph.list_relations("owner:one")
    assert len(relations) == 1
    assert relations[0]["source_name"] == "Oracle"
    assert knowledge_graph.list_relations("owner:two", entity_id=project.id) == []
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.list_entities("owner:one", limit=101)
    with pytest.raises(knowledge_graph.KnowledgeGraphError):
        knowledge_graph.list_relations("owner:one", limit=201)



def test_graph_retrieval_returns_scoped_expansion_terms_and_relation_provenance(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "AgriSmart", "project")
    sensor = knowledge_graph.add_entity("owner:one", "ESP32 soil sensor", "tool")
    private = knowledge_graph.add_entity("owner:two", "Private ESP32 sensor", "tool")
    knowledge_graph.link_entities(
        "owner:one",
        project.id,
        sensor.id,
        "uses",
        evidence="Owner-confirmed architecture record",
    )
    knowledge_graph.link_entities(
        "owner:two",
        private.id,
        knowledge_graph.add_entity("owner:two", "Private field", "place").id,
        "located_at",
        evidence="Private scope record",
    )

    graph = knowledge_graph.retrieve_graph(
        "owner:one", "How does AgriSmart work?", max_entities=5, max_relations=5
    )

    assert graph.seed_count == 1
    assert graph.relation_count == 1
    assert graph.seed_entities[0].id == project.id
    assert graph.related_entities[0].entity.id == sensor.id
    assert graph.related_entities[0].evidence == "Owner-confirmed architecture record"
    assert "AgriSmart" in graph.expansion_terms
    assert "ESP32 soil sensor" in graph.expansion_terms
    assert "Owner-confirmed architecture record" in graph.context_text
    assert "Private ESP32 sensor" not in graph.context_text

    other = knowledge_graph.retrieve_graph("owner:two", "AgriSmart")
    assert other.seed_count == 0
    assert other.related_entities == ()


def test_graph_retrieval_respects_relation_and_entity_limits(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    project = knowledge_graph.add_entity("owner:one", "Oracle project", "project")
    first = knowledge_graph.add_entity("owner:one", "First tool", "tool")
    second = knowledge_graph.add_entity("owner:one", "Second tool", "tool")
    knowledge_graph.link_entities("owner:one", project.id, first.id, "uses")
    knowledge_graph.link_entities("owner:one", project.id, second.id, "uses")

    graph = knowledge_graph.retrieve_graph(
        "owner:one", "Oracle project", max_entities=1, max_relations=1
    )

    assert graph.seed_count == 1
    assert graph.relation_count == 1
    assert len(graph.expansion_terms) == 2
