# Prediction Integration Plan

Ce document est le plan canonique d'integration des repos vus dans cette conversation pour `subprojects/prediction`.

Perimetre :

- uniquement les repos et sources explicitement vus dans cette conversation
- y compris le sweep `projets similaires`
- hors candidats historiques du plan externe qui n'ont pas ete rediscutes ici

Objectif :

- integrer tout ce qui peut augmenter la qualite du projet `prediction`
- sans casser `quality-first`, `advisor-first`, `preflight-first`
- sans ouvrir un nouveau flux canonique parallele aux contrats existants

## Etat d'avancement implemente

Une fondation runtime commune a deja ete livree :

- registre conversation-scoped des profils externes dans `src/lib/prediction-markets/external-source-profiles.ts`
- branchement `research -> source-audit -> world-state -> dashboard` via metadonnees additives
- import amincie de `lyhmyd1211/GeoMapData_CN` pour la couche geo Chine
- lineage `P0/P1/P2` expose en read-only sans ouvrir de nouveau flux canonique
- metadata runtime additives `P0-A` exposees dans les contrats de venue/feed/health Polymarket et visibles depuis les snapshots dashboard
- resumes runtime additives par batch dans `src/lib/prediction-markets/external-runtime.ts`
- gouvernance additive `P1-B` exposee dans `execution-pathways.ts`, `walk-forward.ts` et `autopilot-cycle.ts`
- resumes read-only `P1-C/P2-*` exposes dans `world-state.ts` et `dashboard-models.ts`
- surfaces fonctionnelles read-only dans `polymarket-operator-sidecars.ts`, `research-adapters.ts`, `forecast-governance.ts`, `cop-read-models.ts` et `watchlist-audit.ts`

Cela signifie que les batches ci-dessous ne sont plus de simples intentions documentaires :

- `P0-A` : lineage venue et sidecars read-only expose dans les surfaces Polymarket
- `P1-A` : profils externes detectes et traces dans la recherche et le `source_audit`
- `P1-B` : resume de gouvernance forecast/dissent expose en runtime sans voie canonique parallele
- `P1-C` : surface dashboard read-only pour les integrations externes
- `P2-A` : `geo_context` Chine branche sur `world_state`
- `P2-B/P2-C` : watchlists et backlog de veille captures comme profils runtime non canoniques

## Contraintes stables

- aucune nouvelle route canonique n'est requise en `v1`
- toute source `research` doit se normaliser via `EvidencePacket`, `ResearchReport`, `research-pipeline-trace` et, si utile, `operator_thesis`
- toute source `execution` doit se brancher sur les modules existants `polymarket.ts`, `cross-venue.ts`, `execution-path.ts`, `execution-pathways.ts`, `execution-preview.ts`, `calibration.ts`, `walk-forward.ts` et `microstructure-lab.ts`
- tous les patterns dashboard/COP restent read-only et se branchent sur `dashboard-models.ts`, `dashboard-read-models.ts`, `dashboard-events.ts` et `dashboard-live-intents.ts`
- tous les enrichissements geo/civic restent optionnels et ne deviennent jamais une gate directe de promotion `live`

## Matrice conversation-scoped

| Batch | Source | Cibles locales concretes | Mode | Uplift attendu | Benchmark hook | Statut |
| --- | --- | --- | --- | --- | --- | --- |
| `P0-A` | `Polymarket/clob-client` | `polymarket.ts`, `venue-ops.ts`, `cross-venue.ts`, `execution-preview.ts` | `adapt` | meilleur adapter de venue, meilleure lecture orderbook, meilleure hygiene ordre/readback | parite venue, robustesse des appels, couverture des ordres | `seed retained` |
| `P0-A` | `Polymarket/py-clob-client` | `polymarket.ts`, `live-execution-bridge.ts`, `execution-pathways.ts` | `adapt` | meilleure validation croisee transport Python, paper/shadow/live plus coherents | relecture des ordres, hygiene transport, parite des previews | `seed retained` |
| `P0-A` | `sculptdotfun/tremor` | `dashboard-events.ts`, `dashboard-read-models.ts`, `source-audit.ts` | `wrap` | meilleur alerting operateur sur mouvements Polymarket | delai de detection, bruit versus alertes utiles | `seed retained` |
| `P0-A` | `pab1it0/polymarket-mcp` | wrappers operateur hors coeur autour de `dashboard-control.ts`, `source-audit.ts` | `wrap` | moins de friction pour inspecter markets, orderbooks, trades, history | gain operateur sans couplage runtime | `seed retained` |
| `P0-A` | `guangxiangdebizi/PolyMarket-MCP` | wrappers operateur hors coeur autour de `dashboard-control.ts`, `source-audit.ts` | `wrap` | meilleure inspection positions, holders, analytics | gain operateur sans second flux canonique | `seed retained` |
| `P1-A` | `WorldOSINT` | `research.ts`, `research-pipeline-trace.ts`, `source-audit.ts` | `wrap` | meilleur recall d'evenements et meilleur triage | recall, `date_confidence`, qualite de triage | `seed retained` |
| `P1-A` | `worldmonitor.app` | `research.ts`, `research-compaction.ts`, `source-audit.ts` | `wrap` | meilleure convergence multi-sources et detection rapide | temps de detection, taux de convergence utile | `reviewed` |
| `P1-A` | `Hack23/cia` | `research.ts`, `research-pipeline-trace.ts`, `dashboard-read-models.ts` | `wrap` | meilleur contexte civic/political intelligence | qualite de contexte, recall contextualise | `seed retained` |
| `P1-A` | `codeforamerica/open-civic-datasets` | `research.ts`, `world-state-spine.ts`, `source-audit.ts` | `wrap` | meilleures evidences publiques verifiables | nouvelles evidences utiles par contrat | `seed retained` |
| `P1-A` | `koala73/worldmonitor` | `research-compaction.ts`, `dashboard-read-models.ts`, `dashboard-events.ts` | `pattern-only` | meilleurs patterns de freshness, clustering, alerting et UX operateur | meilleure densite de triage sans second dashboard canonique | `reviewed` |
| `P1-A` | `nativ3ai/hermes-geopolitical-market-sim` | `research.ts`, `research-pipeline-trace.ts`, `operator_thesis` | `pattern-only` | meilleurs seed packets, topic tracking et orchestration recherche | meilleure preparation d'un `ResearchReport` operateur | `reviewed` |
| `P1-B` | `MiroFish` | `research.ts`, `research-pipeline-trace.ts`, `execution-pathways.ts` | `wrap` | meilleur dissent et meilleurs contre-scenarios | qualite des objections, baisse des theses univoques | `seed retained` |
| `P1-B` | `views-platform` | `calibration.ts`, `walk-forward.ts`, `benchmark.ts`, `autopilot-cycle.ts` | `adapt` | meilleure gouvernance des experiments et evaluation forecast | meilleur harness hors echantillon | `seed retained` |
| `P1-B` | `prio-data/views_pipeline` | `calibration.ts`, `walk-forward.ts`, `benchmark.ts`, `autopilot-cycle.ts` | `adapt` | meilleure auditabilite des pipelines et discipline de benchmark | robustesse des experiments et tracabilite | `seed retained` |
| `P1-B` | `openpredictionmarkets/socialpredict` | `contract-examples.ts`, `dashboard-models.ts`, `operator-analytics.ts` | `pattern-only` | meilleures idees produit et economics de marche | utilite reelle sur contracts et surfaces operateur | `seed retained` |
| `P1-B` | `captbullett65/MSCFT` | `operator_thesis`, `research-pipeline-trace.ts`, `ticket-payload.ts` | `pattern-only` | meilleure hygiene de these forecast et audit d'arguments | qualite de these, objections, lineage de decision | `seed retained` |
| `P1-C` | `MISP/misp-dashboard` | `dashboard-models.ts`, `dashboard-read-models.ts`, `dashboard-events.ts` | `pattern-only` | meilleurs patterns d'alerting et denses read models | meilleure lisibilite operateur sans surcharge | `seed retained` |
| `P1-C` | `dfpc-coe/CloudTAK` | `dashboard-read-models.ts`, `world-state-spine.ts`, `dashboard-events.ts` | `pattern-only` | meilleurs patterns carte + couches temps reel | meilleure ergonomie COP en lecture seule | `seed retained` |
| `P1-C` | `FreeTAKTeam/FreeTakServer` | `dashboard-read-models.ts`, `world-state-spine.ts`, `dashboard-events.ts` | `pattern-only` | meilleurs patterns de diffusion d'evenements geo | meilleure lecture d'overlays et d'alertes | `seed retained` |
| `P1-C` | `Esri/dynamic-situational-awareness-qt` | `dashboard-models.ts`, `world-state-spine.ts`, `dashboard-read-models.ts` | `pattern-only` | meilleurs workflows carte/couches/alertes | meilleure lisibilite de situation room | `seed retained` |
| `P1-C` | `CityPulse/CityPulse-City-Dashboard` | `dashboard-read-models.ts`, `dashboard-events.ts`, `world-state.ts` | `pattern-only` | meilleures vues compactes temps reel + historique | meilleure valeur de triage local | `seed retained` |
| `P1-C` | `meteocool/core` | `dashboard-read-models.ts`, `world-state.ts`, `source-audit.ts` | `pattern-only` | meilleurs overlays meteo/carto | meilleure lecture des signaux meteo | `seed retained` |
| `P1-C` | `OdinMB/city-monitor` | `dashboard-read-models.ts`, `world-state.ts`, `source-audit.ts` | `pattern-only` | meilleurs patterns hyper-locaux | meilleure valeur sur contrats localises | `reviewed` |
| `P2-A` | `lyhmyd1211/GeoMapData_CN` | `world-state.ts`, `world-state-spine.ts`, `source-audit.ts` | `import` | geo-layer Chine, admin codes, centroids, choropleths | precision geo et meilleure jointure entite -> region | `data asset ready` |
| `P2-B` | `sjkncs/worldmonitor` | audit diff contre `koala73/worldmonitor`, puis eventuel branchement `research.ts` | `watchlist-diff-only` | extraire un vrai delta utile sur cross-validation exogene | bench local versus upstream uniquement | `fork-diff pending` |
| `P2-B` | `sjkncs/worldmonitor-enhanced` | audit diff contre `koala73/worldmonitor` seulement | `watchlist-diff-only` | verifier si un quelconque delta prediction/backtest est reel | aucun avant audit local strict | `claims-only` |
| `P2-B` | `worldmonitor/worldmonitor` | audit diff contre `koala73/worldmonitor` seulement | `watchlist-diff-only` | verifier si un delta exploitable existe reellement | aucun import sans gain prouve contre upstream | `low-density diff only` |
| `P2-C` | `doctorfree/osint` | backlog qualifie de source discovery autour de `source-audit.ts` | `wrap` | elargissement continu du funnel de nouvelles sources | nouvelles sources utiles integrees sans diluer la qualite | `seed retained` |
| `P2-C` | `ARPSyndicate/awesome-intelligence` | backlog qualifie de source discovery autour de `source-audit.ts` | `wrap` | elargissement continu du funnel de nouvelles sources | nouvelles sources utiles integrees sans diluer la qualite | `seed retained` |

## Batches d'integration

### `P0-A` verite marche et tooling venue

Sources :

- `Polymarket/clob-client`
- `Polymarket/py-clob-client`
- `sculptdotfun/tremor`
- `pab1it0/polymarket-mcp`
- `guangxiangdebizi/PolyMarket-MCP`

Intentions d'integration :

- renforcer les adapters de venue existants sans changer la surface canonique
- enrichir le readback ordre/orderbook et l'alerting operateur
- garder les MCP Polymarket comme wrappers facultatifs, hors coeur runtime

Validation :

- `execution_projection` reste la source canonique
- l'absence des sidecars n'est jamais bloquante
- l'alerting apporte un gain mesurable sur latence de detection ou confort operateur

Etat runtime livre a ce stade :

- surface additive `metadata.p0_a_lineage` dans `capabilities`, `health` et `feed` pour `polymarket`
- exposition explicite des references `Polymarket/clob-client` et `Polymarket/py-clob-client`
- exposition read-only des sidecars optionnels `tremor`, `pab1it0/polymarket-mcp` et `guangxiangdebizi/PolyMarket-MCP`
- verification testee que l'absence des sidecars ne casse pas la surface, et qu'une configuration operateur les rend visibles sans changer la porte canonique
- resume runtime `P0-A` additionnel dans `getPolymarketVenueP0ALineageStatus().runtime_summary`
- surface read-only concrete `getPolymarketOperatorSidecarSurface()` pour wrappers operateur et readback parity

Reste a faire pour fermer reellement `P0-A` :

- brancher un readback ordre/orderbook plus explicite sur les adapters de venue
- mesurer localement l'uplift operateur de l'alerting `tremor`
- outiller les wrappers MCP comme sidecars hors coeur runtime plutot que simple lineage expose

### `P1-A` research discovery et triage

Sources :

- `WorldOSINT`
- `worldmonitor.app`
- `Hack23/cia`
- `codeforamerica/open-civic-datasets`
- `koala73/worldmonitor`
- `nativ3ai/hermes-geopolitical-market-sim`

Intentions d'integration :

- normaliser tout enrichissement en `EvidencePacket`, `ResearchReport` et `research_pipeline_trace`
- utiliser les agregateurs et dashboards uniquement comme discovery, convergence et triage
- reprendre seulement les patterns de `koala73/worldmonitor` et `PrediHermes`, pas leur coeur comme moteur canonique

Validation :

- hausse de recall, `date_confidence`, clustering ou qualite de `ResearchReport`
- aucune source `research` ne promeut `live` a elle seule
- absence degradee proprement si `operator_thesis` ou `research_pipeline_trace` sont absents

Etat runtime livre a ce stade :

- `research.ts` expose maintenant `retrieval_summary.external_runtime` pour `P1-A`, `P2-B` et `P2-C`
- les profils actifs `P1-A` remontent dans `key_factors`
- les contraintes `watchlist-diff-only` et `source discovery backlog` remontent en `no_trade_hints`
- `research-adapters.ts` normalise maintenant concretement des packets read-only pour `WorldOSINT`, `worldmonitor.app`, `Hack23/cia` et `open-civic-datasets`

### `P1-B` simulation, contre-factuels et forecast governance

Sources :

- `MiroFish`
- `views-platform`
- `prio-data/views_pipeline`
- `openpredictionmarkets/socialpredict`
- `captbullett65/MSCFT`

Intentions d'integration :

- utiliser `MiroFish` pour le dissent, les contre-factuels et les hypotheses alternatives
- reprendre `views` pour evaluation, auditabilite, walk-forward et gouvernance des experiments
- reprendre `socialpredict` et `MSCFT` seulement comme patterns de produit, economics et hygiene de these

Validation :

- meilleure qualite de dissent et de theses
- meilleure discipline d'experiments et de benchmark
- aucune nouvelle voie canonique parallele a `execution_projection`

Etat runtime livre a ce stade :

- `execution-pathways.ts` expose maintenant `external_governance_summary`
- `walk-forward.ts` et `autopilot-cycle.ts` tracent un resume `external_governance:*` dans leurs notes
- cette couche reste additive et ne change aucune gate canonique
- `forecast-governance.ts` materialise maintenant un artefact read-only reutilisable pour la discipline de benchmark et le dissent

### `P1-C` dashboard/COP patterns

Sources :

- `MISP/misp-dashboard`
- `dfpc-coe/CloudTAK`
- `FreeTAKTeam/FreeTakServer`
- `Esri/dynamic-situational-awareness-qt`
- `CityPulse/CityPulse-City-Dashboard`
- `meteocool/core`
- `OdinMB/city-monitor`

Intentions d'integration :

- reprendre seulement les patterns de read models, cartes, alertes, overlays et triage operateur
- rester strictement read-only
- ne pas ouvrir un second dashboard canonique ni une seconde source de verite runtime

Validation :

- meilleure lisibilite des read models et des alertes
- aucun conflit avec `approval_ticket`, `operator_thesis` ou `research_pipeline_trace` quand absents
- aucune tentative de promotion `live` depuis ces surfaces

Etat runtime livre a ce stade :

- `world-state.ts` expose maintenant `external_read_models_summary`
- `dashboard-models.ts` expose maintenant `external_integrations.runtime_batches`
- les patterns dashboard/COP restent read-only, visibles en production comme resumes de batch sans second dashboard canonique
- `cop-read-models.ts` materialise maintenant un read model COP additif pour overlays/triage operateur

### `P2-A` geo enrichment

Sources :

- `lyhmyd1211/GeoMapData_CN`

Intentions d'integration :

- importer l'asset de donnees pour geo-layer Chine
- l'utiliser seulement pour enrichissement de contexte, dashboards cartographiques et normalisation d'entites

Validation :

- meilleure precision geo
- aucune gate d'execution derivee de cet enrichissement

### `P2-B` watchlist `diff-only`

Sources :

- `sjkncs/worldmonitor`
- `sjkncs/worldmonitor-enhanced`
- `worldmonitor/worldmonitor`

Intentions d'integration :

- auditer le diff contre `koala73/worldmonitor`
- n'extraire aucun code tant qu'aucun uplift local n'est prouve

Validation :

- diff reel documente
- bench local contre l'upstream
- aucune extraction si le gain n'est pas measurable

Etat runtime livre a ce stade :

- la watchlist `P2-B` remonte maintenant explicitement dans les resumes runtime `research` et `dashboard`
- aucun import de code n'a ete ouvert
- `watchlist-audit.ts` materialise maintenant les entrees diff-only et les gates d'extraction `false` par defaut

### `P2-C` source discovery backlog

Sources :

- `doctorfree/osint`
- `ARPSyndicate/awesome-intelligence`

Intentions d'integration :

- s'en servir pour alimenter la veille de nouvelles sources a qualifier
- ne creer aucune dependance runtime

Validation :

- nouvelles sources candidates qualifiees sans diluer la qualite de la matrice principale

Etat runtime livre a ce stade :

- le backlog `P2-C` remonte maintenant explicitement dans les resumes runtime `research` et `dashboard`
- aucune dependance runtime canonique n'a ete ajoutee
- `watchlist-audit.ts` et `operator-analytics.ts` exposent maintenant ces meta-sources comme backlog qualifie read-only

## Ordre de deversement recommande

1. `Polymarket/clob-client` et `Polymarket/py-clob-client`
2. `sculptdotfun/tremor`
3. `WorldOSINT` et `worldmonitor.app`
4. `koala73/worldmonitor` et `Hack23/cia`
5. `MiroFish`, `views-platform` et `prio-data/views_pipeline`
6. `MISP`, `CloudTAK`, `FreeTAK`, `Esri`
7. `CityPulse`, `meteocool`, `city-monitor`
8. `GeoMapData_CN`
9. la famille `worldmonitor` forked uniquement par `diff` prouve
10. `doctorfree/osint` et `ARPSyndicate/awesome-intelligence` comme backlog de veille continue

## Criteres d'acceptation permanents

- chaque repo de cette conversation est mappe vers une cible locale, un mode, un hook de benchmark et un statut
- les integrations `research` ameliorent au moins un de `recall`, `date_confidence`, `clustering`, qualite de `ResearchReport` ou qualite de dissent
- les integrations `execution` preservent `execution_projection` comme source canonique, degradent proprement si la source externe est absente, et montrent un gain mesurable sur readback venue, orderbook, alerting ou robustesse operateur
- les integrations dashboard/COP restent strictement read-only et ne creent pas de second flux canonique
- les integrations geo/civic restent optionnelles et n'introduisent pas de couplage dur au noyau d'execution
- les repos `watchlist-diff-only` produisent d'abord un audit de diff et un bench local contre l'upstream avant toute extraction
- `pattern-only` interdit tout import de code par defaut
- aucun batch n'ouvre `live`
