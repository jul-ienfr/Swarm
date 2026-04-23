# prediction_core

Cœur cible de la stack prediction.

## Rôle

`prediction_core/` héberge la nouvelle architecture convergente sans casser `subprojects/prediction`.

- `python/` : research, replay, paper, calibration, analytics, evaluation
- `rust/` : moteur live canonique
- `contracts/` : formats d’échange communs entre moteurs et cockpit

## Statut après stabilisation semaine 1

### Minimum acceptable atteint

- `prediction_core/python` existe comme zone canonique Python avec layout et tests dédiés
- `prediction_core/python` documente désormais un scope Phase 2 explicite : `replay`, `paper`, `calibration`, `analytics`, `evaluation`
- `replay` et `paper` sont cadrés comme extractions canoniques minimales, pas comme migration complète du legacy
- `weather_pm` est absorbé sous `prediction_core/python/src/weather_pm/` pour la convergence Python + Rust sous le même parent
- `prediction_core/rust` est un vrai workspace avec `live_engine`, `pm_types`, `pm_book`, `pm_signal`, `pm_storage`, `pm_risk`, `pm_executor`, `pm_ledger` et `xtask`
- les contrats de layout repo racine + Phase 2 Python sont couverts par tests

### Ce que ce statut veut dire

- `prediction_core/` est maintenant le parent canonique crédible pour Python + Rust
- la trajectoire de migration est posée sans déplacer `subprojects/prediction` ni casser le cockpit existant
- la partie Python est stabilisée côté structure/documentation/tests
- la partie Rust n'est plus un simple placeholder global : le workspace et les crates cœur existent déjà

### Ce qui reste hors du minimum

- migration complète du code legacy `replay.py` / `paper_trading.py`
- unification finale du namespace Python autour de `prediction_core.*`
- branchement live bout-en-bout entre artefacts `prediction_core` et surfaces `subprojects/prediction`
- réduction des bridges/redondances restantes côté runtime principal

## Principe de migration

1. construire ici les composants canoniques
2. produire des artefacts stables (Postgres + JSON)
3. faire consommer ces artefacts par `subprojects/prediction`
4. déclasser progressivement les bridges live redondants
