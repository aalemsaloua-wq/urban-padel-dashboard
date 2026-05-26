# ==============================================================
#  extractors/ca_extractor.py
#  Lit le fichier Reporting CA et extrait les données journalières.
#  Structure attendue : feuilles "CA JANVIER 2026", "CA FEVRIER 2026"...
#  Chaque feuille contient : DATE | CB | ESPECE | PAYPAL | CHQ | VIREMENT | TOTAL
# ==============================================================

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from extractors.utils import nettoyer_valeur, lire_date, extraire_mois_annee


# Mots qui indiquent qu'une feuille est une feuille DÉTAIL (à ignorer ici)
MOTS_DETAIL = ["DETAIL", "DETAILE", "DETAILLE", "DÉTAIL", "DÉTAILLE"]

# Mois français pour détecter les feuilles récapitulatives
MOIS_DETECTABLES = [
    "JANV", "FEVR", "FÉVRIER", "MARS", "AVRI", "MAI", "JUIN",
    "JUIL", "AOUT", "AOÛT", "SEPT", "OCTO", "NOVE", "DECE"
]


def _est_feuille_recap(nom: str) -> bool:
    """
    Retourne True si la feuille est une feuille récapitulative CA
    (pas une feuille DETAIL, pas une feuille ancienne sans structure CB/ESPECE).
    """
    nom_upper = nom.upper().strip()
    # Exclure les feuilles DETAIL
    for mot in MOTS_DETAIL:
        if mot in nom_upper:
            return False
    # Exclure les très vieilles feuilles sans format CB/ESPECE
    feuilles_exclues = [
        "CA JUIN", "CA JUILLET", "CA AOUT DETAILLE",
        "CA SEPT 2024", "CA SEPT DETAILLE"
    ]
    for excl in feuilles_exclues:
        if nom_upper.startswith(excl.upper()):
            return False
    # Doit contenir un mois reconnaissable
    for mois in MOIS_DETECTABLES:
        if mois in nom_upper:
            return True
    return False


def _trouver_ligne_entete(lignes: list) -> tuple:
    """
    Cherche la ligne qui contient CB et ESPECE (l'en-tête du tableau).
    Retourne (index_ligne, dict_colonnes) où dict_colonnes mappe
    le nom de la colonne à son index.
    
    Si introuvable, retourne (None, {}).
    """
    for i, ligne in enumerate(lignes):
        valeurs = []
        for cellule in ligne:
            if cellule is not None:
                valeurs.append(str(cellule).upper().strip())
        
        # L'en-tête doit contenir CB et ESPECE
        if "CB" in valeurs and "ESPECE" in valeurs:
            colonnes = {}
            for j, cellule in enumerate(ligne):
                if cellule is None:
                    continue
                cle = str(cellule).upper().strip()
                if cle == "CB":
                    colonnes["cb"] = j
                elif cle == "ESPECE":
                    colonnes["espece"] = j
                elif cle == "PAYPAL":
                    colonnes["paypal"] = j
                elif cle in ("CHQ", "CHEQUE", "CHÈQUE"):
                    colonnes["cheque"] = j
                elif cle == "VIREMENT":
                    colonnes["virement"] = j
                elif cle == "TOTAL":
                    colonnes["total"] = j
            return i, colonnes
    
    return None, {}


def _lire_feuille_recap(ws, nom_feuille: str) -> list:
    """
    Lit une feuille récapitulative et retourne une liste de dictionnaires,
    un par jour avec des données.
    """
    lignes = list(ws.iter_rows(values_only=True))
    idx_entete, colonnes = _trouver_ligne_entete(lignes)
    
    if idx_entete is None:
        print(f"   ⚠  {nom_feuille} : colonnes CB/ESPECE introuvables — feuille ignorée")
        return []
    
    if "total" not in colonnes:
        print(f"   ⚠  {nom_feuille} : colonne TOTAL introuvable — feuille ignorée")
        return []
    
    enregistrements = []
    for ligne in lignes[idx_entete + 1:]:
        # Chercher la date dans les 4 premières colonnes
        date_val = None
        for k in range(min(4, len(ligne))):
            date_val = lire_date(ligne[k])
            if date_val is not None:
                break
        
        if date_val is None:
            continue  # Ligne sans date valide → ignorer
        
        def get_col(nom_col):
            """Lit une colonne par son nom si elle existe."""
            if nom_col in colonnes:
                idx = colonnes[nom_col]
                if idx < len(ligne):
                    return nettoyer_valeur(ligne[idx])
            return None
        
        total = get_col("total")
        if total is None or total == 0:
            continue  # Jour sans chiffre d'affaires → ignorer
        
        enregistrements.append({
            "date":     date_val,
            "feuille":  nom_feuille,
            "cb":       get_col("cb"),
            "espece":   get_col("espece"),
            "paypal":   get_col("paypal"),
            "cheque":   get_col("cheque"),
            "virement": get_col("virement"),
            "total":    total,
        })
    
    return enregistrements


def extraire_ca(chemin_fichier: str) -> dict:
    """
    FONCTION PRINCIPALE — Extrait toutes les données CA journalières.
    
    Paramètre :
        chemin_fichier : chemin complet vers le fichier Excel CA
    
    Retourne un dictionnaire :
        {
            "donnees":  liste de dicts (un par jour),
            "nb_jours": nombre total de jours extraits,
            "erreurs":  liste de messages d'erreur
        }
    
    Chaque dict "donnees" contient :
        date, feuille, cb, espece, paypal, cheque, virement, total
    """
    print(f"\n📂 Lecture du Reporting CA...")
    print(f"   Fichier : {os.path.basename(chemin_fichier)}")
    
    try:
        wb = openpyxl.load_workbook(chemin_fichier, read_only=True, data_only=True)
    except FileNotFoundError:
        return {"donnees": [], "nb_jours": 0, "erreurs": [f"Fichier introuvable : {chemin_fichier}"]}
    except Exception as e:
        return {"donnees": [], "nb_jours": 0, "erreurs": [f"Impossible d'ouvrir le fichier : {e}"]}
    
    toutes_donnees = []
    erreurs = []
    feuilles_lues = 0
    
    for nom_feuille in wb.sheetnames:
        if not _est_feuille_recap(nom_feuille):
            continue  # Feuille DETAIL ou non reconnue → ignorer silencieusement
        
        try:
            ws = wb[nom_feuille]
            donnees = _lire_feuille_recap(ws, nom_feuille)
            if donnees:
                print(f"   ✅ {nom_feuille.strip()} → {len(donnees)} jours")
                toutes_donnees.extend(donnees)
                feuilles_lues += 1
        except Exception as e:
            msg = f"Erreur sur la feuille '{nom_feuille}' : {e}"
            erreurs.append(msg)
            print(f"   ❌ {msg}")
    
    wb.close()
    
    print(f"   → Total : {len(toutes_donnees)} jours extraits depuis {feuilles_lues} feuilles")
    
    if not toutes_donnees:
        erreurs.append(
            "Aucune donnée CA extraite. Vérifiez que vos feuilles contiennent "
            "bien les colonnes CB et ESPECE."
        )
    
    return {
        "donnees":  toutes_donnees,
        "nb_jours": len(toutes_donnees),
        "erreurs":  erreurs
    }
