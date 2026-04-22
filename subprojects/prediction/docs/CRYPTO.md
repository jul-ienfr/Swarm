# CRYPTO

Sous-projet thématique rattaché à `prediction`, dédié exclusivement aux marchés **crypto**.

## Mission

Créer un espace canonique pour isoler les workflows, read-models, recherches et logiques d'exécution orientés crypto sans mélanger ce scope avec les marchés politiques, sports ou culturels.

## Scope canonique

- venues : `Polymarket`, `Kalshi`
- actifs de départ : `BTC`, `ETH`, `SOL`, `XRP`, `HYPE`
- familles de marchés ciblées :
  - `short-horizon up-down`
  - `date-bounded price targets`
  - `range buckets`
  - `expiry-harvest`
  - `cross-venue crypto dislocations`

## Taxonomie stratégique WS1

Le scaffold CRYPTO expose maintenant une taxonomie typed et déterministe pour décrire un marché, un playbook ou un seed d'opportunité.

### Strategic families

- `directional-momentum`
- `volatility-and-range`
- `event-driven-catalyst`
- `relative-value-and-dislocation`
- `carry-and-structure`

### Trading horizons

- `intraday`
- `multi-day`
- `event-window`
- `monthly-expiry`

### Signal classes

- `price-action`
- `volatility-regime`
- `basis-and-spread`
- `flow-and-positioning`
- `catalyst-and-governance`

### Execution styles

- `manual-discretionary`
- `semi-systematic`
- `systematic-monitoring`

### Risk buckets

- `defined-risk`
- `convex-long-vol`
- `carry-harvest`
- `basis-risk`
- `headline-risk`

## Archetype descriptors

Chaque `market_archetype` est relié à un descriptor déterministe :

- famille stratégique principale,
- horizon principal,
- classe de signal dominante,
- style d'exécution attendu,
- bucket de risque,
- résumé opératoire.

Exemples :

- `date-bounded price targets` → `event-driven-catalyst` + `monthly-expiry` + `headline-risk`
- `range buckets` → `volatility-and-range` + `multi-day` + `convex-long-vol`
- `cross-venue crypto dislocations` → `relative-value-and-dislocation` + `event-window` + `basis-risk`

## Playbooks seedés

Le package fournit aussi des playbooks typed et exportés pour servir de base aux futures couches de screener/read-model :

- `btc-strike-catalyst-ladder`
- `sol-vol-regime-buckets`
- `cross-venue-dislocation-watch`
- `expiry-structure-harvest`

Chaque playbook définit :

- `strategic_family`
- `primary_horizon`
- `signal_classes`
- `execution_style`
- `execution_profile`
- `risk_bucket`
- `preferred_venues`
- `focus_assets`
- `archetypes`
- `thesis`
- `operator_focus`
- `tags`

## Helpers exportés

Le module CRYPTO expose maintenant des guards et helpers pour garder les usages stables côté TypeScript :

- guards de venue / asset / archetype / family / horizon / signal / execution / risk
- `getPredictionCryptoArchetypeDescriptor(archetype)`
- `getPredictionCryptoPlaybookById(id)`
- `listPredictionCryptoPlaybooksForAsset(asset)`
- `listPredictionCryptoMarketSeedsByFamily(family)`

## Hors scope initial

- politique
- sports
- culture
- météo
- marchés généralistes non-crypto

## Entrées de code

- `src/lib/prediction-markets/crypto/index.ts`
- `src/lib/prediction-markets/crypto/types.ts`
- `src/lib/prediction-markets/crypto/market-spec.ts`
- `src/lib/prediction-markets/crypto/manifest.ts`
- `src/lib/prediction-markets/crypto/universe.ts`

## Intention d'architecture

Le sous-projet `CRYPTO` reste un package dédié, mais il ne se limite plus à un simple scaffold de nommage. Il fournit désormais :

1. un univers de marchés crypto stable,
2. une taxonomie stratégique réutilisable,
3. des descriptors d'archetypes déterministes,
4. des playbooks seedés pour brancher un screener ou un dashboard,
5. des helpers/guards typed pour éviter les conventions implicites.
