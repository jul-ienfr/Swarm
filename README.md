# swarm

Ce repo regroupe :

- le coeur `swarm` au root
- un sous-projet `prediction`

## Structure

- `prediction_markets/` : moteur prediction markets Python
- `swarm_core/`, `simulation_adapter/`, `engines/` : coeur de deliberation et runtimes
- `subprojects/prediction/` : surfaces TypeScript/API/tests liees a prediction markets

## Bootstrap rapide

- `python -m venv venv`
- `source venv/bin/activate`
- `python -m pip install -r requirements.txt`

Le runtime `pydanticai` a besoin de `pydantic-ai` et d'un backend OpenAI-compatible configure via `OPENAI_BASE_URL` ou `LLM_PROXY_URL` plus une cle API. Si la dependance manque, le health check renvoie un statut `unavailable` avec un `bootstrap_hint` dans `details`.

Pour obtenir une charge JSON-ready du health check, utiliser `check_pydanticai_runtime_health_payload()` depuis `runtime_pydanticai.factory`.

## Points D'entree

- `main.py` : CLI principal de la surface Swarm, pour les missions, la deliberation, les operations prediction markets et les campagnes de deliberation repetee.
- `python main.py deliberation-campaign ...` : lance une campagne de deliberation repetee et persiste un rapport comparable.
- `python main.py read-deliberation-campaign <campaign-id>` : relit un rapport persiste depuis `data/deliberation_campaigns/<campaign-id>/report.json`.
- `python main.py list-deliberation-campaigns` : liste les campagnes persistées avec leur statut, leur volume de samples et le guard de fallback.
- `python main.py compare-deliberation-campaigns <campaign-a> <campaign-b>` : compare deux campagnes persistées et persiste aussi un rapport de comparaison sous `data/deliberation_campaign_comparisons/<comparison-id>/report.json`.
- `python main.py read-deliberation-campaign-comparison <comparison-id>` : relit un rapport de comparaison persiste pour audit ou export JSON.
- `python main.py list-deliberation-campaign-comparisons` : liste les rapports de comparaison persistés les plus récents.
- `python main.py audit-deliberation-campaign-comparison <comparison-id>` : construit une vue d’audit plus lisible du rapport de comparaison persiste.
- `python main.py export-deliberation-campaign-comparison <comparison-id>` : exporte cet audit en `markdown` ou `json` dans un artefact persistant dédié.
- `python main.py compare-deliberation-campaigns-audit-export <campaign-a> <campaign-b>` : enchaîne comparaison canonique, audit, puis export persistant en une seule commande.
- `python main.py read-deliberation-campaign-comparison-export <comparison-id>` : relit l’export persistant le plus canonique pour une comparaison et un format donnés.
- `python main.py list-deliberation-campaign-comparison-exports` : liste les exports persistants de comparaison.
- `python main.py benchmark-deliberation-campaigns ...` : lance le benchmark baseline/candidate canonique, puis persiste la comparaison, l’audit et l’export dans un bundle canonique.
- `python main.py benchmark-deliberation-campaign-matrix ...` : lance une vraie matrice multi-candidats autour d’une baseline partagée, avec lecture/listing dédiés et visibilité dans les vues globales.
- `python main.py audit-deliberation-campaign-benchmark-matrix <matrix-id>` : construit une vue d’audit lisible d’un benchmark matriciel persistant.
- `python main.py export-deliberation-campaign-benchmark-matrix <matrix-id>` : exporte cet audit en `markdown` ou `json` dans un artefact persistant dédié.
- `python main.py read-deliberation-campaign-benchmark-matrix-export <export-id>` : relit l’export persistant d’un benchmark matriciel par `export_id`.
- `python main.py list-deliberation-campaign-benchmark-matrix-exports` : liste les exports persistants de benchmark matriciel.
- `python main.py compare-deliberation-campaign-benchmark-matrix-exports <export-a> <export-b> ...` : compare plusieurs exports persistants de benchmark matriciel et persiste un rapport dédié sous `data/deliberation_campaign_matrix_benchmark_export_comparisons/<comparison-id>/report.json`.
- `python main.py compare-deliberation-campaign-benchmark-matrix-exports-audit-export <export-a> <export-b> ...` : enchaîne comparaison, audit et export persistant pour plusieurs exports de benchmark matriciel déjà matérialisés.
- `python main.py audit-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` : construit la vue d’audit d’une comparaison persistée entre plusieurs exports matriciels.
- `python main.py export-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` : exporte cet audit d’exports matriciels en `markdown` ou `json`.
- `python main.py read-deliberation-campaign-benchmark-matrix-export-comparison-export <export-id>` : relit un export persistant d’une comparaison entre exports matriciels.
- `python main.py list-deliberation-campaign-benchmark-matrix-export-comparison-exports` : liste les exports persistants de comparaison entre exports matriciels.
- `python main.py compare-deliberation-campaign-benchmark-matrices <matrix-a> <matrix-b>` : compare deux matrices de benchmark persistées et persiste un rapport de comparaison dédié sous `data/deliberation_campaign_matrix_comparisons/<comparison-id>/report.json`.
- `python main.py read-deliberation-campaign-benchmark <benchmark-id>` : relit un benchmark persistant baseline/candidate et restaure le bundle matriciel associé.
- `python main.py list-deliberation-campaign-benchmarks` : liste les benchmarks persistants les plus récents.
- `python main.py read-deliberation-campaign-benchmark-matrix <matrix-id>` : relit un benchmark matriciel persistant.
- `python main.py list-deliberation-campaign-benchmark-matrices` : liste les benchmarks matriciels persistants.
- `python main.py read-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` : relit une comparaison persistante entre deux matrices de benchmark.
- `python main.py list-deliberation-campaign-benchmark-matrix-comparisons` : liste les comparaisons persistées de matrices de benchmark.
- `python main.py compare-deliberation-campaign-benchmark-matrices-audit-export <matrix-a> <matrix-b>` : enchaîne comparaison, audit et export persistant pour deux matrices déjà matérialisées.
- `python main.py audit-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` : construit la vue d’audit d’une comparaison de matrices persistée.
- `python main.py export-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` : exporte cet audit matriciel en `markdown` ou `json`.
- `python main.py read-deliberation-campaign-benchmark-matrix-comparison-export <export-id>` : relit un export matriciel persistant par `export_id`.
- `python main.py list-deliberation-campaign-benchmark-matrix-comparison-exports` : liste les exports persistants de comparaison matricielle.
- Les exports de matrix benchmark sont matérialisés sous `data/deliberation_campaign_matrix_benchmark_exports/<export-id>/manifest.json` et `content.md` ou `content.json`, et ils apparaissent aussi dans `deliberation-campaign-index` et `deliberation-campaign-dashboard`.
- Les comparaisons de matrix benchmark exports sont matérialisées sous `data/deliberation_campaign_matrix_benchmark_export_comparisons/<comparison-id>/report.json`, avec leurs exports dérivés sous `data/deliberation_campaign_matrix_benchmark_export_comparison_exports/<export-id>/manifest.json` et `content.md` ou `content.json`.
- Les exports de matrix benchmark comparison sont matérialisés sous `data/deliberation_campaign_matrix_benchmark_comparison_exports/<export-id>/manifest.json` et `content.md` ou `content.json`, et ils apparaissent aussi dans `deliberation-campaign-index` et `deliberation-campaign-dashboard`.
- `python main.py deliberation-campaign-index` : affiche un index compact de toutes les surfaces persistées, avec campagnes, comparaisons, exports et benchmarks, y compris les matrices de benchmark, leurs exports et leurs comparaisons.
- `python main.py deliberation-campaign-dashboard` : affiche une vue dashboard triable/filtrable sur ces mêmes artefacts persistés, y compris les matrices de benchmark, leurs exports et leurs comparaisons.
- Les exports de comparaison sont persistés sous `data/deliberation_campaign_comparison_exports/<export-id>/manifest.json` et `content.md` ou `content.json`.
- Les benchmarks persistants sont conservés sous `data/deliberation_campaign_benchmarks/<benchmark-id>/report.json`.
- Workflow one-shot recommandé: `compare-deliberation-campaigns-audit-export` pour deux rapports déjà persistés, `benchmark-deliberation-campaigns` pour un benchmark baseline/candidate, ou `benchmark-deliberation-campaign-matrix` pour une baseline partagée contre plusieurs candidats.
- Le bundle canonique du coeur reste la source de vérité: `compare-deliberation-campaigns` produit le rapport persistant, et l’audit/export ne font que matérialiser des vues dérivées autour de ce rapport.
- `python main.py list-deliberation-targets <deliberation-id>` : liste les targets interrogables pour une deliberation persistante.
- Surface `compare` des campagnes : la comparaison expose `summary.comparable` et `summary.mismatch_reasons` pour reperer les differences de topic, mode, runtime, engine, sample_count, stability_runs et comparison_key.
- `swarm_mcp.py` : serveur MCP canonique de Swarm, expose les outils du projet aux clients MCP, dont `run_deliberation_campaign`, `read_deliberation_campaign_artifact`, `read_deliberation_campaign_comparison_artifact`, `audit_deliberation_campaign_comparison_artifact` et `export_deliberation_campaign_comparison_artifact`.
- `swarm_mcp.py` expose aussi `compare_audit_export_deliberation_campaigns` pour le one-shot compare+audit+export, `benchmark_deliberation_campaigns` pour le benchmark baseline/candidate, et `benchmark_deliberation_campaign_matrix` pour la matrice multi-candidats.
- `swarm_mcp.py` expose aussi `audit_deliberation_campaign_benchmark_matrix_artifact`, `export_deliberation_campaign_benchmark_matrix_artifact`, `read_deliberation_campaign_benchmark_matrix_export_artifact` et `list_deliberation_campaign_benchmark_matrix_export_artifacts` pour l’audit/export d’une matrice unique, avec visibilité dans les vues globales.
- `swarm_mcp.py` expose aussi `compare_deliberation_campaign_benchmark_matrix_exports`, `compare_audit_export_deliberation_campaign_benchmark_matrix_exports`, `read_deliberation_campaign_benchmark_matrix_export_comparison_artifact`, `audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact`, `export_deliberation_campaign_benchmark_matrix_export_comparison_artifact`, `read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact` et `list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts`.
- `swarm_mcp.py` expose aussi `compare_deliberation_campaign_benchmark_matrices` pour comparer deux matrices persistées, `compare_audit_export_deliberation_campaign_benchmark_matrices` pour le one-shot matriciel, ainsi que `read_deliberation_campaign_benchmark_matrix_comparison_artifact`, `audit_deliberation_campaign_benchmark_matrix_comparison_artifact`, `export_deliberation_campaign_benchmark_matrix_comparison_artifact`, `read_deliberation_campaign_benchmark_matrix_comparison_export_artifact` et `list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts`.
- `swarm_mcp.py` expose également `read_deliberation_campaign_benchmark_matrix_artifact`, `list_deliberation_campaign_benchmark_matrix_artifacts`, `read_deliberation_campaign_benchmark_matrix_export_artifact` et `list_deliberation_campaign_benchmark_matrix_export_artifacts` pour les matrices persistées et leurs exports.
- `swarm_mcp.py` expose également `read_deliberation_campaign_benchmark_artifact` et `list_deliberation_campaign_benchmarks` pour les benchmarks persistants.
- Pour les matrix benchmark comparisons, le coeur matérialise aussi un audit et un export persistants sous `data/deliberation_campaign_matrix_benchmark_comparison_exports/<export-id>/manifest.json` et `content.md` ou `content.json`, et la CLI comme le MCP exposent maintenant les surfaces dédiées pour auditer, exporter, relire et lister ces artefacts.
- `openclaw_mcp.py` : shim de compatibilite legacy qui redirige vers `swarm_mcp.py`.
- `openclaw_client.py` : client Python specifique a OpenClaw, utilise pour parler aux services et gateways OpenClaw.

Les campagnes renvoient un statut `completed`, `partial` ou `failed`, avec dans le rapport un resume rapide des samples, des scores et du guard de fallback.
Les comparaisons persistées gardent en plus les deltas utiles entre campagnes et les raisons de non-comparabilité.

## Vue Globale

La vue globale des artefacts de delibération se lit maintenant de façon uniforme:

- `python main.py list-deliberation-campaigns` et `read-deliberation-campaign <campaign-id>` pour les campagnes
- `python main.py list-deliberation-campaign-comparisons` et `read-deliberation-campaign-comparison <comparison-id>` pour les comparaisons
- `python main.py list-deliberation-campaign-comparison-exports` et `read-deliberation-campaign-comparison-export <comparison-id>` pour les exports dérivés
- `python main.py list-deliberation-campaign-benchmarks` et `read-deliberation-campaign-benchmark <benchmark-id>` pour les benchmarks persistants, y compris les matrices de benchmark agrégées dans les vues globales
- `python main.py list-deliberation-campaign-benchmark-matrices` et `read-deliberation-campaign-benchmark-matrix <matrix-id>` pour les matrices de benchmark persistées
- `python main.py audit-deliberation-campaign-benchmark-matrix <matrix-id>` et `export-deliberation-campaign-benchmark-matrix <matrix-id>` pour auditer et exporter une matrice persistée
- `python main.py list-deliberation-campaign-benchmark-matrix-exports` et `read-deliberation-campaign-benchmark-matrix-export <export-id>` pour les exports dérivés d’une matrice
- `python main.py list-deliberation-campaign-benchmark-matrix-export-comparisons` et `read-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` pour comparer plusieurs exports matriciels déjà persistés
- `python main.py list-deliberation-campaign-benchmark-matrix-export-comparison-exports` et `read-deliberation-campaign-benchmark-matrix-export-comparison-export <export-id>` pour les exports dérivés de ces comparaisons d’exports matriciels
- `python main.py list-deliberation-campaign-benchmark-matrix-comparisons` et `read-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` pour comparer deux matrices de benchmark persistées
- `python main.py compare-deliberation-campaign-benchmark-matrices <matrix-a> <matrix-b>` pour persister une comparaison canonique entre deux matrices de benchmark persistées
- `python main.py list-deliberation-campaign-benchmark-matrix-comparison-exports` et `read-deliberation-campaign-benchmark-matrix-comparison-export <export-id>` pour les exports matriciels dérivés
- `python main.py compare-deliberation-campaign-benchmark-matrices-audit-export <matrix-a> <matrix-b>` pour le one-shot matriciel `compare -> audit -> export`
- `python main.py deliberation-campaign-index` pour un index global compact des artefacts persistés, y compris les exports de matrices de benchmark
- `python main.py deliberation-campaign-dashboard` pour une vue dashboard triable/filtrable de ces mêmes artefacts, y compris les exports de matrices de benchmark
- `swarm_mcp.py` expose les mêmes familles en MCP avec les outils `list_deliberation_campaigns`, `read_deliberation_campaign_artifact`, `list_deliberation_campaign_comparison_artifacts`, `read_deliberation_campaign_comparison_artifact`, `list_deliberation_campaign_comparison_export_artifacts`, `read_deliberation_campaign_comparison_export_artifact`, `list_deliberation_campaign_benchmarks`, `read_deliberation_campaign_benchmark_artifact`, `list_deliberation_campaign_benchmark_matrix_artifacts`, `read_deliberation_campaign_benchmark_matrix_artifact`, `list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts`, `read_deliberation_campaign_benchmark_matrix_export_comparison_artifact`, `list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts`, `read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact`, `list_deliberation_campaign_benchmark_matrix_comparison_artifacts`, `read_deliberation_campaign_benchmark_matrix_comparison_artifact`, `list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts` et `read_deliberation_campaign_benchmark_matrix_comparison_export_artifact`
- `swarm_mcp.py` expose aussi `audit_deliberation_campaign_benchmark_matrix_artifact`, `export_deliberation_campaign_benchmark_matrix_artifact`, `list_deliberation_campaign_benchmark_matrix_export_artifacts` et `read_deliberation_campaign_benchmark_matrix_export_artifact` pour l’audit/export d’une matrice unique
- `swarm_mcp.py` expose aussi `audit_deliberation_campaign_benchmark_matrix_comparison_artifact`, `export_deliberation_campaign_benchmark_matrix_comparison_artifact` et `compare_audit_export_deliberation_campaign_benchmark_matrices`, plus `deliberation_campaign_index` et `deliberation_campaign_dashboard` pour les vues globales, avec les exports matriciels visibles dans ces vues

Les matrix benchmark comparisons et les matrix benchmark export comparisons suivent maintenant le même pattern canonique que les comparaisons de campagnes simples: `comparison -> audit -> export -> bundle`, avec surfaces dédiées en coeur, CLI et MCP.

Cette vue globale s'appuie sur les helpers du coeur pour conserver une source de vérité unique et éviter que CLI et MCP réécrivent leurs propres chemins de lecture.

## Sous-projet Prediction

Le sous-projet contient les surfaces `prediction-markets` :

- `src/lib/prediction-markets/`
- `src/lib/__tests__/prediction-markets*.test.ts`
- `src/app/api/prediction-markets/`
- `src/app/api/v1/prediction-markets/`
- `docs/cli-agent-control.md`

### Validation de production bornee

Le sous-projet `prediction-markets` suit un principe de validation explicite avant toute promotion:

- `proof chain`: `edge predictif -> edge executable -> edge capturable -> edge durable`
- `gates`: benchmark hors echantillon, `ExecutableEdge` apres frictions, stabilite `paper vs shadow`, runbooks/rollback/kill-switch valides
- `kill criteria`: pas d'uplift robuste, edge qui s'evapore apres friction, divergence `paper vs shadow`, incidents ops repetes
- `advisor-first`: tant que l'edge n'est pas prouve, le systeme reste un excellent advisor et ne doit pas etre presente comme un `profit engine`

Le dashboard de validation et les surfaces CLI restent `preflight-only` tant que cette chaine ne passe pas.

Il est inclus ici comme sous-projet fonctionnel/documentaire a cote de la surface Python `swarm`.
