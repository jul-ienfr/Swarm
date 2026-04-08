import subprocess
from typing import Dict, Any

class VideoAssembler:
    """
    Worker LangGraph : Assemble les assets en vidéo 4K.
    S'exécute sur le Ryzen 7 7700 (Cerveau) mais déporte le calcul sur le Ryzen 9 7950X via SSH.
    """
    def __init__(self, config: Dict[str, Any]):
        # L'IP de votre Nœud Monteur (le 7950X)
        self.encoder_ip = config.get("encoder_ip", "192.168.1.XX")
        self.encoder_user = config.get("encoder_user", "julien") # L'utilisateur Ubuntu du 7950X
        self.nas_path = "/mnt/truenas" # Le dossier partagé commun

    def execute(self, state: Any) -> Dict[str, Any]:
        """Interface standard pour le Superviseur global Magentic-One."""
        instruction = state.get("progress_ledger", {}).get("instruction", "")

        import re
        import time
        # On extrait le project_id de l'instruction du superviseur
        match = re.search(r'tiktok_\d+', instruction)
        project_id = match.group(0) if match else f"tiktok_{int(time.time())}"

        print(f"\n[VideoAssembler] 🎬 Ordre du Superviseur reçu pour le projet : {project_id}")

        try:
            result = self.invoke(project_id, {})
            return {
                "workers_output": [{
                    "worker_name": "video-assembler",
                    "content": f"Opération terminée. Statut: {result['status']}. Fichier: {result.get('output_file', '')}\nLogs: {result.get('ffmpeg_logs', result.get('details', ''))}",
                    "metadata": {"project_id": project_id},
                    "success": result["status"] == "success",
                    "error": result.get("error_type"),
                    "tokens_used": 0
                }]
            }
        except Exception as e:
            return {
                "workers_output": [{
                    "worker_name": "video-assembler",
                    "content": "",
                    "metadata": {"project_id": project_id},
                    "success": False,
                    "error": str(e),
                    "tokens_used": 0
                }]
            }

    def invoke(self, project_id: str, assets: Dict[str, Any]) -> Dict[str, Any]:
        """
        project_id: Le nom du dossier du projet en cours (ex: 'tiktok_trou_noir_01')
        assets: Dictionnaire contenant les noms des images et voix générées.
        """
        print(f"[VideoAssembler] Début du montage déporté pour le projet : {project_id}")

        # Le chemin de travail sur le TrueNAS (identique pour le 7700 et le 7950X)
        work_dir = f"{self.nas_path}/projets/{project_id}"
        output_file = f"{work_dir}/final_video.mp4"

        # Exemple simple de commande FFmpeg :
        # Prendre 1 image fixe, la looper sur la durée de la voix-off, et sortir un mp4.
        # Dans un vrai scénario, on génère un fichier texte complexe pour concaténer plusieurs scènes.
        image_path = f"{work_dir}/scene1.jpg"
        audio_path = f"{work_dir}/voix.wav"

        # La commande FFmpeg brute (4K vertical, encodage x264 ultra qualité)
        ffmpeg_cmd = (
            f"ffmpeg -y -loop 1 -framerate 30 -i {image_path} -i {audio_path} "
            f"-c:v libx264 -preset veryfast -crf 18 -tune stillimage "
            f"-c:a aac -b:a 192k -shortest -pix_fmt yuv420p "
            f"-vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920' "
            f"{output_file}"
        )

        # On emballe la commande dans un appel SSH
        print(f"[VideoAssembler] Envoi de l'ordre d'encodage au 7950X ({self.encoder_ip})...")
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no", # Ignore les alertes de clé au 1er lancement
            f"{self.encoder_user}@{self.encoder_ip}",
            ffmpeg_cmd
        ]

        try:
            # Exécution bloquante : le Superviseur attend que le 7950X ait fini les 40s d'encodage
            result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)

            print(f"[VideoAssembler] Succès ! Vidéo disponible sur le TrueNAS : {output_file}")
            return {
                "status": "success",
                "output_file": output_file,
                "ffmpeg_logs": result.stderr # FFmpeg crache ses logs dans stderr, même en cas de succès
            }

        except subprocess.CalledProcessError as e:
            print(f"[VideoAssembler] ERREUR FFmpeg sur le 7950X : {e.stderr}")
            return {
                "status": "error",
                "error_type": "ffmpeg_failure",
                "details": e.stderr
            }
