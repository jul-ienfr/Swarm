import subprocess
import time

def pause_miner_os_level(ip, user="julien"):
    """
    Sends a SIGSTOP signal to all known miner processes on a remote machine via SSH.
    This instantly freezes the miner in RAM without losing its current job state,
    freeing up the GPU/CPU for AI generation.
    """
    print(f"[{ip}] Congélation du minage (SIGSTOP)...")
    miners = ["srbminer-custom", "SRBMiner-MULTI", "t-rex", "lolMiner", "bzminer", "xmrig"]
    
    # Construct a command that finds the PIDs of these miners and sends SIGSTOP
    miner_grep = "\\|".join(miners)
    cmd = f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes {user}@{ip} 'pgrep -f \"{miner_grep}\" | xargs -r sudo kill -STOP'"
    
    try:
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        print(f"[{ip}] Aucun mineur actif trouvé ou erreur de permission.")
        return False

def resume_miner_os_level(ip, user="julien"):
    """
    Sends a SIGCONT signal to resume the frozen miner process.
    """
    print(f"[{ip}] Reprise du minage (SIGCONT)...")
    miners = ["srbminer-custom", "SRBMiner-MULTI", "t-rex", "lolMiner", "bzminer", "xmrig"]
    
    miner_grep = "\\|".join(miners)
    cmd = f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes {user}@{ip} 'pgrep -f \"{miner_grep}\" | xargs -r sudo kill -CONT'"
    
    try:
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        print(f"[{ip}] Impossible de reprendre le minage (processus non trouvé).")
        return False

# Example Usage
if __name__ == "__main__":
    # Test on Rig 1 (GPUs)
    pause_miner_os_level("192.168.31.9")
    time.sleep(2)
    resume_miner_os_level("192.168.31.9")
