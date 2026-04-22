# Sport

Sous-projet thématique rattaché à `prediction`, dédié exclusivement aux marchés **sport**.

## Mission

Créer un espace canonique pour isoler les workflows, read-models, recherches et logiques d'exécution orientés sport sans mélanger ce scope avec les marchés crypto, politiques ou météo.

## Scope initial

- venues : `Polymarket`, `Kalshi`
- sports de départ : `football`, `basketball`, `tennis`, `combat`
- ligues/circuits initiaux :
  - `soccer-top-flight`
  - `nba`
  - `atp-wta`
  - `ufc-boxing`
- familles de marchés ciblées :
  - `moneyline and yes-no`
  - `totals and player thresholds`
  - `spread and handicap`
  - `live microstructure dislocations`
  - `cross-market match clusters`

## Hors scope initial

- politique
- crypto
- culture
- météo
- marchés généralistes non-sport

## Entrées de code créées

- `src/lib/prediction-markets/sport/index.ts`
- `src/lib/prediction-markets/sport/types.ts`
- `src/lib/prediction-markets/sport/market-spec.ts`
- `src/lib/prediction-markets/sport/manifest.ts`
- `src/lib/prediction-markets/sport/universe.ts`

## Taxonomie stratégique WS1

Le sous-projet `Sport` ne se limite plus au scaffold minimum. Il expose maintenant une taxonomie typed et déterministe pour encoder une opportunité sport selon une logique proche de l'analyse RN1.

### Strategic families

- `event-cluster-trading`
- `middle-tail-price-hunting`
- `totals-and-tempo-mapping`
- `live-microstructure-reversion`
- `cross-venue-relative-value`

### Trading horizons

- `pre-match`
- `same-day`
- `live-window`

### Signal classes

- `cross-market-incoherence`
- `price-zone-discipline`
- `tempo-and-game-state`
- `order-book-fragmentation`
- `venue-dislocation`

### Risk buckets

- `price-discipline`
- `liquidity-fragility`
- `late-chasing`
- `scenario-overfit`
- `headline-reflex`

## Playbooks seedés

Le package fournit maintenant des playbooks typed pour brancher un futur dashboard/screener sport :

- `rn1-football-cluster-map`
- `nba-tempo-cluster-board`
- `tennis-middle-tail-pricing`
- `combat-live-dislocation-watch`

Le premier playbook encode explicitement le workflow **RN1-like** discuté : partir du match, vérifier l'incohérence winner/spread/total, forcer un angle `price > storytelling`, puis construire le trade en tranches.

## Scorecard RN1-like

Le module `sport/scorecard.ts` expose désormais une grille déterministe de **13 critères / 28 points** pour évaluer si un spot est vraiment `RN1-like` :

- marchés multiples disponibles
- cluster exploitable
- plusieurs angles cohérents
- zone de prix intéressante
- prix > storytelling
- incohérence inter-marchés
- scénario plausible
- pattern répétable
- liquidité correcte
- scaling possible
- timing encore bon
- thèse écrivable
- plan de trade clair

Helper exporté :

- `evaluatePredictionSportSpot(input)`

Lecture du score :

- `22+` → `very-rn1-like`
- `15-21` → `selective-rn1-like`
- `<15` → `not-rn1-like`

## Intention d'architecture

Le sous-projet `Sport` devient donc une base canonique pour :

1. nom canonique stable,
2. périmètre clair,
3. univers sport/ligues/venues initial,
4. taxonomie stratégique typed,
5. playbooks seedés orientés sport,
6. scorecard RN1-like réutilisable pour dashboard, screener ou read-model.

Les prochaines briques naturelles restent :

- research adapters sport dédiés,
- dashboards séparés du flux prediction général,
- modèles de pricing/monitoring spécialisés par ligue et type de marché,
- branchement du scorecard sur des read-models live et sur un futur screener sport.
