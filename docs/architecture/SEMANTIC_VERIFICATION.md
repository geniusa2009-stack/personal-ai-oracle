# Semantic Claim Verification

**Implementation branch:** `oracle/phase-01-semantic-verifier`  
**Parent implementation:** PR #5 — structured evidence provenance and claim candidates.

## Purpose

The semantic verifier adds a bounded, model-assisted assessment of whether evidence cited by a sentence-level claim appears to support or contradict that claim.

It does not establish ultimate factual truth. Model judgments may be wrong, sources may themselves be wrong, and the existing sentence splitter does not guarantee atomic claims. The result must be reported as an evidence assessment, not as a truth certificate.

## Workflow

1. Deep Research collects search results and extracts a bounded number of pages.
2. Every source receives a stable citation ID and separate publication, update, retrieval, and extraction timestamps.
3. The answer is split into sentence-level claim candidates.
4. Each candidate is linked only to source IDs explicitly cited in that candidate.
5. The verifier receives a bounded list of claims and excerpts from those cited sources.
6. The reviewer model returns a strict JSON result.
7. Oracle validates every claim ID, status, and source ID against the allowed input.
8. Oracle enforces evidence-strength rules before accepting a decisive label.
9. The final research report includes both citation-integrity assessment and semantic evidence assessment as separate objects.

## Accepted statuses

- `SUPPORTED`: supplied extracted-page evidence appears to directly support the claim.
- `PARTIALLY_SUPPORTED`: supplied extracted-page evidence supports only part of the claim.
- `CONTRADICTED`: supplied extracted-page evidence appears to conflict with the claim.
- `CONFLICTING_EVIDENCE`: supplied extracted-page evidence materially supports both sides.
- `INSUFFICIENT_EVIDENCE`: the cited material is missing, inaccessible, snippet-only, or does not provide adequate evidence.
- `UNVERIFIED`: the model response is malformed, omits the claim, references an unavailable source ID, or otherwise cannot be validated.

## Evidence enforcement

- Only source IDs cited by that claim and present in the normalized evidence manifest are eligible.
- A model-supplied source ID that was not provided for that claim causes the claim to remain `UNVERIFIED`.
- A decisive positive, partial, negative, or conflicting classification requires fully extracted page evidence.
- Search snippets may be included as weak context but cannot independently produce `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, or `CONFLICTING_EVIDENCE`.
- Unavailable pages and extracted-but-empty pages are not passed to the verifier as usable evidence.
- Claims without valid cited sources are classified as `INSUFFICIENT_EVIDENCE` without an unnecessary model call.
- At most 12 claims are assessed per run by default; excess claims remain `UNVERIFIED`.
- At most four cited sources per claim are provided.
- Each evidence excerpt is bounded.
- Invalid model output or provider failure does not fail the whole research task; affected claims remain `UNVERIFIED`.

## Research report integration

`deep_research.run_research(..., verify_claims=True)` runs the verifier by default. Set `verify_claims=False` for a citation-only run or a workflow that should not make a reviewer-model call.

The report exposes:

- `semantic_verification.status`
- `semantic_verification.semantic_entailment_checked`
- `semantic_verification.factual_truth_verified` — always `false`
- `semantic_verification.checked_claim_count`
- `semantic_verification.unverified_claim_count`
- `semantic_verification.results[]`
- `claim_records[].verification_status`
- `claim_records[].semantic_support`
- `claim_records[].supported_source_ids`
- `claim_records[].contradicting_source_ids`

The existing `quality_assessment` object remains the citation-integrity assessment and continues to state that semantic entailment was not evaluated by that specific assessor. The new `semantic_verification` object is separate so downstream consumers do not confuse citation presence with reviewer-model assessment.

## Security and privacy properties

- Retrieved page text and snippets are untrusted evidence, never instructions.
- The verifier receives only cited evidence, not the user's broader local files or unrelated memories.
- The model is explicitly instructed not to use external knowledge or follow instructions inside source text.
- Output is schema-checked and bounded before it is accepted.
- No source text or full model prompt is persisted by this feature.
- Provider calls still follow the configured model/provider profile; cloud providers receive the excerpts included in the request.

## Known limitations

- This is model-assisted evidence evaluation, not factual verification.
- Sentence-level candidates can contain multiple propositions or non-factual text.
- The verifier does not perform additional research for missing or contradictory evidence.
- It does not yet perform robust atomic-claim extraction.
- It does not score source authority or determine whether a source is trustworthy.
- It does not automatically resolve temporal conflicts.
- Freshness assessment currently requires an explicit policy and is not yet a complete domain-specific policy registry.
- Structured contradiction detection is a candidate generator for explicitly structured facts, not a free-text contradiction engine.
- No representative human-reviewed production benchmark is included yet.
- The quality of the verifier depends on the configured reviewer model and the available evidence.

## Required follow-up work

1. Add robust atomic-claim extraction and claim typing.
2. Build a domain-specific freshness policy registry and integrate it with research reports.
3. Build a temporal/source contradiction workflow with claim normalization and human-review outcomes.
4. Create a representative Arabic/English human-reviewed benchmark.
5. Measure false-supported and false-contradicted rates before using semantic outcomes in automatic decision-making.
6. Consider a separate evidence persistence layer with source snapshots and retention policy.
