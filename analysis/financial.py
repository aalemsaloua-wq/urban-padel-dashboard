# ==============================================================
#  analysis/financial.py
#  Calculs financiers : CA mensuel, MoM, YoY, EBITDA, anomalies.
# ==============================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from config.mapping import (
    SEUIL_HAUSSE_CHARGES, SEUIL_BAISSE_CA,
    SEUIL_BAISSE_MARGE, SEUIL_ECART_CAISSE
)


# ──────────────────────────────────────────────
# ANALYSE CA
# ──────────────────────────────────────────────

def resume_ca_mensuel(ca_journalier: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège le CA journalier par mois.

    Colonnes résultat :
        annee, mois, date, total_ca, total_especes, total_cb,
        total_paypal, total_cheque, total_virement,
        nb_jours, ca_mom_pct, ca_yoy_pct
    """
    if ca_journalier.empty:
        return pd.DataFrame()

    agg = ca_journalier.groupby(["annee", "mois"]).agg(
        total_ca        =("total",    "sum"),
        total_especes   =("espece",   "sum"),
        total_cb        =("cb",       "sum"),
        total_paypal    =("paypal",   "sum"),
        total_cheque    =("cheque",   "sum"),
        total_virement  =("virement", "sum"),
        nb_jours        =("date",     "count"),
    ).reset_index()

    agg["date"] = pd.to_datetime(
        agg["annee"].astype(str) + "-" + agg["mois"].astype(str).str.zfill(2) + "-01"
    )
    agg = agg.sort_values("date").reset_index(drop=True)

    # Variations MoM (mois sur mois) et YoY (année sur année)
    agg["ca_mom_pct"] = agg["total_ca"].pct_change(1)  * 100
    agg["ca_yoy_pct"] = agg["total_ca"].pct_change(12) * 100

    return agg


def mix_paiements_mensuel(ca_journalier: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule la part de chaque mode de paiement par mois, en % du total.
    """
    if ca_journalier.empty:
        return pd.DataFrame()

    agg = ca_journalier.groupby(["annee", "mois"]).agg(
        espece   =("espece",   "sum"),
        cb       =("cb",       "sum"),
        paypal   =("paypal",   "sum"),
        cheque   =("cheque",   "sum"),
        virement =("virement", "sum"),
        total    =("total",    "sum"),
    ).reset_index()

    for col in ["espece", "cb", "paypal", "cheque", "virement"]:
        agg[f"{col}_pct"] = (agg[col] / agg["total"].replace(0, np.nan) * 100).round(1)

    agg["date"] = pd.to_datetime(
        agg["annee"].astype(str) + "-" + agg["mois"].astype(str).str.zfill(2) + "-01"
    )
    return agg.sort_values("date").reset_index(drop=True)


# ──────────────────────────────────────────────
# ANALYSE CPC
# ──────────────────────────────────────────────

def analyser_cpc(cpc_mensuel: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute les colonnes MoM et YoY pour les métriques clés du CPC.
    """
    if cpc_mensuel.empty:
        return pd.DataFrame()

    df = cpc_mensuel.copy().sort_values("date")

    for metrique in ["total_ca", "total_charges", "resultat_exploitation",
                     "ebitda", "marge_ebitda"]:
        if metrique in df.columns:
            df[f"{metrique}_mom"] = df[metrique].pct_change(1)  * 100
            df[f"{metrique}_yoy"] = df[metrique].pct_change(12) * 100

    return df.reset_index(drop=True)


def comparaison_mom_lignes(cpc_mensuel_brut: list) -> pd.DataFrame:
    """
    Tableau comparatif ligne par ligne entre les 2 derniers mois disponibles.

    Colonnes résultat :
        section, ligne, mois_courant, valeur_courante,
        mois_precedent, valeur_precedente, variation_abs, variation_pct
    """
    if len(cpc_mensuel_brut) < 2:
        return pd.DataFrame()

    dernier  = cpc_mensuel_brut[-1]
    precedent = cpc_mensuel_brut[-2]

    # Rassembler tous les labels présents dans l'un ou l'autre mois
    tous_labels = set()
    for section in ["produits", "charges"]:
        tous_labels.update(dernier.get(section, {}).keys())
        tous_labels.update(precedent.get(section, {}).keys())

    def trouver(rec, label):
        if label in rec.get("produits", {}):
            return "Produits", rec["produits"][label]
        if label in rec.get("charges", {}):
            return "Charges", rec["charges"][label]
        return "Autre", 0.0

    lignes = []
    for label in sorted(tous_labels):
        section, val_actuel = trouver(dernier, label)
        _,       val_prec   = trouver(precedent, label)

        val_actuel = val_actuel or 0.0
        val_prec   = val_prec   or 0.0

        if val_actuel == 0 and val_prec == 0:
            continue

        var_abs = val_actuel - val_prec
        var_pct = (var_abs / val_prec * 100) if val_prec != 0 else None

        lignes.append({
            "section":           section,
            "ligne":             label,
            "mois_courant":      f"{dernier['mois']:02d}/{dernier['annee']}",
            "valeur_courante":   val_actuel,
            "mois_precedent":    f"{precedent['mois']:02d}/{precedent['annee']}",
            "valeur_precedente": val_prec,
            "variation_abs":     var_abs,
            "variation_pct":     var_pct,
        })

    return pd.DataFrame(lignes)


# ──────────────────────────────────────────────
# DÉTECTION D'ANOMALIES
# ──────────────────────────────────────────────

def detecter_anomalies(
    cpc_analyse:   pd.DataFrame,
    ca_mensuel:    pd.DataFrame,
    crosscheck:    pd.DataFrame,
) -> list:
    """
    Détecte automatiquement les anomalies financières.

    Retourne une liste de dicts :
        {
            "type":      str   (HAUSSE_CHARGES / BAISSE_MARGE / BAISSE_CA / ECART_CAISSE),
            "severite":  str   (HIGH / MEDIUM),
            "periode":   str,
            "message":   str,
            "valeur":    float,
        }
    """
    anomalies = []

    # 1. Hausse anormale des charges MoM
    if not cpc_analyse.empty and "total_charges_mom" in cpc_analyse.columns:
        hausse = cpc_analyse[
            cpc_analyse["total_charges_mom"].notna() &
            (cpc_analyse["total_charges_mom"] > SEUIL_HAUSSE_CHARGES)
        ]
        for _, row in hausse.iterrows():
            anomalies.append({
                "type":     "HAUSSE_CHARGES",
                "severite": "HIGH" if row["total_charges_mom"] > 40 else "MEDIUM",
                "periode":  row["date"].strftime("%m/%Y"),
                "message":  f"Charges en hausse de +{row['total_charges_mom']:.1f}% vs mois précédent",
                "valeur":   row.get("total_charges", 0),
            })

    # 2. Baisse de marge EBITDA MoM
    if not cpc_analyse.empty and "marge_ebitda_mom" in cpc_analyse.columns:
        baisses = cpc_analyse[
            cpc_analyse["marge_ebitda_mom"].notna() &
            (cpc_analyse["marge_ebitda_mom"] < -SEUIL_BAISSE_MARGE)
        ]
        for _, row in baisses.iterrows():
            anomalies.append({
                "type":     "BAISSE_MARGE",
                "severite": "HIGH" if row["marge_ebitda_mom"] < -25 else "MEDIUM",
                "periode":  row["date"].strftime("%m/%Y"),
                "message":  f"Marge EBITDA en baisse de {row['marge_ebitda_mom']:.1f}% vs mois précédent",
                "valeur":   row.get("marge_ebitda", 0),
            })

    # 3. Forte baisse du CA MoM
    if not ca_mensuel.empty and "ca_mom_pct" in ca_mensuel.columns:
        baisses_ca = ca_mensuel[
            ca_mensuel["ca_mom_pct"].notna() &
            (ca_mensuel["ca_mom_pct"] < -SEUIL_BAISSE_CA)
        ]
        for _, row in baisses_ca.iterrows():
            anomalies.append({
                "type":     "BAISSE_CA",
                "severite": "HIGH" if row["ca_mom_pct"] < -30 else "MEDIUM",
                "periode":  row["date"].strftime("%m/%Y"),
                "message":  f"CA en baisse de {row['ca_mom_pct']:.1f}% vs mois précédent",
                "valeur":   row.get("total_ca", 0),
            })

    # 4. Écarts de caisse importants
    if not crosscheck.empty:
        gros_ecarts = crosscheck[
            crosscheck["statut"].isin(["🔴 CA > Caisses", "🟡 Caisses > CA"]) &
            (crosscheck["ecart"].abs() > SEUIL_ECART_CAISSE)
        ]
        for _, row in gros_ecarts.iterrows():
            date_str = row["date"].strftime("%d/%m/%Y") if hasattr(row["date"], "strftime") else str(row["date"])
            anomalies.append({
                "type":     "ECART_CAISSE",
                "severite": "HIGH" if abs(row["ecart"]) > 2000 else "MEDIUM",
                "periode":  date_str,
                "message":  (
                    f"Écart de {row['ecart']:+.0f} DH — "
                    f"CA espèces={row['ca_especes']:.0f} / "
                    f"Total caisses={row['total_caisses']:.0f}"
                ),
                "valeur":   row["ecart"],
            })

    # Trier : HIGH d'abord, puis MEDIUM
    anomalies.sort(key=lambda x: 0 if x["severite"] == "HIGH" else 1)
    return anomalies
