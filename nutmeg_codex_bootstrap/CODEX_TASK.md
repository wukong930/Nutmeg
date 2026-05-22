# CODEX_TASK.md

## Task

Implement Nutmeg V2 from the documents under `docs/nutmeg/`.

V2 is the only valid source of truth. Ignore all V1 assumptions. V1 has been deleted and is deprecated.

## Goal

Create the initial production-ready project skeleton and implement the first development milestone from:

- `docs/nutmeg/08_Nutmeg_Execution_Plan_for_Codex.md`

The long-term goal of Nutmeg is to improve football prediction accuracy over time through:

- prediction snapshots
- feature snapshots
- odds snapshots
- score probability grids
- market resolver
- handicap resolver
- upset detection
- parlay optimization
- post-match evaluation
- error analysis
- model retraining
- model versioning
- probability calibration
- model promotion and rollback

## Instructions Before Coding

Do not start coding immediately.

First:

1. Read `AGENTS.md`.
2. Read all files under `docs/nutmeg/` in the order defined by `AGENTS.md`.
3. Produce a Milestone 1 implementation plan only.
4. Confirm the architecture inferred from the V2 docs.
5. List modules to create.
6. List database entities or migrations to create.
7. List tests to write.
8. List assumptions or ambiguities.
9. Wait for approval before making code changes.

## First Milestone Scope

Do not try to build the entire product in one pass.

For the first implementation pass, complete only:

1. Project structure.
2. Backend skeleton.
3. Database schema / migrations for core entities.
4. Competition configuration structure.
5. Market resolver interfaces.
6. Handicap resolver interfaces.
7. Score probability grid data model.
8. Prediction snapshot model.
9. Basic API contract stubs.
10. Unit test skeleton.
11. README with local setup commands.

## Required Backend Domains

Create clear modules for:

- competitions
- teams
- fixtures
- results
- odds snapshots
- feature snapshots
- prediction snapshots
- score probability grid
- market resolver
- handicap resolver
- parlay optimizer
- upset detector
- accuracy loop
- post-match evaluator
- error analysis
- calibration
- model registry
- model versioning
- competition onboarding

## Required Concepts To Support

The first milestone may use stubs where appropriate, but the architecture must support:

- 1X2
- Chinese lottery handicap 1X2
- Asian handicap
- European handicap 1X2
- correct score
- score grid to market probability conversion
- upset detection
- parlay single selection
- parlay multiple selection
- parlay atomic bet expansion
- total stake calculation
- expected payout
- EV / ROI calculation
- budget constraints
- prediction timestamps
- model version
- feature version
- calibration version
- competition configuration
- provider mapping
- model status per competition

## Non-Goals for First Pass

Do not implement:

- live betting
- automated betting
- real-money betting placement
- wallet
- deposit / withdrawal
- payment
- scraping Bet365
- guaranteed profit recommendation
- final UI polish
- advanced ML training
- full Dixon-Coles training
- full Accuracy Learning Loop automation
- live odds streaming

## Acceptance Criteria

The first pass is complete only when:

1. The project can install dependencies.
2. The backend can start locally.
3. Database models or migrations exist for the core schema.
4. Competition configuration files or structures exist.
5. Score probability grid model exists.
6. Prediction snapshot model stores:
   - `fixture_id`
   - `prediction_time`
   - `model_version`
   - `feature_version`
   - `calibration_version`
   - `score_grid`
   - `market_probabilities`
7. Market resolver has unit tests for:
   - 1X2
   - Chinese handicap 1X2
   - Asian handicap integer line
   - Asian handicap half line
   - Asian handicap quarter line
8. Parlay optimizer has unit tests for:
   - single-selection 2x1
   - multiple-selection 4x1
   - atomic bet expansion
   - total stake calculation
   - expected payout calculation
   - EV / ROI calculation
9. No V1 document or assumption is referenced.
10. Local setup instructions are documented.

## Suggested Milestone 1 Implementation Order

1. Initialize project structure.
2. Add configuration and environment handling.
3. Add database schema / ORM models / migrations.
4. Add domain modules and interfaces.
5. Add market resolver core interfaces.
6. Add handicap resolver interfaces and core settlement helpers.
7. Add parlay optimizer interfaces and atomic expansion helper.
8. Add score probability grid model.
9. Add prediction snapshot model.
10. Add API route stubs.
11. Add tests.
12. Run validation.
13. Report results.

## Reporting Format

After implementation, report:

1. Summary
2. Files created
3. Files modified
4. Tests added
5. Tests run
6. Type checks / linting run
7. Known gaps
8. Recommended next milestone

## Reminder

Accuracy is the product goal. Do not optimize for flashy recommendations. Optimize for probability correctness, calibration, testability, traceability, and future model improvement.
