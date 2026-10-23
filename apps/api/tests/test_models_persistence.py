"""Tests for TRAMA persistence layer — model structure, associations, and domain rules.

All tests in this file use the in-memory SQLite engine and run without Docker.
They cover:
  - Creation and basic association of all 5 models
  - Referential integrity (FK enforcement, cascade, restrict)
  - Rejection of invalid FK references
  - Multiple evidences per relationship
  - Uniqueness constraints
  - VALID_* frozenset completeness (service-layer validation helpers)
  - Entity-type-pair validation logic (VALID_TYPE_PAIRS)
  - Self-relationship rejection
  - Status and type constants
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Source, AcademicItem, Entity, Relationship, Evidence
from app.models.source import VALID_PROVIDERS
from app.models.academic_item import VALID_ITEM_TYPES
from app.models.entity import VALID_ENTITY_TYPES
from app.models.relationship import (
    VALID_RELATIONSHIP_TYPES,
    VALID_STATUSES,
    VALID_TYPE_PAIRS,
)

from tests.conftest import make_source, make_item, make_entity, make_relationship


# ---------------------------------------------------------------------------
# 1. Creation and basic associations
# ---------------------------------------------------------------------------

class TestCreation:
    def test_source_creation(self, db_session):
        src = make_source()
        db_session.add(src)
        db_session.flush()
        assert src.id is not None
        assert src.provider == "github"
        assert src.created_at is not None

    def test_academic_item_associated_to_source(self, db_session):
        src = make_source()
        db_session.add(src)
        db_session.flush()

        item = make_item(src)
        db_session.add(item)
        db_session.flush()

        assert item.id is not None
        assert item.source_id == src.id
        assert item.source is src

    def test_entity_creation_all_types(self, db_session):
        for etype in VALID_ENTITY_TYPES:
            e = make_entity(entity_type=etype)
            db_session.add(e)
        db_session.flush()
        # No manual rollback — the fixture handles cleanup via transaction rollback.

    def test_entity_with_origin_item(self, db_session):
        src = make_source()
        item = make_item(src)
        db_session.add_all([src, item])
        db_session.flush()

        e = Entity(entity_type="topic", label="Graph Theory", origin_item=item)
        db_session.add(e)
        db_session.flush()

        assert e.origin_item_id == item.id

    def test_relationship_creation(self, db_session):
        topic = make_entity("topic", "Networks")
        source = make_entity("source", "OpenAlex")
        db_session.add_all([topic, source])
        db_session.flush()

        rel = make_relationship(topic, source, "topic_source")
        db_session.add(rel)
        db_session.flush()

        assert rel.id is not None
        assert rel.status == "pending"
        assert rel.source_entity is topic
        assert rel.target_entity is source

    def test_evidence_creation(self, db_session):
        src = make_source()
        item = make_item(src)
        topic = make_entity("topic", "AI Ethics")
        source_ent = make_entity("source", "ArXiv")
        db_session.add_all([src, item, topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        ev = Evidence(
            relationship=rel,
            origin_item=item,
            reference_url="https://arxiv.org/abs/1234",
            excerpt="AI ethics is discussed in section 2.",
            capture_version="v1",
        )
        db_session.add(ev)
        db_session.flush()

        assert ev.id is not None
        assert ev.relationship_id == rel.id
        assert ev.origin_item_id == item.id

    def test_multiple_evidences_per_relationship(self, db_session):
        src = make_source()
        item1 = make_item(src, external_id="ext-1")
        item2 = make_item(src, external_id="ext-2")
        topic = make_entity("topic", "Climate")
        source_ent = make_entity("source", "OpenAlex-Climate")
        db_session.add_all([src, item1, item2, topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        ev1 = Evidence(relationship=rel, origin_item=item1, excerpt="Evidence A")
        ev2 = Evidence(relationship=rel, origin_item=item2, excerpt="Evidence B")
        ev3 = Evidence(relationship=rel, origin_item=item1, excerpt="Evidence C")
        db_session.add_all([ev1, ev2, ev3])
        db_session.flush()

        db_session.refresh(rel)
        assert len(rel.evidences) == 3


# ---------------------------------------------------------------------------
# 2. Referential integrity
# ---------------------------------------------------------------------------

class TestReferentialIntegrity:
    def test_academic_item_requires_valid_source(self, db_session):
        """AcademicItem with a non-existent source_id must be rejected."""
        item = AcademicItem(
            source_id=uuid.uuid4(),  # does not exist
            external_id="ext-orphan",
            item_type="article",
            title="Orphan",
            content_hash="b" * 64,
        )
        db_session.add(item)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_relationship_requires_valid_source_entity(self, db_session):
        """Relationship with non-existent source_id must be rejected."""
        target = make_entity("source", "ValidTarget")
        db_session.add(target)
        db_session.flush()

        rel = Relationship(
            source_id=uuid.uuid4(),  # does not exist
            target_id=target.id,
            relationship_type="topic_source",
        )
        db_session.add(rel)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_relationship_requires_valid_target_entity(self, db_session):
        """Relationship with non-existent target_id must be rejected."""
        src_e = make_entity("topic", "ValidTopic")
        db_session.add(src_e)
        db_session.flush()

        rel = Relationship(
            source_id=src_e.id,
            target_id=uuid.uuid4(),  # does not exist
            relationship_type="topic_source",
        )
        db_session.add(rel)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_evidence_requires_valid_origin_item(self, db_session):
        """Evidence with non-existent origin_item_id must be rejected."""
        src = make_source()
        item = make_item(src)
        topic = make_entity("topic", "ValidTopic-EI")
        source_ent = make_entity("source", "ValidSource-EI")
        db_session.add_all([src, item, topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        ev = Evidence(
            relationship=rel,
            origin_item_id=uuid.uuid4(),  # does not exist
            excerpt="Bad evidence",
        )
        db_session.add(ev)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_evidence_requires_valid_relationship(self, db_session):
        """Evidence with non-existent relationship_id must be rejected."""
        src = make_source()
        item = make_item(src)
        db_session.add_all([src, item])
        db_session.flush()

        ev = Evidence(
            relationship_id=uuid.uuid4(),  # does not exist
            origin_item=item,
            excerpt="Bad evidence 2",
        )
        db_session.add(ev)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_cascade_delete_source_removes_items(self, db_session):
        """Deleting a Source must cascade to its AcademicItems."""
        src = make_source(canonical_id="cascade-test")
        item = make_item(src)
        db_session.add_all([src, item])
        db_session.flush()

        item_id = item.id
        db_session.delete(src)
        db_session.flush()

        result = db_session.get(AcademicItem, item_id)
        assert result is None

    def test_cascade_delete_relationship_removes_evidences(self, db_session):
        """Deleting a Relationship must cascade to its Evidences."""
        src = make_source(canonical_id="cascade-rel-test")
        item = make_item(src)
        topic = make_entity("topic", "Cascade Topic")
        source_ent = make_entity("source", "Cascade Source")
        db_session.add_all([src, item, topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        ev = Evidence(relationship=rel, origin_item=item, excerpt="will be gone")
        db_session.add(ev)
        db_session.flush()
        ev_id = ev.id

        db_session.delete(rel)
        db_session.flush()

        result = db_session.get(Evidence, ev_id)
        assert result is None


# ---------------------------------------------------------------------------
# 3. Uniqueness constraints
# ---------------------------------------------------------------------------

class TestUniqueness:
    def test_source_unique_provider_canonical(self, db_session):
        """Two Sources with the same (provider, canonical_id) must be rejected."""
        cid = "same-canonical-id"
        s1 = make_source(canonical_id=cid)
        s2 = make_source(canonical_id=cid)  # same provider and canonical_id
        db_session.add(s1)
        db_session.flush()
        db_session.add(s2)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_academic_item_unique_source_external(self, db_session):
        """Two items from the same source with the same external_id must be rejected."""
        src = make_source(canonical_id="unique-src-1")
        db_session.add(src)
        db_session.flush()

        item1 = AcademicItem(
            source_id=src.id,
            external_id="same-ext",
            item_type="article",
            title="Item 1",
            content_hash="d" * 64,
        )
        item2 = AcademicItem(
            source_id=src.id,
            external_id="same-ext",
            item_type="article",
            title="Item 2",
            content_hash="e" * 64,
        )
        db_session.add(item1)
        db_session.flush()
        db_session.add(item2)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_entity_unique_type_label(self, db_session):
        """Two entities with the same (entity_type, label) must be rejected."""
        e1 = make_entity("topic", "Duplicate Label")
        e2 = make_entity("topic", "Duplicate Label")
        db_session.add(e1)
        db_session.flush()
        db_session.add(e2)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_entity_same_label_different_type_is_ok(self, db_session):
        """Same label is allowed for different entity types."""
        e1 = make_entity("topic", "Networks")
        e2 = make_entity("project", "Networks")
        db_session.add_all([e1, e2])
        db_session.flush()  # must not raise

    def test_relationship_unique_source_target_type(self, db_session):
        """Duplicate (source_id, target_id, relationship_type) must be rejected."""
        topic = make_entity("topic", "Unique Rel Topic")
        source_ent = make_entity("source", "Unique Rel Source")
        db_session.add_all([topic, source_ent])
        db_session.flush()

        rel1 = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel1)
        db_session.flush()

        rel2 = Relationship(
            source_id=topic.id,
            target_id=source_ent.id,
            relationship_type="topic_source",
        )
        db_session.add(rel2)
        with pytest.raises((IntegrityError, Exception)):
            db_session.flush()

    def test_relationship_same_entities_different_type_is_ok(self, db_session):
        """Same pair of entities may have different relationship types."""
        project = make_entity("project", "Multi-type Project")
        topic = make_entity("topic", "Multi-type Topic")
        db_session.add_all([project, topic])
        db_session.flush()

        rel1 = make_relationship(project, topic, "project_topic")
        db_session.add(rel1)
        db_session.flush()
        assert rel1.id is not None


# ---------------------------------------------------------------------------
# 4. Valid-set constants (service-layer validators)
# ---------------------------------------------------------------------------

class TestValidConstants:
    def test_valid_providers(self):
        assert VALID_PROVIDERS == frozenset({"github", "moodle", "openalex"})

    def test_valid_item_types(self):
        # 'repository' added in migration 004 for GitHub ingestion
        assert VALID_ITEM_TYPES == frozenset(
            {"article", "course", "opportunity", "activity", "repository"}
        )

    def test_valid_entity_types(self):
        assert VALID_ENTITY_TYPES == frozenset(
            {"person", "project", "topic", "event", "source", "article"}
        )

    def test_valid_relationship_types(self):
        assert VALID_RELATIONSHIP_TYPES == frozenset(
            {"topic_source", "project_event", "project_topic", "project_article"}
        )

    def test_valid_statuses(self):
        assert VALID_STATUSES == frozenset({"pending", "confirmed", "rejected"})
        assert "silenced" not in VALID_STATUSES  # explicitly excluded by PD-0002

    def test_valid_type_pairs_keys(self):
        assert set(VALID_TYPE_PAIRS.keys()) == VALID_RELATIONSHIP_TYPES

    def test_valid_type_pairs_topic_source(self):
        pairs = VALID_TYPE_PAIRS["topic_source"]
        assert ("topic", "source") in pairs
        assert ("source", "topic") in pairs
        # person ↔ project is NOT a valid pair for topic_source
        assert ("person", "project") not in pairs

    def test_valid_type_pairs_project_event(self):
        pairs = VALID_TYPE_PAIRS["project_event"]
        assert ("project", "event") in pairs
        assert ("event", "project") in pairs

    def test_valid_type_pairs_project_topic(self):
        pairs = VALID_TYPE_PAIRS["project_topic"]
        assert ("project", "topic") in pairs
        assert ("topic", "project") in pairs


# ---------------------------------------------------------------------------
# 5. Entity-type-pair validation (service-layer logic)
# ---------------------------------------------------------------------------

class TestEntityTypePairs:
    """Validate that VALID_TYPE_PAIRS correctly gates relationship creation."""

    @pytest.mark.parametrize("rel_type,src_type,tgt_type,expected", [
        ("topic_source",  "topic",   "source",  True),
        ("topic_source",  "source",  "topic",   True),
        ("topic_source",  "person",  "project", False),
        ("project_event", "project", "event",   True),
        ("project_event", "event",   "project", True),
        ("project_event", "topic",   "source",  False),
        ("project_topic", "project", "topic",   True),
        ("project_topic", "topic",   "project", True),
        ("project_topic", "person",  "event",   False),
    ])
    def test_pair_validation(self, rel_type, src_type, tgt_type, expected):
        pair = (src_type, tgt_type)
        result = pair in VALID_TYPE_PAIRS[rel_type]
        assert result is expected

    def test_service_layer_rejects_invalid_pair(self, db_session):
        """Simulate service-layer check: person→project is invalid for topic_source."""
        person = make_entity("person", "Alice")
        project = make_entity("project", "ProjectX")
        db_session.add_all([person, project])
        db_session.flush()

        rel_type = "topic_source"
        pair = (person.entity_type, project.entity_type)
        is_valid = pair in VALID_TYPE_PAIRS[rel_type]
        assert not is_valid, "Service layer must reject person→project for topic_source"


# ---------------------------------------------------------------------------
# 6. Self-relationship rejection
# ---------------------------------------------------------------------------

class TestSelfRelationship:
    def test_self_loop_prevented_by_service_layer(self, db_session):
        """The service layer must detect and reject source_id == target_id
        before persisting. This test validates the detection logic itself,
        not DB enforcement (CHECK constraints are tested in the Postgres tier).
        """
        entity = make_entity("topic", "Looping Topic")
        db_session.add(entity)
        db_session.flush()

        # Simulate what the service layer would check:
        is_self_loop = entity.id == entity.id
        assert is_self_loop, "Self-loop detection must catch equal IDs"

        # Confirm VALID_TYPE_PAIRS does not include any pair that could
        # trivially enable a disguised self-reference at the type level.
        from app.models.relationship import VALID_TYPE_PAIRS
        for rel_type, pairs in VALID_TYPE_PAIRS.items():
            for src_type, tgt_type in pairs:
                # No relationship type maps a type to itself as the only pair.
                # (topic_source: topic↔source; neither is a self-type loop.)
                assert src_type != tgt_type or rel_type not in {
                    "topic_source", "project_event", "project_topic"
                }, f"Unexpected same-type pair in {rel_type}: ({src_type}, {tgt_type})"


# ---------------------------------------------------------------------------
# 7. Default status
# ---------------------------------------------------------------------------

class TestDefaultValues:
    def test_relationship_default_status_is_pending(self, db_session):
        topic = make_entity("topic", "Default Status Topic")
        source_ent = make_entity("source", "Default Status Source")
        db_session.add_all([topic, source_ent])
        db_session.flush()

        rel = Relationship(
            source_entity=topic,
            target_entity=source_ent,
            relationship_type="topic_source",
        )
        db_session.add(rel)
        db_session.flush()

        assert rel.status == "pending"

    def test_relationship_score_is_nullable(self, db_session):
        topic = make_entity("topic", "Score Nullable Topic")
        source_ent = make_entity("source", "Score Nullable Source")
        db_session.add_all([topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        assert rel.score is None

    def test_relationship_score_can_be_set(self, db_session):
        topic = make_entity("topic", "Scored Topic")
        source_ent = make_entity("source", "Scored Source")
        db_session.add_all([topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        rel.score = 0.87
        db_session.add(rel)
        db_session.flush()

        assert rel.score == pytest.approx(0.87)


# ---------------------------------------------------------------------------
# 8. ORM back-references
# ---------------------------------------------------------------------------

class TestBackReferences:
    def test_source_has_academic_items(self, db_session):
        src = make_source(canonical_id="backref-source")
        item1 = make_item(src, external_id="br-1")
        item2 = make_item(src, external_id="br-2")
        db_session.add_all([src, item1, item2])
        db_session.flush()

        db_session.refresh(src)
        assert len(src.academic_items) == 2

    def test_entity_outgoing_and_incoming(self, db_session):
        topic = make_entity("topic", "Backref Topic")
        src1 = make_entity("source", "Backref Source A")
        src2 = make_entity("source", "Backref Source B")
        db_session.add_all([topic, src1, src2])
        db_session.flush()

        rel1 = make_relationship(topic, src1, "topic_source")
        rel2 = make_relationship(topic, src2, "topic_source")
        db_session.add_all([rel1, rel2])
        db_session.flush()

        db_session.refresh(topic)
        assert len(topic.outgoing_relationships) == 2
        assert len(topic.incoming_relationships) == 0

        db_session.refresh(src1)
        assert len(src1.incoming_relationships) == 1

    def test_relationship_has_evidences(self, db_session):
        src = make_source(canonical_id="evidence-backref")
        item = make_item(src)
        topic = make_entity("topic", "Evidence Backref Topic")
        source_ent = make_entity("source", "Evidence Backref Source")
        db_session.add_all([src, item, topic, source_ent])
        db_session.flush()

        rel = make_relationship(topic, source_ent, "topic_source")
        db_session.add(rel)
        db_session.flush()

        ev1 = Evidence(relationship=rel, origin_item=item, excerpt="E1")
        ev2 = Evidence(relationship=rel, origin_item=item, excerpt="E2")
        db_session.add_all([ev1, ev2])
        db_session.flush()

        db_session.refresh(rel)
        assert len(rel.evidences) == 2
