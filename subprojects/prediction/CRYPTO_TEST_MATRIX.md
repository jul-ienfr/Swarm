# CRYPTO_TEST_MATRIX

Matrice compacte des tests à relancer après une modification sur la partie crypto du sous-projet `prediction`.

## Core crypto

| Fichier touché | Commande minimale |
|---|---|
| `src/lib/prediction-markets/crypto/manifest.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts` |
| `src/lib/prediction-markets/crypto/universe.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts` |
| `src/lib/prediction-markets/crypto/market-spec.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts src/lib/__tests__/prediction-markets-crypto-screener.test.ts` |
| `src/lib/prediction-markets/crypto/screener.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-screener.test.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |
| `src/lib/prediction-markets/crypto/schemas.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts src/lib/__tests__/prediction-markets-crypto-screener.test.ts` |
| `src/lib/prediction-markets/crypto/types.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts && npm exec --yes --package typescript tsc -- -p ./tsconfig.autonomous.json --noEmit` |
| `src/lib/prediction-markets/crypto/index.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts src/lib/__tests__/prediction-markets-crypto-screener.test.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |

## API crypto

| Fichier touché | Commande minimale |
|---|---|
| `src/app/api/v1/prediction-markets/crypto/screener/route.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |
| `src/app/api/v1/prediction-markets/crypto/opportunities/[opportunity_id]/route.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |

## Intégration connexe

| Fichier touché | Commande minimale |
|---|---|
| `src/lib/prediction-markets/subprojects.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-subproject.test.ts` |
| `src/lib/prediction-markets/service.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/prediction-markets-crypto-screener.test.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |
| `src/lib/prediction-markets/dashboard-models.ts` | `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts src/lib/__tests__/dashboard-models.test.ts src/lib/__tests__/prediction-markets-dashboard-route.test.ts src/lib/__tests__/prediction-markets-crypto-routes.test.ts` |

## Priorités opérationnelles

### P1 — cœur crypto critique
À lancer dès qu'une modification touche le scoring, les seeds, la taxonomie active ou les routes crypto.

Fichiers typiques :
- `src/lib/prediction-markets/crypto/screener.ts`
- `src/lib/prediction-markets/crypto/market-spec.ts`
- `src/app/api/v1/prediction-markets/crypto/screener/route.ts`
- `src/app/api/v1/prediction-markets/crypto/opportunities/[opportunity_id]/route.ts`

Commande :

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts
```

### P2 — intégration crypto
À lancer si la modif touche l'exposition du sous-projet, le service de marché live, ou les modèles dashboard.

Fichiers typiques :
- `src/lib/prediction-markets/service.ts`
- `src/lib/prediction-markets/subprojects.ts`
- `src/lib/prediction-markets/dashboard-models.ts`

Commande :

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts \
  src/lib/__tests__/dashboard-models.test.ts \
  src/lib/__tests__/prediction-markets-dashboard-route.test.ts
```

### P3 — gate final avant merge
À lancer avant merge ou après une modif transverse.

```bash
npm run test:ops && npm run test:dashboard && npm run typecheck
```

## Commandes par dossier

### Si tu touches `src/lib/prediction-markets/crypto/`

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts
```

### Si tu touches `src/app/api/v1/prediction-markets/crypto/`

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts
```

### Si tu touches `src/lib/prediction-markets/` hors dossier `crypto/`

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts \
  src/lib/__tests__/dashboard-models.test.ts \
  src/lib/__tests__/prediction-markets-dashboard-route.test.ts
```

## Commandes de référence

### Batch minimal crypto

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts
```

### Batch safe crypto + intégration

```bash
npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
  src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
  src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
  src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
  src/lib/__tests__/prediction-markets-crypto-routes.test.ts \
  src/lib/__tests__/dashboard-models.test.ts \
  src/lib/__tests__/prediction-markets-dashboard-route.test.ts
```

### Gate typecheck

```bash
npm exec --yes --package typescript tsc -- -p ./tsconfig.autonomous.json --noEmit
```

### Gate avant merge

```bash
npm run test:ops && npm run test:dashboard && npm run typecheck
```

## Script helper

```bash
./scripts/test-crypto.sh p1
./scripts/test-crypto.sh p2
./scripts/test-crypto.sh merge
npm run test:crypto
npm run test:crypto:safe
npm run test:crypto:merge
```

Aliases :
- `minimal` = `p1`
- `safe` = `p2`

## Règle simple

- **1 fichier crypto cœur touché** → batch minimal crypto / `./scripts/test-crypto.sh p1` / `npm run test:crypto`
- **route/API ou dashboard touché** → batch safe / `./scripts/test-crypto.sh p2` / `npm run test:crypto:safe`
- **avant merge** → gate complet / `./scripts/test-crypto.sh merge` / `npm run test:crypto:merge`

## Hook git optionnel

- pre-commit installer : `npm run hook:crypto:install`
- pre-commit exécution manuelle : `npm run hook:crypto:run`
- pre-commit comportement : le hook `pre-commit` lance `npm run test:crypto` seulement si le commit contient des fichiers crypto ciblés (`src/lib/prediction-markets/crypto/`, routes API crypto, tests crypto, docs crypto, script crypto, `package.json`)
- pre-push installer : `npm run hook:crypto:push:install`
- pre-push exécution manuelle : `npm run hook:crypto:push`
- pre-push comportement : si le push contient des fichiers crypto ciblés, le hook lance `npm run test:crypto:safe` par défaut ; sur `main`/`master`, il bascule sur `npm run test:crypto:merge`
- override explicite : `HERMES_CRYPTO_PREPUSH_LEVEL=safe|merge`
