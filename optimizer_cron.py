import sqlite3
import yaml
import json
import os
import datetime
from collections import defaultdict

CONFIG_PATH = "/home/jul/.openclaw/workspace/langgraph-swarm/config.yaml"
DB_PATH = "/home/jul/mission-control/.data/mission-control.db"


def get_dynamic_model_ladder():
    try:
        with open("/home/jul/.openclaw/openclaw.json", "r") as f:
            oc_config = json.load(f)
            
        discovered_models = set()
        providers = oc_config.get("models", {}).get("providers", {})
        for prov_name, prov_data in providers.items():
            for mod in prov_data.get("models", []):
                if isinstance(mod, dict):
                    mod_id = mod.get("id")
                else:
                    mod_id = str(mod)
                if mod_id:
                    discovered_models.add(mod_id)
                    
        # Si aucun modèle n'est trouvé dans les providers explicites, on fallback
        if not discovered_models:
            discovered_models.add("gemini-3.1-pro-high")
            
        # Scoring heuristique pour trier du moins puissant (rapide/gratuit) au plus puissant (smart/cher)
        def score_model(m):
            m_lower = m.lower()
            score = 50 # Base (Medium)
            
            # Modèles très rapides/petits
            if any(k in m_lower for k in ["nano", "lite", "8b", "small", "haiku"]):
                score -= 30
            elif any(k in m_lower for k in ["flash", "mini"]):
                score -= 15
                
            # Modèles puissants/larges
            if any(k in m_lower for k in ["pro-high", "opus", "70b", "120b", "405b", "super"]):
                score += 30
            elif any(k in m_lower for k in ["sonnet", "pro", "medium"]):
                score += 15
                
            return score
            
        ladder = list(discovered_models)
        ladder.sort(key=score_model)
        
        print(f"  [MODELS] 🧬 Échelle générée dynamiquement ({len(ladder)} modèles) : {', '.join(ladder[:3])}... -> {ladder[-1]}")
        return ladder
    except Exception as e:
        print(f"  [WARN] ⚠️ Impossible de lire openclaw.json pour l'échelle des modèles : {e}")
        return ["gemini-3.1-pro-high"]


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

def analyze_telemetry():
    """Analyse les logs d'activité dans la base Mission Control pour en tirer des métriques."""
    if not os.path.exists(DB_PATH):
        print(f"[WARN] Database {DB_PATH} not found. Skipping analysis.")
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # On regarde les dernières 24h
    yesterday = int((datetime.datetime.utcnow() - datetime.timedelta(days=1)).timestamp())
    
    try:
        cursor.execute('''
            SELECT description, data FROM activities 
            WHERE actor = 'supervisor' AND created_at >= ?
        ''', (yesterday,))
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        print("[WARN] Table activities introuvable ou schéma incorrect.")
        return {}

    metrics = defaultdict(lambda: {"delegations": 0, "errors": 0, "tokens": 0})
    
    for desc, data_json in rows:
        try:
            data = json.loads(data_json) if data_json else {}
            tokens = data.get("tokens", 0)
        except:
            tokens = 0

        # Parse description: "[DÉLÉGATION] Cible : Coder | Instr : ..."
        # or "[ERROR] Coder failed: ..."
        if desc.startswith("[DÉLÉGATION]"):
            try:
                target = desc.split("Cible : ")[1].split(" |")[0].strip()
                metrics[target]["delegations"] += 1
                metrics[target]["tokens"] += tokens
            except IndexError:
                pass
        elif desc.startswith("[ERROR]"):
            try:
                target = desc.split(" ")[1] # Ex: "[ERROR] Coder failed:..."
                metrics[target]["errors"] += 1
            except IndexError:
                pass

    conn.close()
    return dict(metrics)

def optimize_system():
    print("🚀 Démarrage de l'Optimizer (Minimax M2.7 Auto-Improvement Loop)...")
    model_ladder = get_dynamic_model_ladder()
    config = load_config()
    metrics = analyze_telemetry()
    
    if not metrics:
        print("ℹ️ Pas assez de données télémétriques pour optimiser.")
        return

    workers_config = config.get("workers", {})
    changes_made = False

    for worker_name, stats in metrics.items():
        if worker_name not in ["Coder", "ShellExecutor", "WebSearcher", "FileReader"]:
            continue
            
        delegations = stats["delegations"]
        errors = stats["errors"]
        
        if delegations == 0:
            continue
            
        error_rate = errors / delegations
        worker_key = worker_name.lower()
        if worker_key not in workers_config:
            workers_config[worker_key] = {}
            
        current_model = workers_config[worker_key].get("model", "gemini-3.1-pro-high")
        
        print(f"📊 {worker_name} -> Délégations: {delegations}, Erreurs: {errors} (Taux: {error_rate:.1%})")

        # 1. OPTIMISATION DES BUDGETS (Model Tiering)
        try:
            current_idx = model_ladder.index(current_model)
        except ValueError:
            current_idx = len(model_ladder) - 1 # Par défaut, on le met au max si inconnu

        if error_rate == 0.0 and delegations >= 5:
            # Perfection ! On peut tenter de réduire les coûts en prenant un modèle moins cher.
            if current_idx > 0:
                new_model = model_ladder[current_idx - 1]
                print(f"  [BUDGET] 📉 Downgrade du modèle pour {worker_name}: {current_model} -> {new_model} (Économie de tokens)")
                workers_config[worker_key]["model"] = new_model
                changes_made = True
                
        elif error_rate > 0.2:
            # Trop d'erreurs ! On doit escalader vers un modèle plus intelligent.
            if current_idx < len(model_ladder) - 1:
                new_model = model_ladder[current_idx + 1]
                print(f"  [BUDGET] 📈 Escalade du modèle pour {worker_name}: {current_model} -> {new_model} (Amélioration qualité)")
                workers_config[worker_key]["model"] = new_model
                changes_made = True

        # 2. OPTIMISATION DES TIMEOUTS ET RETRIES
        if error_rate > 0.3:
            current_retries = workers_config.get("default_max_retries", 3)
            new_retries = current_retries + 1
            print(f"  [RELIABILITY] 🔧 Augmentation des retries globaux: {current_retries} -> {new_retries}")
            workers_config["default_max_retries"] = new_retries
            
            # Si c'est le ShellExecutor, on augmente potentiellement son timeout
            if worker_name == "ShellExecutor":
                current_timeout = workers_config[worker_key].get("timeout_seconds", 30)
                if current_timeout < 120:
                    workers_config[worker_key]["timeout_seconds"] = current_timeout + 15
                    print(f"  [THRESHOLDS] ⏳ Augmentation du timeout ShellExecutor -> {current_timeout + 15}s")
            changes_made = True


        # 4. OPTIMISATION DE L'INGENIERIE DES PROMPTS (Prompt Refinement)
        if error_rate > 0.4 and worker_name == "Coder":
            # Si le Coder échoue très souvent, on durcit son prompt système pour être plus strict
            print(f"  [PROMPTS] 📝 Renforcement du prompt système pour {worker_name} suite à de nombreux échecs.")
            workers_config[worker_key]["system_prompt_addition"] = "CRITICAL: You MUST write syntactically correct code. Double check all indentation and imports before using the write_file tool."
            changes_made = True
            
        # 5. OPTIMISATION DES SKILLS (ex: WebSearcher)
        if worker_name == "WebSearcher":
            current_depth = workers_config[worker_key].get("max_search_depth", 3)
            if error_rate == 0.0 and delegations > 5 and current_depth > 1:
                # Si le WebSearcher est très efficace, on réduit sa profondeur de recherche pour économiser des tokens
                print(f"  [SKILLS] ⚡ Réduction de la profondeur de recherche WebSearcher: {current_depth} -> {current_depth - 1}")
                workers_config[worker_key]["max_search_depth"] = current_depth - 1
                changes_made = True

    # 3. OPTIMISATION DE L'ORCHESTRATEUR
    total_errors = sum(m["errors"] for m in metrics.values())
    total_dels = sum(m["delegations"] for m in metrics.values())
    
    if total_dels > 10:
        global_error_rate = total_errors / total_dels
        orch_config = config.get("orchestrator", {})
        
        if global_error_rate > 0.25 and orch_config.get("max_stall_count", 3) < 5:
            print("  [ORCHESTRATOR] 🧠 Augmentation de la tolérance au Stall (max_stall_count -> 4) en raison d'un fort taux d'échec global.")
            orch_config["max_stall_count"] = 4
            changes_made = True


        # 6. OPTIMISATION DES CONFIGURATIONS ET OPTIONS GLOBALES (Flags, Limits, Policies)
        # Option Coder : Tolérance au linting AST
        if worker_name == "Coder" and error_rate > 0.3:
            # Si le codeur échoue beaucoup, c'est peut-être que l'AST strict bloque des écritures valides (ex: pseudo-code)
            # ou à l'inverse qu'il n'est pas activé.
            current_lint = workers_config[worker_key].get("auto_lint_patch", True)
            if current_lint:
                print("  [OPTIONS] ⚙️ Désactivation de 'auto_lint_patch' pour le Coder (assouplissement des règles).")
                workers_config[worker_key]["auto_lint_patch"] = False
                changes_made = True

        # Option FileReader : Limite de contexte
        if worker_name == "FileReader" and error_rate > 0.1:
            current_limit = workers_config[worker_key].get("max_read_lines", 500)
            if current_limit > 100:
                print(f"  [OPTIONS] 📉 Réduction de 'max_read_lines' pour le FileReader ({current_limit} -> {current_limit - 100}) pour éviter de saturer le contexte.")
                workers_config[worker_key]["max_read_lines"] = current_limit - 100
                changes_made = True

    # Option Globale : Politique d'escalade
    if total_dels > 5 and (total_errors / total_dels) > 0.5:
        # Si le système échoue plus d'une fois sur deux, les tâches sont impossibles ou l'environnement est cassé.
        # On désactive l'escalade vers les modèles payants pour arrêter de gaspiller de l'argent.
        current_policy = config.get("model_escalation_policy", True)
        if current_policy:
            print("  [OPTIONS] 🛑 Taux d'échec global critique (>50%). Désactivation de 'model_escalation_policy' pour stopper l'hémorragie financière.")
            config["model_escalation_policy"] = False
            changes_made = True

    if changes_made:
        save_config(config)
        print("✅ Configuration mise à jour automatiquement par l'Optimizer !")
    else:
        print("✅ Le système est déjà optimal. Aucune modification de la configuration requise.")

if __name__ == "__main__":
    optimize_system()

    # 4. OPTIMISATION DES SCRIPTS ET CRONS SYSTEMES
    # Si le système global a un taux d'erreur élevé, l'optimizer peut analyser les crons système
    # et potentiellement désactiver ou espacer les crons les plus gourmands ou instables.
    try:
        # Check system load to see if crons need adjusting
        load_avg = os.getloadavg()[0]
        if load_avg > 4.0:
            print(f"  [SYSTEM] ⚠️ Charge système très élevée ({load_avg:.2f}). L'optimizer recommande de vérifier les crons intensifs.")
            # Note: The actual modification of user crontabs is risky, so we log a strong recommendation
            # or we could write to a specific 'managed_crons.json' that a wrapper script reads.
            changes_made = True
    except Exception as e:
        print(f"  [SYSTEM] Impossible de vérifier la charge système: {e}")
