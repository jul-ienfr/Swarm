import asyncio
import os
import sys

# Ajouter le workspace au path pour trouver supervisor.py
sys.path.append("/home/jul/.openclaw/workspace/langgraph-swarm")

from supervisor import SupervisorNode

def test_supervisor_instruction():
    print("🚀 Démarrage du test du Superviseur LangGraph...")

    # Initialisation du superviseur
    supervisor = SupervisorNode(config_path="/home/jul/.openclaw/workspace/langgraph-swarm/config.yaml")

    # Création d'un faux state simulant la demande de l'utilisateur
    fake_state = {
        "task_ledger": {
            "goal": "Demande à l'agent mining-crypto de relancer le minage sur le 7950X",
            "plan": ["1. Demander à mining-crypto de relancer le 7950X"],
        },
        "progress_ledger": {
            "step_index": 0,
            "stall_count": 0
        },
        "workers_output": [],
        "tokens_used_total": 0
    }

    print("\n⏳ Exécution du Superviseur (génération de l'instruction)...")
    result = supervisor.execute(fake_state)

    print("\n✅ Résultat :")
    progress = result.get("progress_ledger", {})
    assignments = progress.get("assignments", [])

    for a in assignments:
        print(f"\n=> Agent assigné : {a.get('speaker')}")
        print(f"=> Instruction générée :\n{a.get('instruction')}")

if __name__ == "__main__":
    test_supervisor_instruction()
