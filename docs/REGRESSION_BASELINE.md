# Radar-News regression baseline

This file is the release contract for changes to collection, ranking, deduplication, scoring, scheduling, and deployment. A green workflow is necessary but is not sufficient for content acceptance.

## Non-regression requirements

1. **GLOBAL TOP eligibility**
   - Routine county/city/provincial discipline-inspection notices must not qualify for GLOBAL TOP solely because the publisher is authoritative or because the item has a high source score.
   - Exceptional central-level or systemically significant investigations may qualify.
   - International conflict, material political developments, macroeconomics, major policy, diplomacy, disasters/public health, and major science/technology events compete on event impact and freshness.
   - A repeated topic is a soft diversity consideration, never a reason to suppress a materially more important event.

2. **Cross-edition deduplication**
   - Suppress an unchanged event from GLOBAL TOP when it was in the previous published edition.
   - Allow re-entry when there is a material new development.
   - Do not use GLOBAL TOP's previous-edition suppression set to delete stories from country sections.

3. **Country coverage**
   - Each country section must contain no more than 30 events.
   - Repeated stories across editions may remain in country sections if still within the collection window and relevant.
   - Distinguish source failure/empty feeds from a genuinely quiet news day; do not fabricate stories to hit a target count.

4. **Pipeline and deployment**
   - Test failure must stop the publication pipeline.
   - A new snapshot must be committed before deployment.
   - Confirm the deployed page reflects the new snapshot; successful Actions alone does not prove content quality.
   - Beijing schedule target: daily at 06:00 and 17:00. Monitor scheduler dispatch, production run, snapshot commit, and Pages deployment independently.

## Required evidence for each change

- List changed files and which requirements they can affect.
- Run the targeted regression tests and the full daily workflow.
- Inspect the generated snapshot for GLOBAL TOP composition, repeated-event rate, country counts (max 30), source-health report, and translation validation.
- Confirm the snapshot commit and deployed site version.
- If any check fails or is not performed, report it as failed or unverified; do not claim the release is complete.

## Known regression cases to retain

- Ordinary local official investigation notices must not dominate GLOBAL TOP.
- A significant central-level investigation can still appear in the China politics section and may qualify for GLOBAL TOP based on significance.
- Previous-edition deduplication must not remove the same valid event from a country section.
- One event reported by multiple outlets must not occupy multiple GLOBAL TOP slots.
- Materially updated events may re-enter GLOBAL TOP.
- A source outage must be distinguishable from zero real news.
- Any country section exceeding 30 events is a hard failure.
- Schedule or Pages failure must not be mistaken for a fresh published edition.

5. **AI/LLM daily coverage and importance parity**
   - Collect AI/LLM news on every scheduled production run, using official company/research sources and independent international reporting; retain major Chinese AI labs as first-class coverage.
   - AI/LLM news must use the same 0–100 event-importance model and freshness logic as mainstream news, not an isolated arbitrary ranking scale.
   - Freshness matters: for otherwise comparable stories, a newer event must outrank an older one.
   - The module targets 20 distinct items, but must report partial coverage honestly rather than inventing or indefinitely recycling stale stories to fill the quota.
   - Keep source-health evidence for AI feeds so an empty day can be distinguished from collection failures.
   - Verify Chinese headline translations and inspect the latest AI/LLM publication dates in each release.
