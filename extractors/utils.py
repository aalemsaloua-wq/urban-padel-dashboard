# ==============================================================
#  extractors/utils.py
#  Fonctions utilitaires partagées entre tous les extracteurs.
#  Vous n'avez pas besoin de modifier ce fichier.
# ==============================================================

import re
import datetime
from typing import Optional
import sys
import os

# Ajouter le dossier parent au chemin Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.mapping import MOIS_FR


def nettoyer_valeur(valeur) -> Optional[float]:
    """
    Convertit n'importe quelle valeur en nombre décimal.
    Retourne None si impossible (ex: texte, cellule vide, #REF!).
    
    Exemples :
        "1 500,50 DH" → 1500.5
        "#REF!"        → None
        ""             → None
        3500           → 3500.0
    """
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        if valeur != valeur:  # NaN
            return None
        return float(valeur)
    if isinstance(valeur, str):
        v = valeur.strip()
        # Valeurs d'erreur Excel à ignorer
        erreurs = ["#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "-", "", " "]
        if v in erreurs:
            return None
        # Nettoyer : espaces, virgules décimales, symboles monétaires
        v = v.replace(" ", "").replace("\xa0", "")
        v = v.replace(",", ".").replace("DH", "").replace("dh", "")
        v = v.replace("MAD", "").replace("€", "").replace("$", "")
        # Supprimer les points de milliers (ex: 1.500 → 1500)
        # mais garder le point décimal si c'est le seul
        if v.count(".") > 1:
            v = v.replace(".", "", v.count(".") - 1)
        try:
            return float(v)
        except ValueError:
            return None
    return None


def lire_date(valeur) -> Optional[datetime.date]:
    """
    Convertit une valeur en date Python.
    Gère les dates Excel, les chaînes de caractères, etc.
    """
    if valeur is None:
        return None
    if isinstance(valeur, datetime.datetime):
        return valeur.date()
    if isinstance(valeur, datetime.date):
        return valeur
    if isinstance(valeur, str):
        v = valeur.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(v, fmt).date()
            except ValueError:
                continue
    return None


def extraire_mois_annee(nom_feuille: str) -> Optional[tuple]:
    """
    Extrait (mois, annee) depuis un nom de feuille Excel.
    
    Exemples testés :
        "012026"          → (1, 2026)
        "012026 "         → (1, 2026)   ← espace en fin
        "JANVIER 2026"    → (1, 2026)
        "CPC MARS  2026"  → (3, 2026)
        "fevrier 2026"    → (2, 2026)
        "CA AVRIL  2026"  → (4, 2026)
    Retourne None si impossible à détecter.
    """
    nom = nom_feuille.strip()

    # Format numérique : "012026" ou "01 2026"
    m = re.match(r"^(\d{2})\s*(\d{4})\s*$", nom)
    if m:
        mois = int(m.group(1))
        annee = int(m.group(2))
        if 1 <= mois <= 12 and 2000 <= annee <= 2100:
            return mois, annee

    # Format textuel : "JANVIER 2026", "CA MARS 2026", etc.
    nom_upper = nom.upper()
    annee_m = re.search(r"(\d{4})", nom_upper)
    if annee_m:
        annee = int(annee_m.group(1))
        if 2000 <= annee <= 2100:
            for nom_mois, num_mois in MOIS_FR.items():
                if nom_mois in nom_upper:
                    return num_mois, annee

    return None


def verifier_fichier(chemin: str, nom_fichier: str) -> bool:
    """
    Vérifie qu'un fichier existe et affiche un message clair si non.
    """
    import os
    if not os.path.exists(chemin):
        print(f"\n❌ ERREUR : Fichier introuvable !")
        print(f"   Fichier attendu : {nom_fichier}")
        print(f"   Chemin cherché  : {chemin}")
        print(f"   ➤  Vérifiez que ce fichier est bien dans votre dossier 'data/'")
        print(f"   ➤  Vérifiez l'orthographe du nom dans config/mapping.py\n")
        return False
    return True
