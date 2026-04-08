# prediction

Sous-projet `prediction` du repo `swarm`.

Contenu principal :

- `src/lib/prediction-markets/`
- `src/lib/__tests__/prediction-markets*.test.ts`
- `src/app/api/prediction-markets/`
- `src/app/api/v1/prediction-markets/`
- `docs/cli-agent-control.md`
- `scripts/mc-cli.cjs` (wrapper CLI local du sous-projet)
- `scripts/prediction-ops.cjs` (helper opérateur local pour `runs`, `capabilities`, `health`, `dispatch`, `paper`, `shadow`, `live` et les alias feed/bootstrap)
- `scripts/prediction-dashboard.cjs` (dashboard web same-origin local avec proxy vers l'API prediction-markets)

Ce sous-projet regroupe les surfaces TypeScript/API/tests liees a prediction markets, a cote du coeur Python `swarm`.

### Validation de production bornee

Le sous-projet `prediction-markets` suit un principe de validation explicite avant toute promotion:

- `proof chain`: `edge predictif -> edge executable -> edge capturable -> edge durable`
- `gates`: benchmark hors echantillon, `ExecutableEdge` apres frictions, stabilite `paper vs shadow`, runbooks/rollback/kill-switch valides
- `kill criteria`: pas d'uplift robuste, edge qui s'evapore apres friction, divergence `paper vs shadow`, incidents ops repetes
- `advisor-first`: tant que l'edge n'est pas prouve, le systeme reste un excellent advisor et ne doit pas etre presente comme un `profit engine`

Le dashboard de validation et les surfaces CLI restent `preflight-only` tant que cette chaine ne passe pas.

Le wrapper CLI local est `scripts/mc-cli.cjs` quand on travaille depuis `/home/jul/swarm/subprojects/prediction`, et `subprojects/prediction/scripts/mc-cli.cjs` si on l'appelle depuis la racine `/home/jul/swarm`. Le wrapper se résout lui-même par chemin relatif; `PREDICTION_CLI_PATH` reste un helper de tests, pas une option runtime.
Le helper opérateur local est `scripts/prediction-ops.cjs`; il résout les surfaces `runs`, `capabilities`, `health`, `dispatch`, `paper`, `shadow` et `live`, peut injecter `PREDICTION_BASE_URL` en URL locale par défaut, et applique `PREDICTION_DEFAULT_VENUE` sur les surfaces feed/bootstrap (`markets`, `capabilities`, `health`, `feed`) quand on ne précise pas `--venue`.

Pour `POLY-025`, les summaries `--research-summary` et `--benchmark-summary` sont lisibles sur `run`/`runs` comme sur `dispatch`, `paper`, `shadow` et `live`, ce qui permet de suivre la gate runtime sans repasser par `service.ts`. Quand les deux familles de champs existent, le CLI préfère les signaux canoniques `benchmark_*` et ne retombe sur `research_benchmark_*` qu'en fallback. Le résumé `research:` indique aussi désormais `mode=market_only` ou `mode=research_driven` pour rendre visible la différence entre un baseline marché et un signal nourri par la recherche.

Le sous-projet embarque aussi son autonomie locale minimale :

- `package.json`
- `tsconfig.json`
- `vitest.config.ts`

Scripts locaux utiles :

- `npm run cli -- prediction-markets runs --json`
- `npm run ops -- runs --json`
- `npm run dashboard -- --upstream http://127.0.0.1:3000`
- `npm run dashboard:help`
- `npm run pm:help`
- `npm run pm:feed -- --venue polymarket --json`
- `npm run pm:feed:summary`
- `npm run pm:feed:request`
- `npm run pm:runs -- --json`
- `npm run pm:runs:summary -- --limit 5`
- `npm run pm:capabilities -- --venue polymarket --json`
- `npm run pm:capabilities:summary`
- `npm run pm:capabilities:request`
- `npm run pm:health -- --venue polymarket --json`
- `npm run pm:health:summary`
- `npm run pm:health:request`
- `npm run pm:dispatch -- --run-id <run-id> --execution-pathways-summary`
- `npm run pm:dispatch:summary -- --run-id <run-id>`
- `npm run pm:dispatch:request -- --run-id <run-id>`
- `npm run pm:paper -- --run-id <run-id> --execution-pathways-summary`
- `npm run pm:paper:summary -- --run-id <run-id>`
- `npm run pm:paper:request -- --run-id <run-id>`
- `npm run pm:shadow -- --run-id <run-id> --execution-pathways-summary`
- `npm run pm:shadow:summary -- --run-id <run-id>`
- `npm run pm:shadow:request -- --run-id <run-id>`
- `npm run pm:live -- --run-id <run-id> --execution-pathways-summary`
- `npm run pm:live:surface -- --run-id <run-id>`
- `npm run pm:live:summary -- --run-id <run-id>`
- `npm run pm:live:request -- --run-id <run-id>`
- `npm run test`
- `npm run test:advisor`
- `npm run test:ops`
- `npm run typecheck`
- `npm run typecheck:full`

`typecheck` valide la surface autonome du sous-projet `prediction` dans ce repo.
`typecheck:full` garde la validation large héritée quand l'environnement Next complet est disponible.

Surfaces opérateur locales :

- `pm:capabilities` expose les contrats de capacités, budgets et contraintes d'automatisation.
- `pm:health` expose l'état live/feed local, y compris `market_feed`, `user_feed` et `rtds`.
- `pm:feed` est un alias opérateur local vers `health` pour les surfaces feed/readiness.
- `pm:dispatch`, `pm:paper`, `pm:shadow` et `pm:live` donnent les surfaces d'exécution opérateur autour de `execution_projection`, sans réexécuter le runtime Python.
- `pm:live` reste strictement `preflight-only` et expose les signaux `execution_readiness` et `multi_venue_execution` du run, sans prétendre à du streaming live réel.
- un dashboard web same-origin plus complet est maintenant disponible :
  - en mode app route : ouvrir `/prediction-markets/dashboard` quand le serveur Swarm/Next qui expose les routes prediction est lancé
  - en mode local autonome : `npm run dashboard -- --upstream http://127.0.0.1:3000`, puis ouvrir l'URL affichée
  - le dashboard lit les read models `overview`, `runs`, `run detail`, `benchmark`, `venue`, les surfaces `dispatch`, `paper`, `shadow` et `live`, les live-intents canoniques (`execution_projection_selected_preview`, `live_trade_intent_preview`) et le `trade_intent_guard`
  - le dashboard doit aussi servir de point de remontee pour `cross_venue_intelligence`, `cross_venue_summary` et `shadow_arbitrage` via un bloc `Cross-Venue / Arbitrage` shadow-only pour commencer avec `Polymarket` et `Kalshi`
  - le helper local repose sur des requêtes HTTP et le proxy local; il ne dépend pas d'un canal SSE dédié externe dans ce sous-projet
  - le flux `/api/v1/prediction-markets/dashboard/events` alimente aussi l'audit temps réel, les alertes benchmark, et les transitions de live-intents
- `ops` et `pm:help` donnent un point d'entrée local unique pour ces surfaces, sans se souvenir de la forme complète `prediction-markets ...`.
- `--operator-summary` est le preset local qui ajoute automatiquement `--execution-pathways-summary`, `--research-summary` et `--benchmark-summary`.
- `--operator-json` ajoute le même preset opérateur, plus `--json`.
- `--print-summary` affiche une ligne compacte de surface, une ligne de sémantique (`readiness`, `promotion`, `transport`), puis un `request_preview` lisible et un résumé opérateur.
- `--print-request` affiche la requête HTTP résolue (`method`, `path`, `url`, `body`) sans exécuter d'appel.
- `--print-command` et `--print-request` embarquent aussi `request_preview`, `surface_summary` et un bloc JSON `semantics` pour distinguer les surfaces `operator_preflight`, `operator_surface`, `feed_bootstrap` et `run_readback`.
- `test:ops` verrouille précisément ces routes et surfaces `live/feed/execution` côté sous-projet.

Points d'entree Python relies a ce sous-projet et a la surface Swarm racine :

- `main.py` : CLI principal de Swarm pour les commandes `prediction-markets`, `run`, `delegate`, `resume` et `status`.
- `swarm_mcp.py` : serveur MCP canonique de Swarm, expose comme outils les capacites Python et les surfaces prediction markets.
- `openclaw_mcp.py` : alias legacy conserve pour compatibilite avec les anciens imports et scripts.

Le sous-projet `prediction` s'aligne donc avec le CLI Python et la surface MCP de Swarm, tout en gardant ses propres routes, tests et docs TypeScript.
