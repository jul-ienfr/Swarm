# Swarm Memory

Ce document est la memoire canonique au niveau du repo `swarm`.

Il sert a garder 4 choses stables :

- la cartographie du repo
- les surfaces canoniques de lecture et d'execution
- la doctrine de memoire du projet
- les pointeurs vers les memoires specialisees

Le detail metier d'un sous-projet ne doit pas vivre ici s'il a deja sa propre memoire canonique.

## Cartographie du repo

Le repo regroupe deux niveaux principaux :

- le coeur `swarm` au root
- le sous-projet `subprojects/prediction` pour les surfaces TypeScript/API/tests autour de `prediction-markets`

Zones structurantes :

- `main.py` : CLI principal du repo
- `swarm_mcp.py` : serveur MCP canonique
- `openclaw_mcp.py` : alias legacy de compatibilite
- `swarm_core/`, `runtime_*`, `engines/`, `simulation_adapter/` : coeur de deliberation et runtimes
- `prediction_markets/` : moteur prediction markets Python cote root
- `subprojects/prediction/` : sous-projet prediction markets cote TypeScript/API/dashboard/tests
- `dashboard/swarm-ui/` et `dashboard/swarm-ui-alt/` : frontends repo-locaux a la racine
- `data/` : artefacts et rapports persistants
- `tests/` : validation du coeur et des surfaces adjacentes

## Surfaces canoniques

Les points d'entree a traiter comme canoniques aujourd'hui sont :

- `python main.py ...` pour la CLI `swarm`
- `python swarm_mcp.py` pour la surface MCP
- `node scripts/swarm-dashboard.cjs` pour la petite surface dashboard HTTP racine
- `subprojects/prediction/scripts/mc-cli.cjs` pour la CLI locale `prediction`
- `subprojects/prediction/scripts/prediction-ops.cjs` pour les surfaces operateur `dispatch/paper/shadow/live`
- `/prediction-markets/dashboard` et `subprojects/prediction/scripts/prediction-dashboard.cjs` pour le dashboard operator prediction

Important :

- les dashboards vendores ou repo-locaux non branches ne deviennent pas canoniques par simple presence dans le repo
- le sous-projet `prediction` reste `advisor-first` et `preflight-first`
- la promotion `live` ne se deduit pas d'une doc ou d'une these ; elle reste gouvernee par les surfaces runtime canoniques

## Doctrine de memoire

La memoire canonique du projet vit dans le repo.

Regles :

- les faits globaux `swarm` vivent ici
- les details d'un sous-projet vivent dans la memoire canonique de ce sous-projet
- un plan de travail hors repo peut servir d'input, mais pas de source canonique durable
- une evaluation de source externe doit vivre dans la memoire specialisee du sous-projet concerne avant toute promotion de code
- une reference externe n'accorde jamais a elle seule un droit d'import ; seule la validation locale tranche

## Conventions d'indexation

On distingue 3 niveaux de documents :

1. `memoire index`
   - repere les surfaces, les conventions et les pointeurs
2. `memoire specialisee`
   - garde la doctrine metier, les decisions stables et le registre des sources
3. `plan d'integration`
   - transforme les sources retenues en batches, priorites, hooks de benchmark et cibles locales

Quand une nouvelle source externe est evaluee pour `prediction` :

1. l'ajouter dans `subprojects/prediction/docs/prediction-memory.md`
2. si elle est actionnable, l'ajouter aussi dans `subprojects/prediction/docs/prediction-integration-plan.md`
3. ne la promouvoir en `import` ou `adapt` qu'apres validation locale

## Memoires specialisees

- [Prediction Memory](../subprojects/prediction/docs/prediction-memory.md)
- [Prediction Integration Plan](../subprojects/prediction/docs/prediction-integration-plan.md)
- [Prediction CLI Agent Control](../subprojects/prediction/docs/cli-agent-control.md)
- [Prediction Dashboard Contract](../subprojects/prediction/docs/dashboard-contract.md)

## Relation entre `swarm` et `prediction`

`swarm` reste la couche de coordination globale.

Le sous-projet `prediction` garde sa propre granularite documentaire car il porte :

- des surfaces runtime et dashboard specifiques
- une doctrine `quality-first` sur la reutilisation externe
- une preuve de promotion metier differente du reste du repo
- des besoins d'integration externes beaucoup plus denses que le coeur `swarm`

Cette separation evite de melanger :

- la carte globale du repo
- la doctrine metier prediction markets
- le backlog d'integration des patterns externes

## Non-canonique mais utile

Le fichier de travail `/home/jul/plan-prediction-markets.md` reste un input utile pour l'import et la normalisation, mais il n'est plus considere comme l'emplacement canonique de la memoire ou du plan d'integration.
