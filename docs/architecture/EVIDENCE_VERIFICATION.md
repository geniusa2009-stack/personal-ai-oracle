# Evidence Verification — Current Contract and Next Steps

**Implementation branch:** `oracle/phase-01-evidence-foundation`  
**Parent audit:** PR #4 (`oracle/phase-00-architecture-audit`)  
**Scope:** Structured evidence provenance and sentence-level claim candidates.

## Purpose

This document describes the first additive evidence-verification increment. It establishes explicit data contracts and deterministic structural checks that can support later semantic verification.

It does **not** claim that Oracle can currently prove factual truth or determine semantic entailment. Candidate claims remain `UNVERIFIED` until an independent verifier and appropriate evaluation process are implemented.

## Source evidence record

The `evidence_verification.normalize_source` function normalizes one research source into a bounded provenance record.

Fields include:

- `citation_id`: stable S-number used by the current report.
- `title`, `url`, `publisher`, `domain`.
- `source_class`: a discovery hint, not an authority verdict.
- `page_status`: fetch/extraction result.
- `evidence_level`: `extracted_page`, `search_snippet_only`, `no_content`, `unavailable_or_partial`, or `unknown`.
- `published_at`: publisher/search/extractor publication date hint, if provided.
- `updated_at`: publisher/search/extractor update date hint, if provided.
- `retrieved_at`: when Oracle collected the search result.
- `extracted_at`: when Oracle extracted page content.
- `date_metadata_origin`: where supplied date hints came from.

Dates are normalized to UTC where parseable. Invalid date hints become unknown rather than being silently interpreted.

### Temporal semantics

These timestamps are intentionally distinct:

- `published_at` is not the same as `retrieved_at`.
- `updated_at` may be a better freshness reference than publication date.
- `extracted_at` only records when Oracle extracted a page.
- Recent retrieval or extraction does not make old source content fresh.

The freshness evaluator requires an explicit `max_age_days` policy. If no policy is supplied, its status is `not_assessed`; if the source has no usable publication/update date, its status is `unknown`. There is no universal age threshold configured by this increment.

## Claim candidate record

`build_claim_candidates` splits the generated answer into sentence-level candidates and associates valid citation IDs with normalized source metadata.

Each record includes:

- `claim_id`
- `text`
- `claim_type = unclassified`
- `granularity = sentence_level_candidate`
- valid and invalid source IDs
- citation-presence status
- `verification_status = UNVERIFIED`
- `semantic_support = not_evaluated`
- bounded evidence metadata for referenced sources

Sentence splitting is a structural starting point. It does not guarantee one atomic proposition per sentence, extract subject/predicate/object semantics, or perform entailment. Those are subsequent milestones.

## Structured contradiction candidates

`detect_structured_contradictions` accepts only explicitly structured claims containing:

- `subject`
- `predicate`
- `object`
- optional `valid_from` and `valid_until`
- optional source IDs

It identifies pairs with the same normalized subject and predicate but different values. Temporal periods that are definitely disjoint are not flagged as conflicts. Missing or ambiguous temporal bounds produce a potential conflict requiring review.

The result status is `POTENTIAL_CONTRADICTION`, not a semantic contradiction verdict. This function deliberately does not infer structure from free-text claims.

## Deep Research integration

The deep-research report now includes:

- `sources`: source entries enriched with publisher/date/provenance fields and evidence level.
- `evidence_manifest`: normalized source records.
- `evidence_summary`: counts of extracted, snippet-only, and unavailable/partial sources, plus candidate claim count.
- `claim_records`: sentence-level candidates that remain unverified.
- Existing `claim_evidence` and `quality_assessment` fields remain for backward compatibility.

Search-provider and page-extractor date hints are preserved as unverified metadata. The date origin is recorded; a date's presence is not proof that the date is authoritative.

The compact research report keeps a bounded subset of the evidence and claim metadata so planner/tool context remains size-limited.

## Current non-goals

This increment does not yet implement:

- Model-assisted atomic claim extraction.
- Semantic entailment verification.
- Claim-type classification.
- Domain-specific freshness policy registry.
- Automatic structured fact extraction from prose.
- Persistent evidence storage or source snapshots.
- Source authority scoring.
- Human review workflows.
- Representative production evaluation data.

## Required next increment

Build and integrate a bounded semantic claim verifier that:

1. Receives one candidate claim and only its referenced evidence.
2. Treats all source text as untrusted data, never as instructions.
3. Returns a schema-validated classification and exact supporting/contradicting source IDs.
4. Rejects source IDs not supplied to the verifier.
5. Uses `INSUFFICIENT_EVIDENCE` when evidence is missing or weak.
6. Distinguishes extracted-page evidence from snippet-only evidence.
7. Never equates a model judgment with verified factual truth.
8. Has deterministic offline tests and a reviewed bilingual evaluation set.
