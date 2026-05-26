# ==============================================================
#  config/mapping.py
#  Fichier de configuration — Modifiez ici si vos colonnes
#  ont des noms différents, SANS toucher au reste du code.
# ==============================================================

# ------------------------------------------------------------------
# NOMS DE VOS FICHIERS EXCEL (à placer dans le dossier data/)
# ------------------------------------------------------------------
FICHIER_CA        = "UP_PHARMA_REPORTING_CA_2026.xlsx"
FICHIER_CAISSE_W  = "2026_W_CAISSE_OMED SPORTS.xlsx"   # optionnel
FICHIER_CAISSE_B  = "2026_CAISSE_B_OMED_SPORTS.xlsx"   # optionnel

# Mettre True si les fichiers caisse sont disponibles, False sinon
CAISSES_DISPONIBLES = False
FICHIER_CPC       = "CPC_OMED_SPORTS.xlsx"

# ------------------------------------------------------------------
# REPORTING CA — Colonnes des feuilles récapitulatives
# (feuilles nommées "CA JANVIER 2026", "CA FEVRIER 2026", etc.)
# ------------------------------------------------------------------
# Le programme cherche automatiquement une ligne contenant "CB" et "ESPECE"
# puis lit les colonnes dans cet ordre.
CA_COL_CB        = "CB"
CA_COL_ESPECE    = "ESPECE"
CA_COL_PAYPAL    = "PAYPAL"
CA_COL_CHEQUE    = "CHQ"       # ou "CHEQUE"
CA_COL_VIREMENT  = "VIREMENT"
CA_COL_TOTAL     = "TOTAL"

# ------------------------------------------------------------------
# CAISSES W et B — Colonnes des feuilles mensuelles
# (feuilles nommées "012026", "022026", etc.)
# ------------------------------------------------------------------
# Le programme cherche automatiquement la ligne d'en-tête.
CAISSE_COL_CODE    = ["CODE", "W", "B"]    # noms possibles pour la colonne code
CAISSE_COL_DATE    = "DATE"
CAISSE_COL_DEBIT   = ["DÉBIT", "DEBIT", "R"]   # entrée cash (recette)
CAISSE_COL_CREDIT  = ["CRÉDIT", "CREDIT", "D"] # sortie cash (dépense)
CAISSE_COL_SOLDE   = "SOLDE"

# Codes qui signifient "entrée CA en espèces" dans la caisse
CAISSE_CODES_CA = ["CA", "ca"]

# ------------------------------------------------------------------
# CPC — Structure des feuilles mensuelles
# (feuilles nommées "JANVIER 2026", "MAI 2025", etc.)
# ------------------------------------------------------------------
# Le programme détecte automatiquement PRODUITS / CHARGES / TOTAL / RÉSULTAT

# Mots-clés pour détecter la section Produits
CPC_MOT_PRODUITS   = "PRODUITS D'EXPLOITATION"
# Mots-clés pour détecter la section Charges
CPC_MOT_CHARGES    = "CHARGES D'EXPLOITATION"
# Mots-clés pour détecter le résultat
CPC_MOT_RESULTAT   = "RESULTAT D'EXPLOITATION"
CPC_MOT_CNSS       = "CNSS"
CPC_MOT_RESULTAT_NET = "RESULTAT"

# ------------------------------------------------------------------
# SEUILS DE DÉTECTION D'ANOMALIES (modifiables)
# ------------------------------------------------------------------
# Écart maxi en DH entre CA espèces et total des caisses (tolérance)
SEUIL_ECART_CAISSE     = 50.0

# Hausse des charges en % MoM au-delà de laquelle c'est une anomalie
SEUIL_HAUSSE_CHARGES   = 20.0

# Baisse du CA en % MoM au-delà de laquelle c'est une anomalie
SEUIL_BAISSE_CA        = 15.0

# Baisse de marge EBITDA en % MoM au-delà de laquelle c'est une anomalie
SEUIL_BAISSE_MARGE     = 10.0

# ------------------------------------------------------------------
# MOIS EN FRANÇAIS (pour la détection dans les noms de feuilles)
# ------------------------------------------------------------------
MOIS_FR = {
    "JANVIER": 1, "FEVRIER": 2, "FÉVRIER": 2,
    "MARS": 3,    "AVRIL": 4,   "MAI": 5,
    "JUIN": 6,    "JUILLET": 7, "AOUT": 8, "AOÛT": 8,
    "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DECEMBRE": 12, "DÉCEMBRE": 12,
}
