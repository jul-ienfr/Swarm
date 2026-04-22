# Météo

Sous-projet dédié à la météo dans `prediction`.

## But

Créer une zone propre pour tout ce qui concerne les marchés météo discrets :

- parsing des marchés température par ville / date / bin
- pricing bin-par-bin à partir de forecasts continus
- branchement futur des providers météo et du routeur d'exécution
- tests dédiés qui évitent de mélanger météo avec le reste du flux généraliste

## Périmètre V1

Implémenté dans :

- `src/lib/prediction-markets/meteo/types.ts`
- `src/lib/prediction-markets/meteo/market-spec.ts`
- `src/lib/prediction-markets/meteo/pricing.ts`
- `src/lib/prediction-markets/meteo/provider-cache.ts`
- `src/lib/prediction-markets/meteo/sources.ts`
- `src/lib/prediction-markets/meteo/orchestrator.ts`
- `src/lib/prediction-markets/meteo/index.ts`
- `src/lib/__tests__/prediction-markets-meteo.test.ts`
- `src/lib/__tests__/prediction-markets-meteo-route.test.ts`

## Décision de structure

On garde `meteo` à l'intérieur du sous-projet `prediction` plutôt que de créer un repo séparé :

- même stack TypeScript/tests
- mêmes conventions d'API et de routing
- réutilisation directe des briques `prediction-markets`
- possibilité de brancher plus tard `service.ts`, `venue-ops.ts` et les routes API sans duplication

## Multi-source gratuit recommandé

### Forecast principal
- **Open-Meteo** : meilleur point d’entrée gratuit, global, simple, multi-modèles

### Source US officielle
- **NWS / NOAA** : prioritaire pour les marchés US et la cohérence avec le terrain américain

### Historique / backtest
- **Meteostat** : utile pour calibration, validation historique et scoring
- l’endpoint JSON documenté passe par `meteostat.p.rapidapi.com`, donc l’intégration ici est **optionnelle** et pilotée par clé API (`METEOSTAT_API_KEY`) quand disponible

### Settlement / vérité terrain
- **Observations officielles** : station / METAR / source de règlement du marché, à distinguer du forecast

## Stratégie V3

La zone `meteo` branche maintenant :

- des fetchers réseau réels pour **Open-Meteo** et **NWS**
- un fetcher **Meteostat historique** optionnel pour calibration / backtest
- un orchestrateur multi-source `buildMeteoForecastPointsFromProviders` / `buildMeteoPricingReportFromProviders`
- une couche de consensus déterministe pondéré
- de la provenance dans le rapport de pricing
- un endpoint dédié `GET /api/v1/prediction-markets/meteo`
- un cache mémoire léger + retry court pour éviter les doubles hits providers

## Endpoint météo

`GET /api/v1/prediction-markets/meteo`

Params principaux :

- `question`
- `latitude`
- `longitude`

Options providers :

- `open_meteo_models=ecmwf,gfs`
- `include_nws=true|false`
- `include_meteostat=true|false`
- `meteostat_start=YYYY-MM-DD`
- `meteostat_end=YYYY-MM-DD`

Options infra :

- `cache_ttl_ms=60000`
- `retry_count=2`

Note : la route lit `METEOSTAT_API_KEY` côté serveur si Meteostat est activé.

## Étapes suivantes naturelles

1. normaliser les règles de settlement par marché Polymarket
2. brancher un scorer EV / edge / stale quote
3. exposer une vue dashboard dédiée météo
4. ajouter observations officielles / METAR comme source de vérité terrain
5. raffiner le cache en LRU/persistant si la charge augmente
