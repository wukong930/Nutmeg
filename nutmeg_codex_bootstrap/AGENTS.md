# AGENTS.md

## Project

Project name: Nutmeg

Nutmeg is a football match prediction platform. The final goal is to improve prediction accuracy over time, not to create a betting hype product.

## Single Source of Truth

The only valid product and technical documents are under:

- `docs/nutmeg/`

All previous V1 documents are deleted and deprecated.

If any historical implementation, memory, generated code, or old assumption conflicts with `docs/nutmeg/`, follow `docs/nutmeg/`.

## Required Reading Order

Before implementing, read these files in order:

1. `docs/nutmeg/00_Nutmeg_README.md`
2. `docs/nutmeg/01_Nutmeg_PRD.md`
3. `docs/nutmeg/02_Nutmeg_System_Architecture.md`
4. `docs/nutmeg/06_Nutmeg_Database_and_API_Spec.md`
5. `docs/nutmeg/05_Nutmeg_Markets_Handicap_Parlay_Rules.md`
6. `docs/nutmeg/04_Nutmeg_Modeling_and_Accuracy_Loop.md`
7. `docs/nutmeg/03_Nutmeg_Data_and_Competition_Onboarding.md`
8. `docs/nutmeg/07_Nutmeg_Frontend_Design_Spec.md`
9. `docs/nutmeg/08_Nutmeg_Execution_Plan_for_Codex.md`
10. `docs/nutmeg/09_Nutmeg_Ops_Compliance_and_Governance.md`
11. `docs/nutmeg/10_Nutmeg_Glossary_and_References.md`

## Development Principles

1. Build from the V2 documents only.
2. Do not implement betting placement, automated betting, account wallet, payment, or guaranteed-profit language.
3. The system must output probabilities, uncertainty, model version, feature version, calibration version, and prediction timestamp where applicable.
4. The core prediction design is:

   ```text
   score probability grid -> market resolver -> upset detector -> parlay optimizer -> frontend/API display
   ```

5. The MVP may start with a Poisson baseline, but the architecture must allow Dixon-Coles v1.5 and the Accuracy Learning Loop.
6. Do not hardcode only the World Cup or top five European leagues. Use competition configuration.
7. Implement Chinese sports lottery handicap, Asian handicap, European handicap, correct score, and parlay logic through a rule engine / market resolver.
8. Keep code modular, typed, testable, and easy to extend.
9. Every milestone must include tests.
10. If a requirement is ambiguous, make the safest implementation consistent with `docs/nutmeg/` and document the assumption.

## Accuracy-First Requirement

Accuracy is the product goal. Do not optimize for flashy recommendations. Optimize for:

- probability correctness
- calibration
- testability
- traceability
- explainability
- model versioning
- future model improvement

## Modeling Principles

The system must distinguish between:

- model probability
- market implied probability
- calibrated probability
- confidence / data quality
- recommendation score

Do not treat a high-probability outcome as automatically valuable. A recommendation requires both probability quality and market/value analysis when odds are involved.

## Prediction Memory and Learning Loop

The system must be designed to remember predictions and improve through a formal feedback loop:

1. store prediction snapshots before matches
2. store feature snapshots and odds snapshots
3. store final results and post-match statistics
4. evaluate prediction quality after matches
5. classify errors
6. update calibration and model reports
7. retrain models periodically
8. compare model versions
9. promote or roll back model versions based on evidence

Do not claim the system “learns” unless the Accuracy Learning Loop is implemented and tested.

## Competition Expansion

All competitions must be onboarded through configuration and provider mapping. The implementation must support future addition of:

- top five European leagues
- Japanese leagues
- Korean leagues
- Dutch league
- UEFA Champions League
- UEFA Europa League
- UEFA European Championship
- World Cup
- domestic cups
- other club and national-team competitions

New competitions may be marked as beta until data coverage, backtests, and calibration are sufficient.

## Market and Parlay Rules

The system must support, at minimum:

- 1X2
- Chinese lottery handicap 1X2
- Asian handicap, including integer, half, and quarter lines
- European handicap 1X2
- correct score
- upset detection
- single-selection parlays
- multiple-selection parlays
- atomic bet expansion
- unit stake calculation
- total stake calculation
- expected payout
- EV
- ROI
- budget constraints
- risk scoring

Parlay logic must not assume exactly one outcome per match. Multiple selections per match must expand into atomic bets, and total stake must be calculated from the number of atomic bets times unit stake.

## Compliance and Safety Boundaries

Do not implement:

- automated betting
- real-money betting placement
- wallet or deposit features
- payment processing
- scraping Bet365 or other sources that prohibit scraping
- guaranteed profit claims
- “sure win” or “must bet” language

Use neutral product language such as:

- probability analysis
- model estimate
- risk level
- expected value estimate
- uncertainty
- backtest result

## Validation Requirements

After each milestone:

- run type checks if configured
- run unit tests
- run linting if configured
- update implementation notes if relevant
- do not expand scope beyond the current milestone

## Output Style

When reporting progress, include:

1. What was implemented
2. Files created
3. Files modified
4. Tests added
5. Tests run
6. Known gaps
7. Next recommended milestone
