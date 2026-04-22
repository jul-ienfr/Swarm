# prediction_core/python

Zone Python canonique pour les briques de recherche et d'évaluation autour de `prediction_core`.

## Phase 2 scope for this extraction

Cette extraction prépare la Phase 2 avec deux premières extractions canoniques minimales pour `replay` et `paper`, tout en gardant le focus principal sur les domaines restants.

- `replay` (signature canonique minimale)
- `paper` (simulation canonique minimale)
- `calibration`
- `analytics`
- `evaluation`

Les implémentations legacy de `replay` et `paper` ne sont pas migrées en bloc : seules des briques minimales et stables sont extraites ici pour ancrer le layout Python canonique.

## Principes de cadrage

- on documente les frontières minimales des domaines restants avant tout port de code ;
- on évite d'introduire une API publique prématurée ;
- on garde les chemins de modules stables pour faciliter l'extraction incrémentale future.

## Layout actuel

- `src/prediction_core/replay/` (première extraction canonique : signatures replay)
- `src/prediction_core/paper/` (première extraction canonique : simulation paper)
- `src/prediction_core/calibration/`
- `src/prediction_core/analytics/`
- `src/prediction_core/evaluation/`
- `docs/reuse-map.md`

Cette zone réutilisera progressivement le Python utile déjà présent dans l’écosystème existant, domaine par domaine, avec TDD ciblé.