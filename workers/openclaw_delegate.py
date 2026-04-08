from typing import Dict, Any
import time
import hashlib
from openclaw_client import OpenClawClient
from swarm_memory import AdaptiveRateLimiter

rate_limiter = AdaptiveRateLimiter()

class OpenClawDelegateWorker:
    def __init__(self, agent_id: str, config_path: str = "config.yaml"):
        self.agent_id = agent_id
        self.client = OpenClawClient(config_path=config_path)

    def execute(self, state: Any) -> Dict[str, Any]:
        instruction = state.get("progress_ledger", {}).get("instruction", "")
        task_ledger = state.get("task_ledger", {})
        
        goal = task_ledger.get("goal", "")
        plan = task_ledger.get("plan", [])
        
        # Adaptive Rate Limiting
        provider = "antigravity-proxy" # Simplification for now
        delay = rate_limiter.get_delay_for_provider(provider)
        if delay > 0:
            print(f"[{self.agent_id}] Adaptive Rate Limiter: Sleeping for {delay:.1f}s to respect {provider} limits.")
            time.sleep(delay)
            
        messages = [
            {"role": "user", "content": f"""Global Goal: {goal}
Current Plan: {plan}
Your specific instruction: {instruction}"""}
        ]
        
        try:
            result = self.client.chat_with_agent(
                worker_name=self.agent_id,
                agent_id=self.agent_id,
                messages=messages
            )
            # Vérifier si OpenClaw a renvoyé une erreur 429
            if not result.get("success") and result.get("error") and "429" in result["error"]:
                raise Exception(result["error"])
                
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower() or "exhausted" in error_str.lower():
                print(f"[{self.agent_id}] ⚠️ 429 Detected. Teaching AdaptiveRateLimiter.")
                rate_limiter.record_429(provider, error_msg=error_str)
                
            # Compute a hash of the failed instruction to prevent infinite retry loops on identical failures of the failed instruction to prevent infinite retry loops on identical failures
            task_hash = hashlib.md5(instruction.encode('utf-8')).hexdigest()
            
            result = {
                "worker_name": self.agent_id,
                "content": f"FAILED (Agent Error: {error_str})",
                "metadata": {},
                "success": False,
                "error": error_str,
                "tokens_used": 0,
                "failed_task_hash": task_hash
            }
        
        return {"workers_output": [result]}

class OpenClawDebateWorker:
    def __init__(self, config_path: str = "config.yaml"):
        self.client = OpenClawClient(config_path=config_path)

    def execute(self, state: Any) -> Dict[str, Any]:
        instruction = state.get("progress_ledger", {}).get("instruction", "")
        
        # Debater logic could go here
        messages = [{"role": "user", "content": instruction}]
        
        result = self.client.chat_with_agent(
            worker_name="debate_room",
            agent_id="architect", # default fallback
            messages=messages
        )
        return {"workers_output": [result]}
