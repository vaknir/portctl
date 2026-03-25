# Plan: Improve Scorecard Diff Output

## Goal
Eliminate false-positive diffs in scorecard rule comparisons (dict key reordering, API-injected `description` fields) and make legitimate changes readable by showing field-level diffs instead of full JSON blobs.

## Acceptance Criteria
- [x] Scorecard rules with only dict key reordering differences produce no diff
- [x] API-injected `description` fields on scorecard rules are stripped before comparison
- [x] Rules are matched by `identifier` field, not by list position or content similarity
- [x] When rules have real changes, formatter shows field-level diffs (e.g., `- description`, `~ level: B → A`) instead of `{full_old_dict} → {full_new_dict}`
- [x] All existing unit tests pass (348 total)
- [x] Linting passes

## Tasks

### Phase 1: Planner normalization (sequential)
1. [x] Normalize scorecard rules in `_normalize_for_diff` — agent: senior-dev, depends: none
   - Sort `rules` list by `identifier`
   - Strip `description` from each rule (API-injected metadata)

### Phase 2: Formatter improvement
2. [x] Improve `_build_change_lines` in diffs.py — agent: senior-dev, depends: 1
   - Detect when `values_changed` has dict old/new values
   - Compute sub-diff via `_build_dict_sub_diff` and show field-level changes
   - Show rule identifier as label
   - Use JSON formatting for nested dict/list values

### Phase 3: Quality
3. [x] Write tests — 12 new tests (4 planner, 8 formatter)
4. [x] Run tests and lint — 348 pass, 0 lint errors
5. [x] Tech-lead review — approved with suggestions applied

## Complexity: S
## Estimated agents: senior-dev, tech-lead
