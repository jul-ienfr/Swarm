import json
from workers.openclaw_delegate import OpenClawDelegateWorker

# Configuration simplifiée (OpenClaw gère tout)
config_path = "/home/jul/.openclaw/openclaw.json"

if __name__ == "__main__":
    print(r"""
     _____                   _       ___  ____
    |_   _| __ ___ _ __   __| |     / _ \|  _ \
      | || '__/ _ \ '_ \ / _` |____| | | | | | |
      | || | |  __/ | | | (_| |____| |_| | |_| |
      |_||_|  \___|_| |_|\__,_|     \___/|____/

    --- Mode "Chercheur d'Or" (Découverte de Niche Autonome via OpenClaw) ---
    """)

    # Instanciation de l'Agent natif OpenClaw "trend-discoverer"
    directeur_rd = OpenClawDelegateWorker(agent_id="trend-discoverer", config_path=config_path)

    print("[TrendDiscoverer] Lancement de l'étude de marché via OpenClaw...")

    # On simule l'état du superviseur attendu par le Delegate
    mock_state = {
        "progress_ledger": {
            "instruction": "Analyse les tendances YouTube Shorts et TikTok actuelles pour l'année 2026. Trouve les 3 meilleures niches avec le plus haut potentiel de RPM (Revenu pour 1000 vues). Propose 3 noms de chaînes uniques. Réponds UNIQUEMENT en JSON format: {\"niches\": [{\"niche_name\": \"...\", \"rpm_potential\": \"...\", \"reasoning\": \"...\", \"proposed_channel_names\": [\"...\", \"...\"]}]}"
        }
    }

    # Appel direct à l'agent OpenClaw
    resultat = directeur_rd.execute(mock_state)

    # Le Delegate renvoie une liste dans 'workers_output', on prend le premier élément
    agent_response = resultat.get("workers_output", [{}])[0]

    if agent_response.get("success"):
        try:
            # Nettoyage et parsing du JSON renvoyé par l'agent OpenClaw
            clean_text = agent_response["content"].replace("```json", "").replace("```", "").strip()
            discovery_data = json.loads(clean_text)

            print("\n=== 💎 RÉSULTATS DE L'ÉTUDE DE MARCHÉ ===")
            niches = discovery_data.get("niches", [])
            for i, niche in enumerate(niches, 1):
                print(f"\n[{i}] NICHE : {niche.get('niche_name')}")
                print(f"💰 Potentiel RPM : {niche.get('rpm_potential')}")
                print(f"🧠 Raison : {niche.get('reasoning')}")
                print(f"📛 Noms suggérés : {', '.join(niche.get('proposed_channel_names', []))}")
                print("-" * 50)

            print("\n[Action Suivante] Copie le nom de la niche choisie et insère-la dans le 'initial_state' de main_graph.py !")
            print(f"\n(Tokens utilisés : {agent_response.get('tokens_used', 'N/A')})")

        except json.JSONDecodeError as e:
            print(f"\n[ERREUR] L'agent n'a pas renvoyé un JSON valide : {e}")
            print("Réponse brute de l'agent :")
            print(agent_response["content"])
    else:
        print(f"\n[ERREUR] Impossible de réaliser l'étude : {agent_response.get('error')}")
