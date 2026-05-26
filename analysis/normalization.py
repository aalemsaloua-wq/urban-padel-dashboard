# ==============================================================
#  analysis/normalization.py
#  Transforme les données brutes en tableaux propres (DataFrames).
#  Un DataFrame = un tableau comme Excel, avec lignes et colonnes.
# ==============================================================

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from config.mapping import SEUIL_ECART_CAISSE


def normaliser_ca_journalier(donnees_brutes: list) -> pd.DataFrame:
    """
    Transforme la liste de dicts CA en DataFrame propre.
    - Convertit les dates
    - Met les nombres en numérique
    - Supprime les doublons (garde le jour avec le total le plus élevé)
    - Ajoute colonnes année, mois, période
    
    Retourne un DataFrame vide si aucune donnée.
    """
    if not donnees_brutes:
        print("   ⚠  Aucune donnée CA à normaliser")
        return pd.DataFrame()
    
    df = pd.DataFrame(donnees_brutes)
    
    # Convertir les dates
    df["date"] = pd.to_datetime(df["date"])
    
    # Convertir les colonnes numériques
    for col in ["cb", "espece", "paypal", "cheque", "virement", "total"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
    
    # Supprimer les doublons de date : garder le total le plus élevé
    df = df.sort_values("total", ascending=False, na_position="last")
    df = df.drop_duplicates(subset="date", keep="first")
    df = df.sort_values("date").reset_index(drop=True)
    
    # Ajouter des colonnes utiles
    df["annee"]  = df["date"].dt.year
    df["mois"]   = df["date"].dt.month
    df["periode"] = df["date"].dt.to_period("M")
    
    print(f"   ✅ CA journalier : {len(df)} jours "
          f"({df['date'].min().strftime('%d/%m/%Y')} → {df['date'].max().strftime('%d/%m/%Y')})")
    return df


def normaliser_caisse_par_jour(entrees_ca: list, id_caisse: str) -> pd.DataFrame:
    """
    Agrège les entrées CA d'une caisse par jour (somme des débits).
    
    Retourne un DataFrame avec colonnes : date, caisse_w (ou caisse_b)
    """
    nom_col = f"caisse_{id_caisse.lower()}"
    
    if not entrees_ca:
        return pd.DataFrame(columns=["date", nom_col])
    
    df = pd.DataFrame(entrees_ca)
    df["date"]  = pd.to_datetime(df["date"])
    df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
    
    # Grouper par date et sommer
    agg = df.groupby("date")["debit"].sum().reset_index()
    agg.columns = ["date", nom_col]
    
    # Garder uniquement les jours avec un montant > 0
    agg = agg[agg[nom_col] > 0].reset_index(drop=True)
    
    print(f"   ✅ Caisse {id_caisse} agrégée : {len(agg)} jours avec entrées CA")
    return agg


def construire_tableau_crosscheck(
    ca_journalier: pd.DataFrame,
    caisse_w_agg: pd.DataFrame,
    caisse_b_agg: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit le tableau de contrôle espèces.
    
    Pour chaque jour où le CA a des espèces :
        Vérifie que : CA_espèces = Caisse_W + Caisse_B
    
    Retourne un DataFrame avec colonnes :
        date | ca_especes | caisse_w | caisse_b | total_caisses | ecart | statut
    
    Statuts possibles :
        ✅ OK           → écart ≤ seuil de tolérance
        🔴 CA > Caisses → le CA déclare plus d'espèces que les caisses
        🟡 Caisses > CA → les caisses ont plus que le CA
        ⬜ Pas de caisse → aucune entrée caisse ce jour
    """
    if ca_journalier.empty:
        return pd.DataFrame()
    
    # Base = jours du CA avec des espèces
    base = ca_journalier[["date", "espece"]].copy()
    base.columns = ["date", "ca_especes"]
    base = base[base["ca_especes"].notna() & (base["ca_especes"] > 0)].copy()
    
    if base.empty:
        print("   ⚠  Aucun jour avec espèces dans le CA")
        return pd.DataFrame()
    
    # Merger avec Caisse W
    if not caisse_w_agg.empty:
        base = base.merge(caisse_w_agg, on="date", how="left")
    else:
        base["caisse_w"] = np.nan
    
    # Merger avec Caisse B
    if not caisse_b_agg.empty:
        base = base.merge(caisse_b_agg, on="date", how="left")
    else:
        base["caisse_b"] = np.nan
    
    # Remplir les NaN par 0 pour le calcul
    base["caisse_w"] = base["caisse_w"].fillna(0)
    base["caisse_b"] = base["caisse_b"].fillna(0)
    
    # Calcul du total caisses et de l'écart
    base["total_caisses"] = base["caisse_w"] + base["caisse_b"]
    base["ecart"]         = base["ca_especes"] - base["total_caisses"]
    
    # Statut
    def calculer_statut(row):
        if row["total_caisses"] == 0:
            return "⬜ Pas de caisse"
        elif abs(row["ecart"]) <= SEUIL_ECART_CAISSE:
            return "✅ OK"
        elif row["ecart"] > SEUIL_ECART_CAISSE:
            return "🔴 CA > Caisses"
        else:
            return "🟡 Caisses > CA"
    
    base["statut"] = base.apply(calculer_statut, axis=1)
    base = base.sort_values("date").reset_index(drop=True)
    
    nb_ok      = (base["statut"] == "✅ OK").sum()
    nb_ecarts  = (base["statut"] != "✅ OK").sum()
    print(f"   ✅ Cross-check : {len(base)} jours analysés "
          f"({nb_ok} OK / {nb_ecarts} écarts)")
    return base


def normaliser_cpc_mensuel(mensuel_brut: list) -> pd.DataFrame:
    """
    Transforme la liste de CPC mensuels en DataFrame plat.
    
    Chaque ligne = 1 mois.
    Les produits et charges sont aplatis en colonnes séparées.
    """
    if not mensuel_brut:
        return pd.DataFrame()
    
    enregistrements = []
    for m in mensuel_brut:
        rec = {
            "annee":                  m["annee"],
            "mois":                   m["mois"],
            "feuille":                m["feuille"],
            "total_ca":               m.get("total_produits"),
            "total_charges":          m.get("total_charges"),
            "resultat_exploitation":  m.get("resultat_exploitation"),
            "cnss":                   m.get("cnss"),
            "resultat_net":           m.get("resultat_net"),
            "ebitda":                 m.get("ebitda"),
            "marge_ebitda":           m.get("marge_ebitda"),
        }
        # Aplatir les produits (préfixe "prod_")
        for k, v in (m.get("produits") or {}).items():
            rec[f"prod_{k}"] = v
        # Aplatir les charges (préfixe "chg_")
        for k, v in (m.get("charges") or {}).items():
            rec[f"chg_{k}"] = v
        
        enregistrements.append(rec)
    
    df = pd.DataFrame(enregistrements)
    
    # Créer une colonne "date" pour faciliter les calculs
    df["date"] = pd.to_datetime(
        df["annee"].astype(str) + "-" + df["mois"].astype(str).str.zfill(2) + "-01"
    )
    df = df.sort_values("date").reset_index(drop=True)
    
    print(f"   ✅ CPC mensuel : {len(df)} mois normalisés")
    return df
