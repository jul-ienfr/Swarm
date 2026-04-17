# Prediction Dashboards

Le sous-projet prediction contient maintenant trois couches distinctes :

- `index.html` : dashboard operateur local deja branche aux surfaces prediction du repo
- `../dashboard-ui/` : transplant direct de `PolFish/MiroFish/frontend`, avec `npm run run` comme alias de lancement et `npm run help` pour l'aide Vite
- `../dashboard-vendor/` : references statiques reprises depuis `AskEliraTrader`, `CloneHorse`, `firehorse` et `kalshi-ai-trading-bot`

Usage recommande :

- garder `dashboard/index.html` comme surface locale principale du sous-projet
- utiliser `dashboard-ui/` comme base frontend vendorisee pour une future interface plus riche
- utiliser `dashboard-vendor/` comme bibliotheque de patterns visuels et de flux operateur
