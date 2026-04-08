import os
import time
from typing import Dict, Any

from openclaw_client import OpenClawClient

RIG1_IP = "192.168.31.9"
NAS_PATH = "/mnt/truenas"

# --- STRATÉGIE DE FALLBACK AUTO-HEALING ---
# 1. OpenRouter (Très intelligent, gratuit, mais capricieux sur les rate limits)
# 2. Antigravity (Google Cloud, très robuste et constant)
# 3. Ollama (Local, 100% garanti de fonctionner même sans internet)
FALLBACK_MODELS = [
    "openrouter/nousresearch/hermes-3-llama-3.1-405b:free",
    "antigravity-proxy/gemini-3.1-pro-high",
    "ollama/qwen2.5-coder:14b"
]

class MediaGenerator:
    """
    Worker LangGraph : Le Studio Multimédia (Rig 1).
    Délègue l'exécution à l'agent OpenClaw centralisé qui lance lui-même les commandes
    (SSH, API SwarmUI, XTTS) grâce à ses propres outils natifs.
    """
    def __init__(self, config: Dict[str, Any]):
        self.client = OpenClawClient(config_path="config.yaml")
        # On identifie l'agent configuré côté OpenClaw (par défaut media_generator)
        self.agent_id = config.get("agent_id", "media_generator")
        self.rig1_ip = config.get("rig1_ip", RIG1_IP)

    def execute(self, state: Any) -> Dict[str, Any]:
        """Interface standard pour le Superviseur global Magentic-One."""
        instruction = state.get("progress_ledger", {}).get("instruction", "")

        import re
        import time
        # On extrait le project_id de l'instruction du superviseur
        match = re.search(r'tiktok_\d+', instruction)
        project_id = match.group(0) if match else f"tiktok_{int(time.time())}"

        mission_prompt = f"""MISSION ORDONNÉE PAR LE SUPERVISEUR :
{instruction}
Dossier cible du projet : {NAS_PATH}/projets/{project_id}

CONTRAINTES CRITIQUES MATÉRIELLES (Raisonnement étape par étape exigé) :
1. Les GPUs de la machine distante ({self.rig1_ip}) sont actuellement utilisés pour du MINAGE CRYPTO 24/7.
2. Avant de générer les médias, tu DOIS te connecter en SSH (julien@{self.rig1_ip}) et vérifier la VRAM avec 'nvidia-smi'.
3. Si la mémoire est saturée, trouve les PIDs des processus miniers et mets-les en pause (sudo kill -STOP).
4. Utilise tes outils (SwarmUI, XTTS) pour générer les médias demandés par le superviseur dans le dossier cible.
5. RÈGLE D'OR : Dès que tu as fini de générer les médias, tu DOIS ABSOLUMENT relancer le minage (sudo kill -CONT).

Termine ta réponse par un récapitulatif clair de ce que tu as accompli et des fichiers générés."""

        messages = [{"role": "user", "content": mission_prompt}]

        result = None
        used_model = None

        print(f"\n[MediaGenerator] 🔌 Ordre du Superviseur reçu pour le projet : {project_id}")

        for model in FALLBACK_MODELS:
            try:
                print(f"  [Auto-Healing] Tentative d'exécution avec le modèle : {model}")
                result = self.client.chat_with_agent(
                    worker_name="studio-media",
                    agent_id=self.agent_id,
                    model=model,
                    messages=messages
                )

                error_msg = str(result.get("error", "")).lower()
                if not result.get("success") and any(err in error_msg for err in ["429", "503", "rate limit", "too many requests"]):
                    print(f"  [Auto-Healing] ⚠️ Échec avec {model} (Surcharge). Bascule automatique...")
                    continue

                if result.get("success"):
                    used_model = model
                    print(f"  [Auto-Healing] ✅ Succès avec le modèle : {used_model}")
                    break
            except Exception as e:
                print(f"  [Auto-Healing] 💥 Exception avec {model} : {str(e)}")
                continue

        if not result or not result.get("success"):
            return {
                "workers_output": [{
                    "worker_name": "studio-media",
                    "content": "",
                    "success": False,
                    "error": "Épuisement du fallback LLM. L'agent n'a pas pu s'exécuter.",
                    "tokens_used": 0,
                    "metadata": {}
                }]
            }

        return {
            "workers_output": [{
                "worker_name": "studio-media",
                "content": result.get("content", ""),
                "success": True,
                "error": None,
                "tokens_used": result.get("tokens_used", 0),
                "metadata": {"model_used": used_model, "project_id": project_id}
            }]
        }

    def invoke(self, project_id: str, script_data: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n[MediaGenerator] 🧠 Réveil de l'Agent Multimédia pour le projet '{project_id}'")

        scenes = script_data.get("scenes", [])
        prompts = [s.get("visual_prompt", "") for s in scenes if s.get("visual_prompt")]
        work_dir = f"{NAS_PATH}/projets/{project_id}"

        # On s'assure que le dossier parent existe
        os.makedirs(work_dir, exist_ok=True)

        expected_audio = f"{work_dir}/voix.wav"
        expected_images = [f"{work_dir}/scene_{i+1}.jpg" for i in range(len(prompts))]

        mission_prompt = f"""Tu es l'Agent DevOps Multimédia chargé de produire les assets pour le projet '{project_id}'.
Voici les {len(prompts)} prompts d'images à générer : {prompts}
Dossier de travail ciblé : {work_dir}

CONTRAINTES CRITIQUES (Raisonnement étape par étape exigé) :
1. Les GPUs de la machine distante ({self.rig1_ip}) sont actuellement utilisés pour du MINAGE CRYPTO 24/7.
2. Avant de générer la moindre image, tu DOIS utiliser tes outils pour te connecter en SSH (julien@{self.rig1_ip}) et vérifier la VRAM avec 'nvidia-smi'.
3. Si la mémoire est saturée, trouve les PIDs des processus miniers et mets-les en pause (sudo kill -STOP).
4. Une fois la voie libre, utilise les APIs ou commandes nécessaires pour générer les images (SwarmUI) et l'audio (XTTS) dans le dossier de travail.
   - Le fichier audio généré DOIT être sauvegardé sous : {expected_audio}
   - Les fichiers images générés DOIVENT être sauvegardés sous : {expected_images}
5. RÈGLE D'OR : Dès que tu as fini de générer les médias, tu DOIS ABSOLUMENT relancer le minage (sudo kill -CONT).

Termine ta réponse par un récapitulatif clair de ce que tu as accompli."""

        messages = [{"role": "user", "content": mission_prompt}]

        max_retries = 3
        attempts = 0

        # Boucle de validation (Agentic Feedback Loop)
        while attempts < max_retries:
            print(f"[MediaGenerator] 🔌 Délégation des commandes à l'agent OpenClaw '{self.agent_id}' (Tentative {attempts + 1}/{max_retries})...")

            result = None
            used_model = None

            # --- BOUCLE DE FALLBACK (Auto-Healing) ---
            for model in FALLBACK_MODELS:
                try:
                    print(f"  [Auto-Healing] Tentative d'exécution avec le modèle : {model}")
                    
                    # On tente l'appel. Note: Nécessite que `chat_with_agent` supporte l'override de `model`
                    result = self.client.chat_with_agent(
                        worker_name="MediaGenerator",
                        agent_id=self.agent_id,
                        model=model, # Surcharge dynamique du modèle
                        messages=messages
                    )

                    # Gestion des erreurs typiques de rate limit OpenRouter
                    error_msg = str(result.get("error", "")).lower()
                    if not result.get("success") and any(err in error_msg for err in ["429", "503", "rate limit", "too many requests"]):
                        print(f"  [Auto-Healing] ⚠️ Échec avec {model} (Surcharge/RateLimit). Bascule automatique au modèle suivant...")
                        continue
                    
                    if result.get("success"):
                        used_model = model
                        print(f"  [Auto-Healing] ✅ Succès avec le modèle : {used_model}")
                        break
                    else:
                        print(f"  [Auto-Healing] ❌ Erreur avec {model} : {result.get('error')}")

                except Exception as e:
                    print(f"  [Auto-Healing] 💥 Exception critique avec {model} : {str(e)}")
                    continue
            
            # Si la boucle a terminé mais qu'aucun modèle n'a fonctionné
            if not result or not result.get("success"):
                print("[MediaGenerator] 💥 ERREUR FATALE : Tous les modèles de fallback ont échoué !")
                return {
                    "status": "error",
                    "error": "Épuisement du fallback LLM. L'agent n'a pas pu s'exécuter."
                }

            print(f"  [Agent {self.agent_id} via {used_model}] 🗣️  \n{result.get('content')}")

            # Vérification de la création RÉELLE des fichiers sur le disque
            missing_files = []
            if not os.path.exists(expected_audio):
                missing_files.append(expected_audio)
            for img in expected_images:
                if not os.path.exists(img):
                    missing_files.append(img)

            if not missing_files:
                print("[MediaGenerator] ✅ Succès : Tous les fichiers multimédias ont bien été créés sur le disque.")
                return {
                    "status": "success",
                    "assets_generated": {
                        "audio": expected_audio,
                        "images": expected_images
                    }
                }

            # Si des fichiers manquent, on relance l'agent en lui signalant son erreur
            print(f"[MediaGenerator] ⚠️ Échec de validation : {len(missing_files)} fichiers manquants. Relance de l'agent...")
            messages.append({"role": "assistant", "content": result.get("content", "")})
            messages.append({
                "role": "user",
                "content": f"ÉCHEC DE VÉRIFICATION : Les fichiers suivants n'ont PAS été trouvés sur le disque : {missing_files}.\nTu as peut-être simulé l'action dans ta réponse sans réellement utiliser d'outil pour écrire les fichiers. Tu DOIS utiliser tes outils d'exécution (ex: bash, script, ou API) pour générer physiquement ces fichiers. Merci de corriger et de réessayer."
            })
            attempts += 1
            time.sleep(2)

        print(f"[MediaGenerator] 🚨 ÉCHEC CRITIQUE : L'agent n'a pas réussi à générer les fichiers réels après {max_retries} tentatives.")
        return {
            "status": "error",
            "error": f"L'agent {self.agent_id} a échoué à générer les fichiers réels sur le NAS après {max_retries} tentatives."
        }
