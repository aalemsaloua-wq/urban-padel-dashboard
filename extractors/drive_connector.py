# ==============================================================
#  extractors/drive_connector.py
#  Telecharge les fichiers depuis Google Drive via Apps Script
#  ou via export direct. Aucune cle API necessaire.
# ==============================================================

import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def telecharger_fichiers_drive(config_path: str, dossier_data: str) -> dict:
    """
    Telecharge les fichiers depuis Google Drive.
    Utilise l export direct Google Sheets (fonctionne si fichiers partages).
    """
    try:
        import requests
    except ImportError:
        return {"succes": False,
                "messages": ["ERREUR: requests non installe. Lancez INSTALL.bat"],
                "fichiers": []}

    # Trouver drive_config.json
    if os.path.isdir(config_path):
        drive_cfg = os.path.join(config_path, "drive_config.json")
    elif os.path.basename(config_path) == "drive_config.json":
        drive_cfg = config_path
    else:
        drive_cfg = os.path.join(os.path.dirname(os.path.abspath(config_path)), "drive_config.json")

    if not os.path.exists(drive_cfg):
        return {"succes": False,
                "messages": [f"ERREUR: drive_config.json introuvable"],
                "fichiers": []}

    with open(drive_cfg, encoding="utf-8") as f:
        cfg = json.load(f)

    liens = cfg.get("liens_partage", {})
    if not liens:
        return {"succes": False,
                "messages": ["ERREUR: liens_partage manquants dans drive_config.json"],
                "fichiers": []}

    os.makedirs(dossier_data, exist_ok=True)
    messages = []
    fichiers = []
    session = requests.Session()

    for nom_local, url in liens.items():
        chemin_local = os.path.join(dossier_data, nom_local)
        try:
            messages.append(f"  Telechargement : {nom_local}...")

            # Essayer le telechargement direct
            resp = session.get(url, stream=True, timeout=60, allow_redirects=True)

            # Verifier si c est du HTML (page de connexion) au lieu d un fichier Excel
            content_type = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and "spreadsheet" in content_type or "excel" in content_type or "openxml" in content_type:
                # Fichier Excel recu directement
                pass
            elif resp.status_code == 200 and len(resp.content) > 5000:
                # Probablement ok si assez grand
                pass
            else:
                messages.append(f"  [ERREUR] {nom_local}: acces refuse (HTTP {resp.status_code})")
                messages.append(f"  Le fichier doit etre partage en mode 'Tout le monde avec le lien'")
                messages.append(f"  Demandez au proprietaire du fichier de le partager.")
                continue

            with open(chemin_local, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            taille = os.path.getsize(chemin_local) // 1024
            if taille < 5:
                os.remove(chemin_local)
                messages.append(f"  [ERREUR] {nom_local}: fichier trop petit ({taille} Ko) - acces refuse")
                continue

            messages.append(f"  [OK] {nom_local} ({taille} Ko)")
            fichiers.append(chemin_local)

        except requests.exceptions.Timeout:
            messages.append(f"  [ERREUR] {nom_local}: timeout - verifiez votre connexion")
        except requests.exceptions.ConnectionError:
            messages.append(f"  [ERREUR] {nom_local}: pas de connexion internet")
        except Exception as e:
            messages.append(f"  [ERREUR] {nom_local}: {e}")

    # Succes si au moins 1 fichier telecharge
    succes = len(fichiers) > 0
    if succes:
        messages.append(f"[OK] Synchronisation reussie - {len(fichiers)} fichiers mis a jour")
    elif len(fichiers) > 0:
        messages.append(f"[ATTENTION] {len(fichiers)}/{len(liens)} fichiers synchronises")
        messages.append(f"Pour les fichiers manquants: demandez au proprietaire de les partager")
        messages.append(f"En attendant, les anciens fichiers locaux seront utilises")
    else:
        messages.append(f"[ERREUR] Aucun fichier telecharge.")
        messages.append(f"Solution: demandez au proprietaire de partager les fichiers Drive")
        messages.append(f"OU copiez manuellement vos fichiers Excel dans le dossier data\\")

    return {"succes": succes, "messages": messages, "fichiers": fichiers}


def verifier_config_drive(dossier_projet: str) -> dict:
    drive_cfg = os.path.join(dossier_projet, "drive_config.json")
    if not os.path.exists(drive_cfg):
        return {"ok": False, "message": "drive_config.json absent.", "manquants": []}
    try:
        with open(drive_cfg, encoding="utf-8") as f:
            cfg = json.load(f)
        liens = cfg.get("liens_partage", {})
        if not liens:
            return {"ok": False, "message": "liens_partage manquants.", "manquants": []}
        return {"ok": True, "message": f"Drive configure ({len(liens)} fichiers).", "manquants": []}
    except Exception as e:
        return {"ok": False, "message": f"drive_config.json invalide: {e}", "manquants": []}
