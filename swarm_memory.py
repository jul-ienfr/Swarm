import json
import os
import time
from typing import Dict, Any

class AdaptiveRateLimiter:
    """
    Système d'apprentissage du Rate Limit (429) pour le Swarm.
    Calcule dynamiquement le délai d'attente optimal (Exponential Backoff + Jitter)
    plutôt que d'utiliser un délai codé en dur.
    """
    def __init__(self, memory_file: str = "/home/jul/.openclaw/workspace/langgraph-swarm/data/rate_limits_memory.json"):
        self.memory_file = memory_file
        self.default_ttl = 3600 * 12  # 12 heures pour l'exploration
        self.memory = self._load_memory()
        
    def _load_memory(self) -> Dict[str, Any]:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"providers": {}}
        
    def _save_memory(self):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, 'w') as f:
            json.dump(self.memory, f, indent=2)

    def record_429(self, provider: str, error_msg: str = ""):
        """
        Enregistre un crash 429. 
        Calcule la pénalité de manière adaptative.
        """
        now = time.time()
        provider_mem = self.memory["providers"].setdefault(provider, {
            "last_429_time": 0,
            "wait_until": 0,
            "current_penalty": 5, 
            "status": "throttled",
            "consecutive_429s": 0,
            "crash_history": [] # NOUVEAU: Historique multi-niveaux (Timeline)
        })
        
        # 1. Vérifier si l'API nous donne explicitement le temps d'attente
        explicit_wait = 0
        import re
        match = re.search(r'reset after (\d+)s', error_msg)
        if match:
            explicit_wait = int(match.group(1))

        # 2. Logique adaptative (Exponential Backoff)
        time_since_last = now - provider_mem["last_429_time"]
        if time_since_last < provider_mem["current_penalty"] * 3:
            provider_mem["consecutive_429s"] += 1
            provider_mem["current_penalty"] = min(provider_mem["current_penalty"] * 2, 120)
        else:
            provider_mem["consecutive_429s"] = 1
            provider_mem["current_penalty"] = 5
            
        final_wait = max(provider_mem["current_penalty"], explicit_wait)
        import random
        final_wait = final_wait * random.uniform(1.0, 1.2)
        
        provider_mem["last_429_time"] = now
        provider_mem["wait_until"] = now + final_wait
        provider_mem["status"] = "throttled"
        
        # 3. Mémorisation à long terme du crash (Timeline)
        from datetime import datetime
        crash_record = {
            "timestamp": now,
            "date": datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S'),
            "penalty_applied": round(final_wait, 1),
            "consecutive_crashes": provider_mem["consecutive_429s"]
        }
        
        # On garde les 100 derniers événements marquants pour que l'agent puisse analyser
        # ses propres limites passées s'il le souhaite.
        provider_mem.setdefault("crash_history", []).append(crash_record)
        if len(provider_mem["crash_history"]) > 100:
            provider_mem["crash_history"] = provider_mem["crash_history"][-100:]
            
        print(f"[RateLimiter] Enregistrement 429 historique. Pénalité: {final_wait:.1f}s")
        self._save_memory()

    def get_delay_for_provider(self, provider: str) -> float:
        """
        Calcule combien de temps le thread doit dormir avant de lancer une requête.
        """
        provider_mem = self.memory.get("providers", {}).get(provider)
        if not provider_mem:
            return 0.0 # Aucune limite connue
            
        now = time.time()
        wait_until = provider_mem.get("wait_until", 0)
        last_429_time = provider_mem.get("last_429_time", 0)
        
        if now < wait_until:
            return wait_until - now
            
        # Remise en question (Exploration) après 12h
        if now - last_429_time > self.default_ttl:
            # On NE SUPPRIME PAS la mémoire (pas de 'del').
            # On la conserve comme connaissance historique, mais on autorise le thread
            # à ignorer la pénalité cette fois-ci pour retester le proxy à pleine vitesse.
            # Si le proxy échoue à nouveau, record_429() reprendra le dessus avec le backoff.
            return 0.0
            
        # Pacing préventif (Exploitation) : très faible délai pour rester sous le radar
        return 1.0
