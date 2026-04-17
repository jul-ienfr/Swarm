# Prediction Memory

Ce document est la memoire canonique du sous-projet `prediction`.

Il capture :

- la doctrine stable du sous-projet
- la logique de reutilisation externe
- les couches de preuve et de promotion
- les decisions deja prises sur les sources externes
- l'univers de sources a surveiller ou a integrer

Le fichier de travail `/home/jul/plan-prediction-markets.md` reste une source d'import et de normalisation, mais la memoire canonique vit desormais dans le repo.

## Etat d'implementation runtime

Les decisions de cette memoire ne sont plus seulement documentaires.

Une premiere couche runtime conversation-scoped est maintenant en place dans :

- `src/lib/prediction-markets/external-source-profiles.ts` pour le registre canonique des profils externes, batches, modes, roles et cibles locales
- `src/lib/prediction-markets/source-audit.ts` pour l'association source -> profils externes -> batches -> geo refs
- `src/lib/prediction-markets/research.ts` et `research-pipeline-trace.ts` pour la provenance des profils externes dans `EvidencePacket`, `ResearchReport` et le trace
- `src/lib/prediction-markets/world-state.ts` pour `external_integration` et `geo_context`
- `src/lib/prediction-markets/dashboard-models.ts` pour la surface read-only `external_integrations`
- `src/lib/prediction-markets/polymarket.ts`, `venue-ops.ts` et les snapshots dashboard de venue pour exposer le lineage runtime `P0-A` des adapters officiels et des sidecars operateur optionnels
- `src/lib/prediction-markets/geomapdata-cn.ts` et `data/geomapdata-cn-provinces.json` pour un import amincie de `GeoMapData_CN`
- `src/lib/prediction-markets/external-runtime.ts` pour les resumes runtime additives par batch `P0-A` a `P2-C`
- `src/lib/prediction-markets/polymarket-operator-sidecars.ts` pour les sidecars operateur `P0-A` effectivement exposes comme surface read-only
- `src/lib/prediction-markets/research-adapters.ts` pour les adapters read-only `P1-A` normalisant `WorldOSINT`, `worldmonitor.app`, `Hack23/cia` et `open-civic-datasets`
- `src/lib/prediction-markets/forecast-governance.ts`, `cop-read-models.ts` et `watchlist-audit.ts` pour materialiser `P1-B`, `P1-C`, `P2-B` et `P2-C` comme artefacts runtime additifs

Cette couche respecte les contraintes stables :

- pas de nouvelle route canonique
- pas de nouvelle voie `live`
- `execution_projection` reste la porte unique de promotion runtime
- les profils `pattern-only` et `watchlist-diff-only` restent non canoniques et read-only

Le batch `P0-A` a maintenant une presence runtime plus concrete mais toujours additive :

- `getPolymarketVenueP0ALineageStatus()` expose le lineage officiel `clob-client` / `py-clob-client`, les sidecars optionnels `tremor` et MCP, et le rappel explicite que `execution_projection` reste la gate canonique
- `getVenueCapabilitiesContract('polymarket')`, `getVenueHealthSnapshotContract('polymarket')` et `getVenueFeedSurfaceContract('polymarket')` embarquent ces metadonnees dans `metadata.p0_a_lineage`
- les sidecars restent facultatifs, read-only ou operator-bound, et leur absence degrade proprement sans casser la surface de venue
- `research.ts` expose maintenant un resume runtime `P1-A/P2-B/P2-C` dans `retrieval_summary.external_runtime`, plus des facteurs/no-trade hints additives pour la gouvernance des sources
- `execution-pathways.ts`, `walk-forward.ts` et `autopilot-cycle.ts` exposent maintenant un resume additif `P1-B` pour la gouvernance benchmark/dissent, sans ouvrir de voie canonique parallele
- `world-state.ts` et `dashboard-models.ts` exposent maintenant des resumes read-only `P1-C` / `P2-*` pour rendre les patterns dashboard/COP et watchlists visibles en prod
- `dashboard-control.ts` embarque maintenant la surface sidecar operateur Polymarket dans les evenements de live intent, toujours en read-only
- `source-audit.ts` embarque maintenant un `watchlist_audit` explicite pour `P2-B/P2-C`
- `contract-examples.ts` expose maintenant des exemples read-only d'integration externe hors des contrats canoniques parsees strictement

## Doctrine canonique

### `quality-first`

La politique de sourcing est `quality-first`.

Cela signifie :

- on ouvre largement l'acquisition de sources externes
- on n'ecarte pas une source juste parce qu'elle est mal packagee, peu elegante, ou juridiquement confuse au premier regard
- on juge une source a sa densite technique extractible et a son uplift local mesurable
- rien ne devient canonique sans validation locale

Formule operative :

- `source acquisition = large`
- `canonization = ultra-strict`

### `copy-paste-first`

Quand un delta externe est reellement utile, la priorite est :

1. extraire le chemin de code ou de donnees concret
2. bench localement le delta
3. promouvoir en `import` ou `adapt` seulement si le gain est mesurable

En pratique :

- on prefere les chemins copiables concrets aux repos trop abstraits
- on garde `wrap` ou `pattern-only` quand le code est trop couple
- on reserve `watchlist-diff-only` aux forks ou repos ambigus tant qu'aucun delta utile n'est prouve

### `advisor-first` et `preflight-first`

Le sous-projet reste :

- `advisor-first` tant qu'un edge robuste n'est pas prouve
- `preflight-first` pour `dispatch/paper/shadow/live`

La presence d'une bonne source de recherche n'autorise jamais une promotion `live`.

## Proof chain et couches de verite

La proof chain canonique reste :

`predictive edge -> executable edge -> capturable edge -> durable edge`

Les couches de verite a ne pas melanger sont :

- `discovery` : detection, alerting, triage, veille
- `evidence` : sources sous-jacentes, resolution, pieces verifiables
- `pricing/execution` : venues directes, orderbooks, fills, couts, friction

Regle simple :

- les agregateurs et dashboards servent surtout `discovery`
- les sources primaires et autorites de resolution servent `evidence`
- les clients de venue et donnees de marche directes servent `pricing/execution`

## Taxonomie des roles

Roles de source au niveau `prediction` :

- `execution` : contribue directement a l'execution, aux fills, aux couts ou a la reconciliation
- `reference` : sert de verite secondaire ou de benchmark
- `signal` : enrichit la recherche, le triage ou la detection d'evenements
- `comparison` : sert aux contre-factuels, au calibration lab, ou aux comparaisons de pipelines
- `watchlist` : source a surveiller sans promotion immediate

## Modes de reutilisation

- `import` : copier/coller ou importer directement une brique concrete
- `adapt` : reprendre une brique concrete avec adaptation locale
- `wrap` : garder le composant a la frontiere et l'appeler comme sidecar
- `pattern-only` : reprendre le pattern, pas le code
- `watchlist-diff-only` : n'extraire qu'un delta de code prouve contre un upstream
- `skip` : ne pas investir plus de temps a ce stade

## Regle de promotion canonique

Une source externe ne devient jamais canonique juste parce qu'elle semble bonne.

Promotion minimale requise :

- benchmark hook explicite
- compatibilite avec `execution_projection` et les contrats runtime du sous-projet
- absence de regression sur les surfaces `paper/shadow/live`
- uplift mesurable sur une cible locale precise

## Registre des decisions deja prises

Perimetre de ce registre :

- uniquement les repos et sources explicitement vus dans cette conversation
- y compris le sweep `projets similaires`
- hors candidats historiques non rediscutes du plan externe

### Execution et outillage venue

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Polymarket/clob-client` | `execution` | `polymarket.ts`, `venue-ops.ts`, `cross-venue.ts`, `execution-preview.ts` | `adapt` | `P0` | parite venue, readback orderbook, robustesse des appels | `seed retained` | client officiel a adapter sur les adapters de venue, sans changer la surface canonique |
| `Polymarket/py-clob-client` | `execution` | `polymarket.ts`, `live-execution-bridge.ts`, `execution-pathways.ts` | `adapt` | `P0` | relecture des ordres, parite paper/shadow/live, hygiene transport | `seed retained` | reference Python utile pour transport et validation croisee, pas coeur runtime autonome |
| `sculptdotfun/tremor` | `signal` + `execution` | `dashboard-events.ts`, `dashboard-read-models.ts`, `source-audit.ts` | `wrap` | `P0` | delai de detection, bruit versus alertes utiles, readback operateur | `seed retained` | bon sidecar d'alerting, jamais source canonique de pricing |
| `pab1it0/polymarket-mcp` | `signal` + `watchlist` | outillage operateur read-only autour de `dashboard-control.ts`, `source-audit.ts` | `wrap` | `P0` | baisse de friction operateur pour inspecter market, event, orderbook, trades | `seed retained` | utile comme outillage facultatif, jamais comme coeur runtime |
| `guangxiangdebizi/PolyMarket-MCP` | `signal` + `watchlist` | outillage operateur read-only autour de `dashboard-control.ts`, `source-audit.ts` | `wrap` | `P0` | meilleure inspection positions, activity, holders, analytics | `seed retained` | utile comme boite a outils operateur, jamais comme source canonique |

### Research, discovery et triage

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `WorldOSINT` | `signal` | `research.ts`, `research-pipeline-trace.ts`, `source-audit.ts`, `EvidencePacket` | `wrap` | `P1` | recall d'evenements, `date_confidence`, qualite de triage | `seed retained` | utile en amont de la recherche, jamais comme preuve finale d'edge ou d'execution |
| `worldmonitor.app` | `signal` | `research.ts`, `research-compaction.ts`, `source-audit.ts` | `wrap` | `P1` | baisse du temps de detection et meilleure convergence multi-sources | `reviewed` | agregateur utile de discovery, pas source canonique de preuve |
| `Hack23/cia` | `signal` + `reference` | `research.ts`, `research-pipeline-trace.ts`, `dashboard-read-models.ts` | `wrap` | `P1` | meilleure couverture civic/political intelligence et qualite de contexte | `seed retained` | utile en enrichissement recherche, pas comme gate `live` |
| `codeforamerica/open-civic-datasets` | `reference` | `research.ts`, `world-state-spine.ts`, `source-audit.ts` | `wrap` | `P1` | nouvelles evidences publiques verifiables, meilleure jointure civic -> contrat | `seed retained` | datasets utiles comme evidence secondaire, jamais coeur execution |
| `koala73/worldmonitor` | `signal` + `reference` | `research-compaction.ts`, `dashboard-read-models.ts`, `dashboard-events.ts` | `pattern-only` | `P1` | alerting, freshness, clustering, ergonomie dashboard | `reviewed` | baseline amont de la famille `worldmonitor`; reprendre surtout les patterns |
| `nativ3ai/hermes-geopolitical-market-sim` | `signal` + `watchlist` | `research.ts`, `research-pipeline-trace.ts`, `operator_thesis` | `pattern-only` | `P1` | uplift sur seed packets, topic tracking, orchestration recherche | `reviewed` | bon repo d'inspiration recherche, mauvaise base pour le coeur trading |

### Simulation, contre-factuels et gouvernance forecast

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MiroFish` | `comparison` + `signal` | `research.ts`, `research-pipeline-trace.ts`, `execution-pathways.ts` | `wrap` | `P1` | meilleure couverture des hypotheses, objections et scenarios alternatifs | `seed retained` | utile pour simulation et contre-scenarios, pas comme gate canonique |
| `views-platform` | `comparison` + `reference` | `calibration.ts`, `walk-forward.ts`, `benchmark.ts`, `autopilot-cycle.ts` | `adapt` | `P1` | meilleur harness hors echantillon et gouvernance des experiments | `seed retained` | source serieuse de patterns forecast et evaluation |
| `prio-data/views_pipeline` | `comparison` + `reference` | `calibration.ts`, `walk-forward.ts`, `benchmark.ts`, `autopilot-cycle.ts` | `adapt` | `P1` | auditabilite des pipelines, robustesse des experiments, discipline d'evaluation | `seed retained` | complement naturel de `views-platform` pour pipeline et gouvernance |
| `openpredictionmarkets/socialpredict` | `comparison` | `contract-examples.ts`, `dashboard-models.ts`, `operator-analytics.ts` | `pattern-only` | `P1` | utilite reelle pour economics produit et structure de marche | `seed retained` | source d'idees produit et economics, pas une brique de coeur runtime |
| `captbullett65/MSCFT` | `comparison` | `operator_thesis`, `research-pipeline-trace.ts`, `ticket-payload.ts` | `pattern-only` | `P1` | meilleure hygiene de cadrage forecast, objections et traces d'argument | `seed retained` | utile pour discipline de these et audit, pas pour execution |

### Dashboards, COP et triage operateur

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MISP/misp-dashboard` | `signal` + `comparison` | `dashboard-models.ts`, `dashboard-read-models.ts`, `dashboard-events.ts` | `pattern-only` | `P1` | meilleure densite d'information operateur sans surcharge | `seed retained` | bon pattern de flux live et alerting, strictement read-only |
| `dfpc-coe/CloudTAK` | `signal` | `dashboard-read-models.ts`, `world-state-spine.ts`, `dashboard-events.ts` | `pattern-only` | `P1` | meilleurs patterns carte + couches temps reel + triage | `seed retained` | pattern COP utile, jamais second dashboard canonique |
| `FreeTAKTeam/FreeTakServer` | `signal` | `dashboard-read-models.ts`, `world-state-spine.ts`, `dashboard-events.ts` | `pattern-only` | `P1` | meilleurs patterns de diffusion d'evenements et overlays geo | `seed retained` | read-only et pattern-only uniquement |
| `Esri/dynamic-situational-awareness-qt` | `signal` | `dashboard-models.ts`, `world-state-spine.ts`, `dashboard-read-models.ts` | `pattern-only` | `P1` | workflows carte + couches + alertes lisibles | `seed retained` | source de patterns d'interface et de triage |
| `CityPulse/CityPulse-City-Dashboard` | `signal` | `dashboard-read-models.ts`, `dashboard-events.ts`, `world-state.ts` | `pattern-only` | `P1` | bonnes vues compactes real-time + historic + correlation streams | `seed retained` | pattern utile pour vues locales, pas pour execution |
| `meteocool/core` | `signal` | `dashboard-read-models.ts`, `world-state.ts`, `source-audit.ts` | `pattern-only` | `P1` | meilleure lisibilite des signaux meteo et d'alertes cartographiques | `seed retained` | pattern meteo/carto utile en enrichissement seulement |
| `OdinMB/city-monitor` | `signal` | `dashboard-read-models.ts`, `world-state.ts`, `source-audit.ts` | `pattern-only` | `P2` | uplift sur signaux locaux et vues compactes de situation | `reviewed` | utile pour patterns hyper-locaux, faible pertinence directe execution |

### Geo enrichment et source discovery

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `lyhmyd1211/GeoMapData_CN` | `reference` | `world-state.ts`, `world-state-spine.ts`, `source-audit.ts` | `import` | `P2` | meilleure resolution geo et enrichissement cartographique des evidences | `data asset ready` | bon asset de donnees, pas une source de logique |
| `doctorfree/osint` | `watchlist` | backlog source discovery et `source-audit.ts` | `wrap` | `P2` | nouvelles sources utiles integrees sans diluer la qualite | `seed retained` | source de veille, aucune dependance runtime |
| `ARPSyndicate/awesome-intelligence` | `watchlist` | backlog source discovery et `source-audit.ts` | `wrap` | `P2` | elargissement continu du funnel de sources a qualifier | `seed retained` | source de veille, aucune dependance runtime |

### Watchlist `diff-only`

| Source | Role | Cible locale | Mode | Priorite | Benchmark hook | Statut | Decision stable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sjkncs/worldmonitor` | `comparison` + `watchlist` | cross-validation exogene dans `research.ts` | `watchlist-diff-only` | `P2` | uplift prouve sur validation croisee CII versus marche | `fork-diff pending` | ne rien reprendre sans isoler un vrai delta contre `koala73/worldmonitor` |
| `sjkncs/worldmonitor-enhanced` | `watchlist` | aucune cible canonique tant que l'audit n'est pas fait | `watchlist-diff-only` | `P2` | claims de prediction et backtest a valider localement | `claims-only` | ne pas croire les claims sans audit code serieux |
| `worldmonitor/worldmonitor` | `watchlist` | diff opportuniste versus `koala73/worldmonitor` | `watchlist-diff-only` | `P2` | tout delta doit survivre a un bench local contre l'upstream | `low-density diff only` | faible densite technique observable ; surveiller seulement les deltas reels |

Le plan d'integration canonique pour ces sources conversation-scoped vit dans [prediction-integration-plan.md](./prediction-integration-plan.md).

## Rappels de gouvernance

- une source `research` n'est jamais une preuve finale d'edge
- une these operateur n'est jamais une promotion `live`
- `approval_ticket`, `operator_thesis` et `research_pipeline_trace` restent des compagnons utiles, pas la source canonique de verite runtime
- `execution_projection` reste la porte unique `paper/shadow/live`
- `no trade` reste un bon resultat si aucun edge robuste n'existe
