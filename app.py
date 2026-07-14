#!/usr/bin/env python3
# ==============================================================
#  dashboard/app.py  —  Dashboard Urban Padel — Analyse Complète
# ==============================================================
import sys, os
DOSSIER_PROJET = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER_PROJET)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

st.set_page_config(page_title="Urban Padel — Dashboard", page_icon="🎾",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.section-titre{font-size:1.15rem;font-weight:700;color:#1e3a5f;margin:22px 0 10px;
  border-bottom:2px solid #e5e7eb;padding-bottom:6px;}
.kpi-card{background:linear-gradient(135deg,#1e3a5f,#2563eb);border-radius:14px;
  padding:18px 20px;color:white;text-align:left;min-height:118px;
  display:flex;flex-direction:column;justify-content:space-between;
  box-shadow:0 2px 8px rgba(30,58,95,0.12);transition:transform .15s ease;}
.kpi-card:hover{transform:translateY(-2px);}
.kpi-label{font-size:.72rem;opacity:.82;text-transform:uppercase;letter-spacing:.06em;
  margin-bottom:8px;font-weight:500;line-height:1.3;}
.kpi-info{cursor:help;margin-left:5px;opacity:.65;font-size:.85rem;}
.kpi-info:hover{opacity:1;}
.kpi-value{font-size:1.55rem;font-weight:800;line-height:1.05;letter-spacing:-.02em;}
.kpi-delta{font-size:.75rem;margin-top:6px;opacity:.88;font-weight:400;}
.alert-high{background:#fee2e2;border-left:4px solid #ef4444;padding:10px 14px;
  border-radius:6px;margin:4px 0;font-size:.88rem;}
.alert-med{background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;
  border-radius:6px;margin:4px 0;font-size:.88rem;}
.score-green{background:#d1fae5;color:#065f46;border-radius:8px;padding:8px 16px;
  font-weight:700;font-size:1.1rem;display:inline-block;}
.score-orange{background:#fef3c7;color:#92400e;border-radius:8px;padding:8px 16px;
  font-weight:700;font-size:1.1rem;display:inline-block;}
.score-red{background:#fee2e2;color:#991b1b;border-radius:8px;padding:8px 16px;
  font-weight:700;font-size:1.1rem;display:inline-block;}
</style>
""", unsafe_allow_html=True)

MOIS_NOMS = {1:"Janvier",2:"Février",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
             7:"Juillet",8:"Août",9:"Septembre",10:"Octobre",11:"Novembre",12:"Décembre"}
JOURS_FR  = {0:"Lundi",1:"Mardi",2:"Mercredi",3:"Jeudi",4:"Vendredi",5:"Samedi",6:"Dimanche"}

# ──────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎾 Urban Padel")
    st.caption("Dashboard Analyse Financière")
    st.divider()
    st.subheader("📂 Dossier de données")
    dossier_data = st.text_input("Chemin vers data/",
        value=os.path.join(DOSSIER_PROJET, "data"),
        help="Dossier local de données (non utilisé en mode Cloud)")
    st.divider()
    st.subheader("⚙️ Paramètres")
    seuil_caisse  = st.number_input("Tolérance écart caisse (DH)", value=50, min_value=0, step=10)
    ca_max_jour   = st.number_input("CA max théorique / jour (DH)", value=33000, min_value=1000, step=1000,
                                     help="Utilisé pour calculer le taux de remplissage")
    seuil_charges = st.slider("Seuil hausse charges MoM (%)", 5, 50, 20)
    seuil_ca_drop = st.slider("Seuil baisse CA MoM (%)", 5, 50, 15)
    st.divider()
    if st.button("🔄 Actualiser les données locales", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # Bouton sync Drive
    drive_cfg_path = os.path.join(DOSSIER_PROJET, "drive_config.json")
    if os.path.exists(drive_cfg_path):
        st.divider()
        st.subheader("☁️ Google Drive")
        if st.button("🔄 Synchroniser depuis Drive", type="secondary", use_container_width=True):
            result = sync_drive_si_configure(DOSSIER_PROJET, dossier_data)
            if result:
                for msg in result["messages"]:
                    if "[OK]" in msg:
                        st.success(msg)
                    elif "[ERREUR]" in msg:
                        st.error(msg)
                    else:
                        st.info(msg)
                if result["succes"]:
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.divider()
        st.caption("☁️ [Drive non configuré]")
        st.caption("Voir README_DRIVE.txt")


# ──────────────────────────────────────────────
# SYNCHRONISATION GOOGLE DRIVE (optionnel)
# ──────────────────────────────────────────────
def sync_drive_si_configure(dossier_projet: str, dossier_data: str):
    """
    Si drive_config.json existe, telecharge les fichiers depuis Google Drive.
    Sinon, utilise les fichiers locaux du dossier data/.
    """
    from extractors.drive_connector import verifier_config_drive, telecharger_fichiers_drive

    cfg = verifier_config_drive(dossier_projet)
    if not cfg["ok"]:
        return None  # Pas de Drive configure, mode local

    with st.spinner("🔄 Synchronisation avec Google Drive..."):
        result = telecharger_fichiers_drive(
            os.path.join(dossier_projet, "drive_config.json"),
            dossier_data
        )

    return result

# ──────────────────────────────────────────────
# CHARGEMENT
# ──────────────────────────────────────────────
@st.cache_data(show_spinner="⏳ Chargement des données...")
def charger(dossier, seuil_c, ca_max, seuil_ch, seuil_ca):
    from config.mapping import FICHIER_CA, FICHIER_CAISSE_W, FICHIER_CAISSE_B, FICHIER_CPC
    from extractors.ca_extractor      import extraire_ca
    from extractors.caisse_extractor  import extraire_caisse
    from extractors.cpc_extractor     import extraire_cpc
    from analysis.normalization       import (normaliser_ca_journalier,
        normaliser_caisse_par_jour, construire_tableau_crosscheck, normaliser_cpc_mensuel)
    from analysis.financial           import (resume_ca_mensuel, mix_paiements_mensuel,
        analyser_cpc, comparaison_mom_lignes, detecter_anomalies)

    chemins = {k: os.path.join(dossier, v) for k, v in {
        "ca": FICHIER_CA, "cw": FICHIER_CAISSE_W,
        "cb": FICHIER_CAISSE_B, "cpc": FICHIER_CPC}.items()}

    # Seuls CA et CPC sont obligatoires — les caisses sont optionnelles
    manquants = [k for k in ["ca", "cpc"] if not os.path.exists(chemins[k])]
    if manquants:
        return None, manquants

    res_ca  = extraire_ca(chemins["ca"])
    res_cpc = extraire_cpc(chemins["cpc"])

    # Caisses optionnelles
    vide_caisse = {"entrees_ca": [], "mouvements": [], "nb_mouvements": 0, "nb_entrees_ca": 0, "erreurs": []}
    res_cw = extraire_caisse(chemins["cw"], "W") if os.path.exists(chemins["cw"]) else vide_caisse
    res_cb = extraire_caisse(chemins["cb"], "B") if os.path.exists(chemins["cb"]) else vide_caisse

    ca_j    = normaliser_ca_journalier(res_ca["donnees"])
    cw_agg  = normaliser_caisse_par_jour(res_cw["entrees_ca"], "W")
    cb_agg  = normaliser_caisse_par_jour(res_cb["entrees_ca"], "B")
    cc      = construire_tableau_crosscheck(ca_j, cw_agg, cb_agg)
    cpc_m   = normaliser_cpc_mensuel(res_cpc["mensuel"])
    ca_m    = resume_ca_mensuel(ca_j)
    ca_mix  = mix_paiements_mensuel(ca_j)
    cpc_a   = analyser_cpc(cpc_m)
    cpc_l   = comparaison_mom_lignes(res_cpc["mensuel"])
    anom    = detecter_anomalies(cpc_a, ca_m, cc)

    # Enrichissements journaliers
    if not ca_j.empty:
        ca_j["dow"]          = ca_j["date"].dt.dayofweek
        ca_j["jour_nom"]     = ca_j["dow"].map(JOURS_FR)
        ca_j["semaine"]      = ca_j["date"].dt.isocalendar().week.astype(int)
        ca_j["taux_rempli"]  = (ca_j["total"] / ca_max * 100).clip(0, 100)
        ca_j["pct_especes"]  = (ca_j["espece"] / ca_j["total"].replace(0, np.nan) * 100).round(1)

    return {
        "ca_j": ca_j, "ca_m": ca_m, "ca_mix": ca_mix,
        "cc": cc, "cpc_m": cpc_m, "cpc_a": cpc_a,
        "cpc_l": cpc_l, "anom": anom, "cpc_brut": res_cpc["mensuel"],
    }, []

# Auto-sync depuis Drive au démarrage (mode Cloud)
_drive_cfg = os.path.join(DOSSIER_PROJET, "drive_config.json")
_data_dir  = os.path.join(DOSSIER_PROJET, "data")
if os.path.exists(_drive_cfg):
    os.makedirs(_data_dir, exist_ok=True)
    from extractors.drive_connector import telecharger_fichiers_drive, verifier_config_drive
    _cfg = verifier_config_drive(DOSSIER_PROJET)
    if _cfg["ok"]:
        _result = telecharger_fichiers_drive(_drive_cfg, _data_dir)
        dossier_data = _data_dir

D, manquants = charger(dossier_data, seuil_caisse, ca_max_jour, seuil_charges, seuil_ca_drop)

if D is None:
    st.error("❌ Fichiers manquants dans data/")
    for f in manquants:
        st.markdown(f"- `{f}`")
    st.stop()

ca_j, ca_m, ca_mix = D["ca_j"], D["ca_m"], D["ca_mix"]

# Securite : garantir les colonnes enrichies (au cas ou le cache renvoie une version incomplete)
if not ca_j.empty:
    if "dow" not in ca_j.columns:
        ca_j["dow"] = ca_j["date"].dt.dayofweek
    if "jour_nom" not in ca_j.columns:
        ca_j["jour_nom"] = ca_j["dow"].map(JOURS_FR)
    if "semaine" not in ca_j.columns:
        ca_j["semaine"] = ca_j["date"].dt.isocalendar().week.astype(int)
    if "taux_rempli" not in ca_j.columns:
        ca_j["taux_rempli"] = (ca_j["total"] / ca_max_jour * 100).clip(0, 100)
    if "pct_especes" not in ca_j.columns:
        ca_j["pct_especes"] = (ca_j["espece"] / ca_j["total"].replace(0, np.nan) * 100).round(1)
cc_full = D["cc"]
cc = cc_full[cc_full["date"].dt.year >= 2026].copy() if not cc_full.empty else cc_full
cpc_m, cpc_a = D["cpc_m"], D["cpc_a"]
cpc_l, anom        = D["cpc_l"], D["anom"]
cpc_brut           = D["cpc_brut"]

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def fmt(v, default="—"):
    if v is None or (isinstance(v, float) and np.isnan(v)): return default
    return f"{v:,.0f} DH"

def fpct(v, default="—"):
    if v is None or (isinstance(v, float) and np.isnan(v)): return default
    return f"{'+' if v>=0 else ''}{v:.1f}%"

def kpi(label, value, delta=None, info=None):
    d = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    # Petit i d'info avec tooltip natif (au survol)
    i = ""
    if info:
        info_clean = info.replace('"', "&quot;")
        i = f'<span class="kpi-info" title="{info_clean}">&#9432;</span>'
    return (f'<div class="kpi-card"><div class="kpi-label">{label}{i}</div>'
            f'<div class="kpi-value">{value}</div>{d}</div>')

COLORS = ["#2563eb","#10b981","#f59e0b","#8b5cf6","#ef4444","#06b6d4","#ec4899"]

# ──────────────────────────────────────────────
# EN-TÊTE + KPIs GLOBAUX
# ──────────────────────────────────────────────
st.title("🎾 Urban Padel — Dashboard Financier")
st.caption(f"Mis à jour le {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')} — {len(ca_j)} jours analysés")

if not ca_m.empty:
    last = ca_m.iloc[-1]
    prev = ca_m.iloc[-2] if len(ca_m) > 1 else None

    # ── Score de santé — 4 composantes de 25 pts ──────────

    # Composante 1 : Rentabilité (marge EBITDA dernier mois)
    s_rent = 0
    if not cpc_a.empty and pd.notna(cpc_a.iloc[-1].get("marge_ebitda")):
        marge = cpc_a.iloc[-1]["marge_ebitda"]
        if   marge >= 25: s_rent = 25
        elif marge >= 15: s_rent = 20
        elif marge >= 5:  s_rent = 10
        else:             s_rent = 0
    else:
        s_rent = 25

    # Composante 2 : Croissance CA
    # On utilise le dernier mois COMPLET (>= 25 jours)
    # pour eviter que un mois partiel fausse le score
    s_ca = 20  # neutre par defaut
    ca_m_complets = ca_m[ca_m["nb_jours"] >= 25]
    if len(ca_m_complets) >= 2:
        last_complet = ca_m_complets.iloc[-1]
        prev_complet = ca_m_complets.iloc[-2]
        if prev_complet["total_ca"] > 0:
            mom_complet = (last_complet["total_ca"] - prev_complet["total_ca"]) / prev_complet["total_ca"] * 100
            if   mom_complet >= 5:   s_ca = 25
            elif mom_complet >= 0:   s_ca = 20
            elif mom_complet >= -10: s_ca = 10
            else:                    s_ca = 0
        ca_m_ref = last_complet
    else:
        mom_complet = None
        ca_m_ref = ca_m.iloc[-1] if not ca_m.empty else None

    # Composante 3 : Contrôle caisses 2026
    # On penalise uniquement "CA > Caisses" (especes declarees mais pas en caisse)
    # On ignore "Caisses > CA" car ce sont souvent des recettes annexes legitimes
    s_cc = 25
    cc_2026 = cc[cc["date"].dt.year >= 2026] if not cc.empty else cc
    if not cc_2026.empty:
        nb_vrais_ecarts = (cc_2026["statut"] == "🔴 CA > Caisses").sum()
        nb_jours_2026   = (cc_2026["statut"] != "⬜ Pas de caisse").sum()
        pct_ecarts = (nb_vrais_ecarts / nb_jours_2026 * 100) if nb_jours_2026 > 0 else 0
        if   pct_ecarts == 0:   s_cc = 25
        elif pct_ecarts <= 5:   s_cc = 20
        elif pct_ecarts <= 15:  s_cc = 10
        else:                   s_cc = 0
    else:
        s_cc = 25

    # Composante 4 : Anomalies critiques
    # On exclut les anomalies de type ECART_CAISSE "Caisses > CA"
    # car elles sont souvent dues a des recettes annexes legitimes (tournois, ventes)
    # Anomalies HIGH retenues pour le score :
    # - On exclut les ecarts caisse ou Caisses > CA (ecart negatif = recettes annexes legitimes)
    # - On garde : CA > Caisses (especes non versees en caisse), baisses CA, baisses marge
    def _ecart_caisses_superieur(a):
        if a["type"] != "ECART_CAISSE": return False
        msg = a.get("message", "")
        # Ecart negatif = caisses > CA (ex: "Ecart de -8500 DH")
        import re as _re
        m = _re.search(r"Ecart de ([+-]?[\d,\.]+)", msg.replace("É","E").replace("é","e").replace(",",""))
        if m:
            try:
                val = float(m.group(1).replace(",",""))
                return val < 0  # negatif = caisses > CA = recette annexe legitime
            except: pass
        return False

    nb_high = sum(1 for a in anom
                  if a["severite"] == "HIGH"
                  and not _ecart_caisses_superieur(a))
    if   nb_high == 0: s_anom = 25
    elif nb_high <= 2: s_anom = 15
    elif nb_high <= 5: s_anom = 5
    else:              s_anom = 0

    score = s_rent + s_ca + s_cc + s_anom
    score = max(0, min(100, score))
    score_cls   = "score-green"  if score >= 70 else ("score-orange" if score >= 40 else "score-red")
    score_emoji = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")

    # Calcul CA/terrain mois en cours
    def get_terrains_kpi(annee, mois):
        a, m = int(annee), int(mois)
        if a in (2023, 2024): return 3.5
        if a == 2026:
            if m <= 4: return 3.5
            if m == 5: return 4.5
            return 7.5
        return 3.5

    nb_ter_last   = get_terrains_kpi(last["annee"], last["mois"])
    ca_par_ter    = last["total_ca"] / nb_ter_last if nb_ter_last else None

    # ── CA mois en cours (N) ──────────────────────────────
    ca_n_label = f"CA {int(last['mois']):02d}/{int(last['annee'])}"
    ca_n_val   = last["total_ca"]

    # ── CA mois precedent (N-1) avec variation vs N-2 ─────
    ca_m_prec = ca_m.iloc[-2] if len(ca_m) >= 2 else None
    ca_m_prec2 = ca_m.iloc[-3] if len(ca_m) >= 3 else None
    ca_prec_val = ca_m_prec["total_ca"] if ca_m_prec is not None else None
    ca_prec_delta = None
    ca_prec_label = "CA mois precedent"
    if ca_m_prec is not None:
        ca_prec_label = f"CA {int(ca_m_prec['mois']):02d}/{int(ca_m_prec['annee'])}"
        # Variation N-1 vs N-2
        if ca_m_prec2 is not None and ca_m_prec2["total_ca"]:
            ca_prec_pct = (ca_prec_val - ca_m_prec2["total_ca"]) / ca_m_prec2["total_ca"] * 100
            ca_prec_delta = f"{ca_prec_pct:+.1f}% vs mois avant"

    # ── CA moyen/jour mois en cours (jusqu a la veille) ───
    # Option A : on divise par le nombre de jours CALENDAIRES ecoules
    # jusqu a hier, meme si certains jours n ont pas encore de donnees CA.
    import datetime as _dt
    aujourd_hui = _dt.date.today()
    ca_j_mois_courant = ca_j[
        (ca_j["date"].dt.year == int(last["annee"])) &
        (ca_j["date"].dt.month == int(last["mois"]))
    ]
    if int(last["annee"]) == aujourd_hui.year and int(last["mois"]) == aujourd_hui.month:
        # Mois calendaire actuel : jours ecoules = date d hier = (aujourd hui - 1)
        nb_jours_ecoules = aujourd_hui.day - 1
        ca_somme_courant = ca_j_mois_courant[ca_j_mois_courant["date"].dt.day < aujourd_hui.day]["total"].sum()
    else:
        # Mois passe : on prend tous les jours du mois presents dans les donnees
        nb_jours_ecoules = ca_j_mois_courant["date"].dt.day.max() if not ca_j_mois_courant.empty else 0
        nb_jours_ecoules = int(nb_jours_ecoules) if nb_jours_ecoules else 0
        ca_somme_courant = ca_j_mois_courant["total"].sum()
    ca_moyen_jour_courant = (ca_somme_courant / nb_jours_ecoules) if nb_jours_ecoules > 0 else None

    # ── CA moyen/jour mois precedent (mois complet) ───────
    ca_moyen_jour_prec = None
    if ca_m_prec is not None and ca_m_prec.get("nb_jours"):
        ca_moyen_jour_prec = ca_m_prec["total_ca"] / ca_m_prec["nb_jours"]

    # ── CA previsionnel du mois en cours ──────────────────
    # = (CA jusqu a la veille / jours ecoules) x nombre total de jours du mois
    import calendar as _cal
    nb_jours_mois_total = _cal.monthrange(int(last["annee"]), int(last["mois"]))[1]
    ca_previsionnel = None
    if ca_moyen_jour_courant is not None:
        ca_previsionnel = ca_moyen_jour_courant * nb_jours_mois_total

    # ── CA previsionnel par terrain (mois en cours) ───────
    ca_prev_par_terrain = None
    if ca_previsionnel is not None and nb_ter_last:
        ca_prev_par_terrain = ca_previsionnel / nb_ter_last

    # ── CA par terrain N-1 (mois precedent complet) ───────
    ca_par_terrain_prec = None
    nb_ter_prec = None
    if ca_m_prec is not None:
        nb_ter_prec = get_terrains_kpi(ca_m_prec["annee"], ca_m_prec["mois"])
        if nb_ter_prec:
            ca_par_terrain_prec = ca_m_prec["total_ca"] / nb_ter_prec

    # Cross-check 2026 uniquement
    cc_2026 = cc[cc["date"].dt.year >= 2026] if not cc.empty else cc
    nb_ok_2026  = (cc_2026["statut"]=="✅ OK").sum() if not cc_2026.empty else 0
    tot_cc_2026 = len(cc_2026)

    # Taux de remplissage depuis le planning (pour KPI)
    taux_planning = None
    try:
        _plan_path = None
        # Chercher le fichier planning dans data/ ET dans le dossier projet
        _dossiers_recherche = [dossier_data, os.path.join(DOSSIER_PROJET, "data"), DOSSIER_PROJET]
        for _dossier in _dossiers_recherche:
            if _dossier and os.path.isdir(_dossier):
                for _f in os.listdir(_dossier):
                    if "PLANNING" in _f.upper() and _f.endswith(".xlsx"):
                        _plan_path = os.path.join(_dossier, _f)
                        break
            if _plan_path:
                break
        if _plan_path:
            from extractors.planning_extractor import extraire_taux_remplissage
            _res_plan = extraire_taux_remplissage(_plan_path)
            taux_planning = _res_plan.get("taux_moyen")
    except Exception as _e:
        taux_planning = None

    # ═══════════════ BARRE KPI (regroupee par principe) ═══════════════
    # Ligne 1 : CA GLOBAL (en cours vs precedent) + CA MOYEN/JOUR (en cours vs precedent)
    r1c1, r1c2, r1c3, r1c4 = st.columns(4, gap="medium")
    with r1c1:
        st.markdown(kpi(ca_n_label, fmt(ca_n_val),
            info="Chiffre d'affaires total du mois en cours (somme des CA journaliers)."), unsafe_allow_html=True)
    with r1c2:
        st.markdown(kpi(ca_prec_label, fmt(ca_prec_val) if ca_prec_val else "—",
            ca_prec_delta,
            info="CA total du mois precedent. La variation compare ce mois precedent avec le mois encore avant (N-1 vs N-2)."), unsafe_allow_html=True)
    with r1c3:
        st.markdown(kpi("CA moyen / jour (en cours)",
            fmt(ca_moyen_jour_courant) if ca_moyen_jour_courant else "—",
            f"sur {nb_jours_ecoules} jours" if ca_moyen_jour_courant else None,
            info="CA du mois en cours divise par le nombre de jours ecoules jusqu'a la veille (aujourd'hui non compte)."), unsafe_allow_html=True)
    with r1c4:
        st.markdown(kpi("CA moyen / jour (mois prec.)",
            fmt(ca_moyen_jour_prec) if ca_moyen_jour_prec else "—",
            info="CA total du mois precedent divise par son nombre total de jours (mois complet)."), unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Ligne 2 : CA/TERRAIN (previsionnel en cours vs precedent) + PREVISIONNEL + EBITDA
    r2c1, r2c2, r2c3, r2c4 = st.columns(4, gap="medium")
    with r2c1:
        st.markdown(kpi(
            "CA prev. / terrain (en cours)",
            f"{ca_prev_par_terrain:,.0f} DH" if ca_prev_par_terrain else "—",
            f"{nb_ter_last} terrains" if ca_prev_par_terrain else None,
            info="CA previsionnel du mois en cours divise par le nombre de terrains actifs."), unsafe_allow_html=True)
    with r2c2:
        st.markdown(kpi(
            "CA / terrain (mois prec.)",
            f"{ca_par_terrain_prec:,.0f} DH" if ca_par_terrain_prec else "—",
            f"{nb_ter_prec} terrains" if ca_par_terrain_prec else None,
            info="CA total du mois precedent divise par son nombre de terrains. A comparer avec le previsionnel par terrain du mois en cours."), unsafe_allow_html=True)
    with r2c3:
        st.markdown(kpi(
            f"CA previsionnel {int(last['mois']):02d}/{int(last['annee'])}",
            fmt(ca_previsionnel) if ca_previsionnel else "—",
            f"sur {nb_jours_mois_total} jours" if ca_previsionnel else None,
            info=f"Projection du CA pour le mois complet = (CA jusqu'a la veille / {nb_jours_ecoules} jours ecoules) x {nb_jours_mois_total} jours du mois."), unsafe_allow_html=True)
    with r2c4:
        if not cpc_a.empty:
            lc = cpc_a.iloc[-1]
            st.markdown(kpi("EBITDA dernier mois", fmt(lc.get("ebitda")),
                f"Marge {lc.get('marge_ebitda',0):.1f}%" if pd.notna(lc.get("marge_ebitda")) else None,
                info="EBITDA = Produits - Charges (hors amortissements) du dernier mois du CPC. Marge = EBITDA / CA x 100."),
                unsafe_allow_html=True)
        else:
            st.markdown(kpi("EBITDA", "—"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# ONGLETS
# ──────────────────────────────────────────────
tabs = st.tabs([
    "📈 CA Global", "📅 Jours & Saisonnalité",
    "🏓 CA par Activité", "📉 Taux de Remplissage",
    "💰 Seuil de Rentabilité", "📋 CPC & Charges",
    "🔮 Tendance & Prévision", "💳 Espèces vs CB",
    "🔍 Jours Anomalies", "💰 Contrôle Caisses",
    "🚨 Alertes & Santé"
])

tab_ca, tab_jour, tab_act, tab_rem, tab_be, tab_cpc, tab_prev, tab_mix, tab_ano, tab_cc, tab_alert = tabs

# ══════════════════════════════════════════════
# ONGLET 1 — CA GLOBAL
# ══════════════════════════════════════════════
with tab_ca:
    if ca_m.empty:
        st.warning("Aucune donnee CA.")
    else:
        # Configuration terrains par periode
        def get_terrains(annee, mois):
            a, m = int(annee), int(mois)
            if a in (2023, 2024): return 3.5
            if a == 2026:
                if m <= 4: return 3.5
                if m == 5: return 4.5
                return 7.5
            return 3.5

        ca_m2 = ca_m.copy()
        ca_m2["nb_terrains"]    = ca_m2.apply(lambda r: get_terrains(r["annee"], r["mois"]), axis=1)
        ca_m2["ca_par_terrain"] = ca_m2["total_ca"] / ca_m2["nb_terrains"]

        # Sous-onglets
        st1, st2, st3, st4, st5 = st.tabs([
            "📊 CA Journalier",
            "📅 CA Mensuel N",
            "📅 CA Mensuel N-1",
            "🏓 CA / Terrain",
            "🏓 CA / Terrain N-1",
        ])

        # ── SOUS-ONGLET 1 : CA JOURNALIER ──────────────────
        with st1:
            lx = ca_m["date"].dt.strftime("%b %Y")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=lx, y=ca_m["total_ca"], name="CA", marker_color="#2563eb",
                text=ca_m["total_ca"].apply(lambda v: f"{v/1000:.0f}k"), textposition="outside"))
            fig.add_trace(go.Scatter(x=lx, y=ca_m["total_ca"].rolling(3,min_periods=1).mean(),
                name="Moy. 3 mois", line=dict(color="#f59e0b",width=2,dash="dash")))
            fig.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
                legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=30,b=10))
            st.plotly_chart(fig, use_container_width=True)
            cola, colb = st.columns(2)
            with cola:
                st.markdown("**Variation MoM (%)**")
                fm = go.Figure(go.Bar(x=lx, y=ca_m["ca_mom_pct"],
                    marker_color=["#10b981" if v>=0 else "#ef4444" for v in ca_m["ca_mom_pct"].fillna(0)],
                    text=ca_m["ca_mom_pct"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else ""),
                    textposition="outside"))
                fm.add_hline(y=0, line_color="#9ca3af")
                fm.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white", margin=dict(t=10,b=10))
                st.plotly_chart(fm, use_container_width=True)
            with colb:
                st.markdown("**Variation YoY (%)**")
                fy = go.Figure(go.Bar(x=lx, y=ca_m["ca_yoy_pct"],
                    marker_color=["#10b981" if v>=0 else "#ef4444" for v in ca_m["ca_yoy_pct"].fillna(0)],
                    text=ca_m["ca_yoy_pct"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else ""),
                    textposition="outside"))
                fy.add_hline(y=0, line_color="#9ca3af")
                fy.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white", margin=dict(t=10,b=10))
                st.plotly_chart(fy, use_container_width=True)
            st.download_button("📥 CA CSV", ca_m.to_csv(index=False).encode(),
                f"ca_mensuel_{datetime.date.today()}.csv","text/csv")

        # ── SOUS-ONGLET 2 : CA MENSUEL N ───────────────────
        with st2:
            st.markdown('<div class="section-titre">CA Mensuel — Annee N</div>', unsafe_allow_html=True)
            annees_dispo = sorted(ca_m["annee"].unique().astype(int), reverse=True)
            annee_n = st.selectbox("Annee N", annees_dispo, index=0, key="an_n")
            df_n = ca_m[ca_m["annee"]==annee_n].copy()
            df_n["mois_nom"] = df_n["mois"].map(MOIS_NOMS)
            fn = go.Figure(go.Bar(x=df_n["mois_nom"], y=df_n["total_ca"], marker_color="#2563eb",
                text=df_n["total_ca"].apply(lambda v: f"{v/1000:.0f}k"), textposition="outside"))
            fn.update_layout(height=360, plot_bgcolor="white", paper_bgcolor="white",
                title=f"CA mensuel {annee_n}", yaxis_title="DH", margin=dict(t=50,b=10))
            st.plotly_chart(fn, use_container_width=True)
            df_nd = df_n[["mois_nom","total_ca","total_especes","total_cb","nb_jours","ca_mom_pct"]].copy()
            df_nd.columns = ["Mois","CA Total","Especes","CB","Nb jours","MoM %"]
            for c in ["CA Total","Especes","CB"]:
                df_nd[c] = df_nd[c].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
            df_nd["MoM %"] = df_nd["MoM %"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else "-")
            st.dataframe(df_nd, use_container_width=True, hide_index=True)
            c1,c2,c3 = st.columns(3)
            c1.metric(f"Total {annee_n}", f"{df_n['total_ca'].sum():,.0f} DH")
            best_idx = df_n["total_ca"].idxmax()
            c2.metric("Meilleur mois", MOIS_NOMS.get(int(df_n.loc[best_idx,"mois"]),"-"),
                      f"{df_n['total_ca'].max():,.0f} DH")
            c3.metric("CA moyen/mois", f"{df_n['total_ca'].mean():,.0f} DH")

        # ── SOUS-ONGLET 3 : CA MENSUEL N-1 ─────────────────
        with st3:
            st.markdown('<div class="section-titre">CA Mensuel — N vs N-1</div>', unsafe_allow_html=True)
            annees2 = sorted(ca_m["annee"].unique().astype(int), reverse=True)
            cs1, cs2 = st.columns(2)
            with cs1:
                an_ref = st.selectbox("Annee N", annees2, index=0, key="an_ref")
            with cs2:
                an_comp_list = [a for a in annees2 if a != an_ref]
                an_comp = st.selectbox("Annee N-1", an_comp_list, index=0, key="an_comp") if an_comp_list else None
            if an_comp:
                dfr = ca_m[ca_m["annee"]==an_ref].set_index("mois")
                dfp = ca_m[ca_m["annee"]==an_comp].set_index("mois")
                tous_m = sorted(set(dfr.index)|set(dfp.index))
                rows = []
                for mo in tous_m:
                    cr = dfr.loc[mo,"total_ca"] if mo in dfr.index else None
                    cp = dfp.loc[mo,"total_ca"] if mo in dfp.index else None
                    va = (cr-cp) if cr and cp else None
                    vp = (va/cp*100) if va and cp else None
                    rows.append({"Mois": MOIS_NOMS.get(int(mo),str(mo)),
                        f"CA {an_ref}":  f"{cr:,.0f}" if cr else "-",
                        f"CA {an_comp}": f"{cp:,.0f}" if cp else "-",
                        "vs N-1 (DH)":  f"{va:+,.0f}" if va else "-",
                        "Evolution %":  f"{vp:+.1f}%" if vp else "-"})
                dft = pd.DataFrame(rows)
                fc = go.Figure()
                fc.add_trace(go.Bar(x=dft["Mois"],
                    y=[dfr.loc[m,"total_ca"] if m in dfr.index else 0 for m in tous_m],
                    name=str(an_ref), marker_color="#2563eb"))
                fc.add_trace(go.Bar(x=dft["Mois"],
                    y=[dfp.loc[m,"total_ca"] if m in dfp.index else 0 for m in tous_m],
                    name=str(an_comp), marker_color="#93c5fd"))
                fc.update_layout(barmode="group", height=380,
                    title=f"CA : {an_ref} vs {an_comp}",
                    plot_bgcolor="white", paper_bgcolor="white",
                    legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=50,b=10))
                st.plotly_chart(fc, use_container_width=True)
                def ce(v):
                    try:
                        n=float(str(v).replace("%","").replace("+",""))
                        return "background-color:#d1fae5;color:#065f46" if n>0 else ("background-color:#fee2e2;color:#991b1b" if n<0 else "")
                    except: return ""
                st.dataframe(dft.style.map(ce,subset=["Evolution %","vs N-1 (DH)"]),
                    use_container_width=True, hide_index=True)
                t1=dfr["total_ca"].sum(); t2=dfp["total_ca"].sum()
                vt=t1-t2; vtp=(vt/t2*100) if t2 else 0
                c1,c2,c3=st.columns(3)
                c1.metric(f"Total {an_ref}", f"{t1:,.0f} DH")
                c2.metric(f"Total {an_comp}", f"{t2:,.0f} DH")
                c3.metric("Evolution globale", f"{vtp:+.1f}%", f"{vt:+,.0f} DH")

        # ── SOUS-ONGLET 4 : CA PAR TERRAIN ─────────────────
        with st4:
            st.markdown('<div class="section-titre">CA par Terrain — Annee N</div>', unsafe_allow_html=True)
            st.caption("CA mensuel divise par le nombre de terrains actifs ce mois")
            annees_t = sorted(ca_m2["annee"].unique().astype(int), reverse=True)
            an_t = st.selectbox("Annee", annees_t, index=0, key="an_t")
            dft2 = ca_m2[ca_m2["annee"]==an_t].copy()
            dft2["mois_nom"] = dft2["mois"].map(MOIS_NOMS)
            ft = go.Figure(go.Bar(x=dft2["mois_nom"], y=dft2["ca_par_terrain"],
                marker_color="#8b5cf6",
                text=dft2["ca_par_terrain"].apply(lambda v: f"{v/1000:.0f}k"),
                textposition="outside"))
            ft.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
                title=f"CA par terrain — {an_t}", yaxis_title="DH/terrain", margin=dict(t=50,b=10))
            st.plotly_chart(ft, use_container_width=True)
            dtd = dft2[["mois_nom","nb_terrains","total_ca","ca_par_terrain","nb_jours"]].copy()
            dtd["total_ca"]       = dtd["total_ca"].apply(lambda v: f"{v:,.0f}")
            dtd["ca_par_terrain"] = dtd["ca_par_terrain"].apply(lambda v: f"{v:,.0f}")
            dtd.columns = ["Mois","Nb Terrains","CA Total","CA/Terrain","Nb jours"]
            st.dataframe(dtd, use_container_width=True, hide_index=True)
            c1,c2,c3 = st.columns(3)
            c1.metric("CA/terrain moyen", f"{dft2['ca_par_terrain'].mean():,.0f} DH")
            bi = dft2["ca_par_terrain"].idxmax()
            c2.metric("Meilleur mois", MOIS_NOMS.get(int(dft2.loc[bi,"mois"]),"-"),
                f"{dft2['ca_par_terrain'].max():,.0f} DH")
            c3.metric("Terrains actifs (dernier mois)", str(dft2["nb_terrains"].iloc[-1]))

        # ── SOUS-ONGLET 5 : CA PAR TERRAIN N-1 ─────────────
        with st5:
            st.markdown('<div class="section-titre">CA par Terrain — N vs N-1</div>', unsafe_allow_html=True)
            annees_t2 = sorted(ca_m2["annee"].unique().astype(int), reverse=True)
            ct1,ct2 = st.columns(2)
            with ct1:
                an_tr = st.selectbox("Annee N", annees_t2, index=0, key="an_tr")
            with ct2:
                an_tn1_list = [a for a in annees_t2 if a != an_tr]
                an_tn1 = st.selectbox("Annee N-1", an_tn1_list, index=0, key="an_tn1") if an_tn1_list else None
            if an_tn1:
                dtr  = ca_m2[ca_m2["annee"]==an_tr].set_index("mois")
                dtn1 = ca_m2[ca_m2["annee"]==an_tn1].set_index("mois")
                tous_mt = sorted(set(dtr.index)|set(dtn1.index))
                rowst = []
                for mo in tous_mt:
                    cr  = dtr.loc[mo,"ca_par_terrain"]  if mo in dtr.index  else None
                    cn1 = dtn1.loc[mo,"ca_par_terrain"] if mo in dtn1.index else None
                    ter_r  = dtr.loc[mo,"nb_terrains"]  if mo in dtr.index  else None
                    ter_n1 = dtn1.loc[mo,"nb_terrains"] if mo in dtn1.index else None
                    va = (cr-cn1) if cr and cn1 else None
                    vp = (va/cn1*100) if va and cn1 else None
                    rowst.append({"Mois": MOIS_NOMS.get(int(mo),str(mo)),
                        f"CA/T {an_tr}":  f"{cr:,.0f}"  if cr  else "-",
                        f"Terrains {an_tr}":  str(ter_r)  if ter_r  else "-",
                        f"CA/T {an_tn1}": f"{cn1:,.0f}" if cn1 else "-",
                        f"Terrains {an_tn1}": str(ter_n1) if ter_n1 else "-",
                        "vs N-1 (DH)": f"{va:+,.0f}" if va else "-",
                        "Evolution %":  f"{vp:+.1f}%" if vp else "-"})
                dfct = pd.DataFrame(rowst)
                ftc = go.Figure()
                ftc.add_trace(go.Bar(x=dfct["Mois"],
                    y=[dtr.loc[m,"ca_par_terrain"] if m in dtr.index else 0 for m in tous_mt],
                    name=str(an_tr), marker_color="#8b5cf6"))
                ftc.add_trace(go.Bar(x=dfct["Mois"],
                    y=[dtn1.loc[m,"ca_par_terrain"] if m in dtn1.index else 0 for m in tous_mt],
                    name=str(an_tn1), marker_color="#c4b5fd"))
                ftc.update_layout(barmode="group", height=380,
                    title=f"CA/Terrain : {an_tr} vs {an_tn1}",
                    plot_bgcolor="white", paper_bgcolor="white",
                    legend=dict(orientation="h",y=1.1),
                    yaxis_title="DH/terrain", margin=dict(t=50,b=10))
                st.plotly_chart(ftc, use_container_width=True)
                def ce2(v):
                    try:
                        n=float(str(v).replace("%","").replace("+",""))
                        return "background-color:#d1fae5;color:#065f46" if n>0 else ("background-color:#fee2e2;color:#991b1b" if n<0 else "")
                    except: return ""
                st.dataframe(dfct.style.map(ce2,subset=["Evolution %","vs N-1 (DH)"]),
                    use_container_width=True, hide_index=True)


with tab_jour:
    st.markdown('<div class="section-titre">CA moyen par jour de la semaine</div>', unsafe_allow_html=True)
    dow_avg = ca_j.groupby(["dow","jour_nom"])["total"].agg(["mean","sum","count"]).reset_index()
    dow_avg.columns = ["dow","jour","ca_moyen","ca_total","nb_jours"]
    dow_avg = dow_avg.sort_values("dow")
    fig_dow = go.Figure(go.Bar(
        x=dow_avg["jour"], y=dow_avg["ca_moyen"],
        marker_color=["#2563eb" if v==dow_avg["ca_moyen"].max() else "#93c5fd" for v in dow_avg["ca_moyen"]],
        text=dow_avg["ca_moyen"].apply(lambda v: f"{v:,.0f}"),
        textposition="outside"))
    fig_dow.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
        yaxis_title="CA moyen (DH)", title="Le meilleur jour est mis en évidence",
        margin=dict(t=40,b=10))
    st.plotly_chart(fig_dow, use_container_width=True)

    meilleur_jour = dow_avg.loc[dow_avg["ca_moyen"].idxmax(), "jour"]
    pire_jour     = dow_avg.loc[dow_avg["ca_moyen"].idxmin(), "jour"]
    ratio         = dow_avg["ca_moyen"].max() / dow_avg["ca_moyen"].min()
    c1,c2,c3 = st.columns(3)
    c1.metric("Meilleur jour", meilleur_jour, f"{dow_avg['ca_moyen'].max():,.0f} DH/j")
    c2.metric("Jour le plus faible", pire_jour, f"{dow_avg['ca_moyen'].min():,.0f} DH/j")
    c3.metric("Écart meilleur/pire", f"×{ratio:.1f}")

    # Carte de chaleur mois × année (saisonnalité)
    st.markdown('<div class="section-titre">Carte de chaleur — saisonnalité (CA mensuel)</div>', unsafe_allow_html=True)
    heat = ca_m.copy()
    heat["mois_nom"] = heat["mois"].map(MOIS_NOMS)
    heat_pivot = heat.pivot_table(index="annee", columns="mois", values="total_ca", aggfunc="sum")
    heat_pivot.columns = [MOIS_NOMS.get(int(c), str(c)) for c in heat_pivot.columns]
    fig_heat = px.imshow(heat_pivot,
        color_continuous_scale="Blues",
        text_auto=".0f",
        aspect="auto",
        title="CA mensuel par année (DH)")
    fig_heat.update_layout(height=max(200, len(heat_pivot)*60+80),
        coloraxis_showscale=True, margin=dict(t=50,b=10))
    st.plotly_chart(fig_heat, use_container_width=True)
    st.caption("Les cases plus foncées = CA plus élevé. Les cases blanches = données manquantes.")

    # CA par semaine de l'année
    st.markdown('<div class="section-titre">CA par semaine de l\'année</div>', unsafe_allow_html=True)
    week_data = ca_j.groupby(["annee","semaine"])["total"].sum().reset_index()
    fig_wk = px.line(week_data, x="semaine", y="total", color="annee",
        color_discrete_sequence=COLORS,
        labels={"semaine":"Semaine","total":"CA (DH)","annee":"Année"},
        title="Comparaison semaine par semaine")
    fig_wk.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h",y=1.1), margin=dict(t=50,b=10))
    st.plotly_chart(fig_wk, use_container_width=True)

# ══════════════════════════════════════════════
# ONGLET 3 — CA PAR ACTIVITÉ (depuis CPC)
# ══════════════════════════════════════════════
with tab_act:
    if not cpc_brut:
        st.warning("Aucune donnée CPC disponible.")
    else:
        st.markdown('<div class="section-titre">Répartition du CA par activité</div>', unsafe_allow_html=True)

        # Construire DataFrame des produits par mois
        rows_prod = []
        for m in cpc_brut:
            for prod, val in (m.get("produits") or {}).items():
                if val and val > 0:
                    rows_prod.append({"mois": m["mois"], "annee": m["annee"],
                        "activite": prod, "montant": val,
                        "periode": f"{m['mois']:02d}/{m['annee']}"})
        df_prod = pd.DataFrame(rows_prod) if rows_prod else pd.DataFrame()

        if df_prod.empty:
            st.info("Données de détail par activité non disponibles.")
        else:
            # Top activités
            top_act = df_prod.groupby("activite")["montant"].sum().sort_values(ascending=False)
            col_pie, col_bar = st.columns(2)
            with col_pie:
                fig_pie = px.pie(values=top_act.values, names=top_act.index,
                    title="Répartition globale par activité",
                    color_discrete_sequence=px.colors.qualitative.Bold)
                fig_pie.update_layout(height=320, margin=dict(t=50,b=10))
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_bar:
                fig_hbar = go.Figure(go.Bar(
                    x=top_act.values, y=top_act.index, orientation="h",
                    marker_color=COLORS[:len(top_act)],
                    text=top_act.apply(lambda v: f"{v:,.0f}"),
                    textposition="outside"))
                fig_hbar.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
                    title="CA total par activité", xaxis_title="DH", margin=dict(t=50,b=10))
                st.plotly_chart(fig_hbar, use_container_width=True)

            # Évolution par activité dans le temps
            st.markdown('<div class="section-titre">Évolution mensuelle par activité</div>', unsafe_allow_html=True)
            activites_dispo = sorted(df_prod["activite"].unique())
            act_sel = st.multiselect("Sélectionner les activités",
                activites_dispo, default=activites_dispo[:4])
            if act_sel:
                df_filt = df_prod[df_prod["activite"].isin(act_sel)]
                fig_act = px.line(df_filt.sort_values(["annee","mois"]),
                    x="periode", y="montant", color="activite",
                    color_discrete_sequence=COLORS,
                    markers=True,
                    labels={"periode":"Période","montant":"CA (DH)","activite":"Activité"})
                fig_act.update_layout(height=360, plot_bgcolor="white", paper_bgcolor="white",
                    legend=dict(orientation="h",y=1.1), margin=dict(t=50,b=10))
                st.plotly_chart(fig_act, use_container_width=True)

            # Tableau récap
            st.markdown('<div class="section-titre">Tableau par activité et par mois</div>', unsafe_allow_html=True)
            pivot_act = df_prod.pivot_table(index="activite", columns="periode",
                values="montant", aggfunc="sum").fillna(0)
            pivot_act["TOTAL"] = pivot_act.sum(axis=1)
            pivot_act = pivot_act.sort_values("TOTAL", ascending=False)
            def colorier_pivot(val):
                if pd.isna(val) or val == 0:
                    return "background-color: #f9fafb; color: #9ca3af"
                max_v = pivot_act.values.max()
                ratio = val / max_v if max_v > 0 else 0
                if ratio > 0.75:   return "background-color: #1e40af; color: white"
                elif ratio > 0.50: return "background-color: #3b82f6; color: white"
                elif ratio > 0.25: return "background-color: #93c5fd; color: #1e3a5f"
                else:              return "background-color: #dbeafe; color: #1e3a5f"
            st.dataframe(pivot_act.style.format("{:,.0f}").map(colorier_pivot),
                use_container_width=True)

# ══════════════════════════════════════════════
# ONGLET 4 — TAUX DE REMPLISSAGE
# ══════════════════════════════════════════════
with tab_rem:
    st.markdown('<div class="section-titre">Taux de remplissage reel — base sur le planning de reservation</div>', unsafe_allow_html=True)

    # Charger le planning depuis le dossier data
    planning_path = None
    for fname in os.listdir(dossier_data) if os.path.isdir(dossier_data) else []:
        if "PLANNING" in fname.upper() and fname.endswith(".xlsx"):
            planning_path = os.path.join(dossier_data, fname)
            break

    if planning_path is None:
        st.warning("Fichier planning introuvable. Le taux de remplissage necessite le fichier PLANNING.")
        st.caption("Assurez-vous que le fichier PLANNING est synchronise depuis Google Drive.")
    else:
        from extractors.planning_extractor import extraire_taux_remplissage
        res_plan = extraire_taux_remplissage(planning_path)

        if not res_plan["jours"]:
            st.warning("Aucune donnee de reservation trouvee dans le planning.")
            if res_plan["erreurs"]:
                for e in res_plan["erreurs"]:
                    st.caption(e)
        else:
            df_plan = pd.DataFrame(res_plan["jours"])
            df_plan["date"] = pd.to_datetime(df_plan["date"])
            df_plan["jour_nom"] = df_plan["date"].dt.day_name().map({
                "Monday":"Lundi","Tuesday":"Mardi","Wednesday":"Mercredi",
                "Thursday":"Jeudi","Friday":"Vendredi","Saturday":"Samedi","Sunday":"Dimanche"})

            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Taux moyen", f"{res_plan['taux_moyen']:.0f}%")
            c2.metric("Creneaux reserves", f"{res_plan['total_reserves']:,}")
            c3.metric("Creneaux disponibles", f"{res_plan['total_creneaux']:,}")
            best = df_plan.loc[df_plan["taux"].idxmax()]
            c4.metric("Meilleur jour", best["jour_nom"], f"{best['taux']:.0f}%")

            # Graphique journalier
            st.markdown('<div class="section-titre">Taux de remplissage par jour</div>', unsafe_allow_html=True)
            fig_p = go.Figure(go.Bar(
                x=df_plan["date"].dt.strftime("%d/%m"),
                y=df_plan["taux"],
                marker_color=["#10b981" if v>=60 else ("#f59e0b" if v>=40 else "#ef4444") for v in df_plan["taux"]],
                text=df_plan["taux"].apply(lambda v: f"{v:.0f}%"),
                textposition="outside",
            ))
            fig_p.add_hline(y=res_plan["taux_moyen"], line_dash="dash", line_color="#6b7280",
                annotation_text=f"Moyenne {res_plan['taux_moyen']:.0f}%")
            fig_p.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
                yaxis_title="Taux (%)", yaxis_range=[0,105], margin=dict(t=20,b=10))
            st.plotly_chart(fig_p, use_container_width=True)

            # Taux par jour de la semaine
            st.markdown('<div class="section-titre">Taux moyen par jour de la semaine</div>', unsafe_allow_html=True)
            dow_plan = df_plan.groupby("jour_nom").agg(
                taux=("taux","mean"), reserves=("reserves","sum"), total=("total","sum")).reset_index()
            ordre = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
            dow_plan["ordre"] = dow_plan["jour_nom"].map({j:i for i,j in enumerate(ordre)})
            dow_plan = dow_plan.sort_values("ordre")
            fig_dow = go.Figure(go.Bar(
                x=dow_plan["jour_nom"], y=dow_plan["taux"],
                marker_color=["#2563eb" if v==dow_plan["taux"].max() else "#93c5fd" for v in dow_plan["taux"]],
                text=dow_plan["taux"].apply(lambda v: f"{v:.0f}%"), textposition="outside"))
            fig_dow.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
                yaxis_title="Taux (%)", yaxis_range=[0,105], margin=dict(t=10,b=10))
            st.plotly_chart(fig_dow, use_container_width=True)

            # Tableau detaille
            st.markdown('<div class="section-titre">Detail par jour</div>', unsafe_allow_html=True)
            df_disp = df_plan[["date","jour_nom","reserves","libres","total","taux"]].copy()
            df_disp["date"] = df_disp["date"].dt.strftime("%d/%m/%Y")
            df_disp["taux"] = df_disp["taux"].apply(lambda v: f"{v:.0f}%")
            df_disp.columns = ["Date","Jour","Reserves","Libres","Total creneaux","Taux"]
            st.dataframe(df_disp, use_container_width=True, hide_index=True, height=350)

            st.download_button("📥 Taux remplissage CSV", df_plan.to_csv(index=False).encode(),
                f"taux_remplissage_{datetime.date.today()}.csv", "text/csv")

            st.caption("Regle : un creneau est compte comme reserve uniquement si une reservation y est inscrite. "
                "Les creneaux vides sont consideres comme disponibles.")


with tab_be:
    st.markdown('<div class="section-titre">Analyse du seuil de rentabilité</div>', unsafe_allow_html=True)

    if cpc_m.empty:
        st.warning("Données CPC nécessaires pour cette analyse.")
    else:
        # Estimer les charges fixes et variables
        charge_cols_fixes = [c for c in cpc_m.columns
            if c.startswith("chg_") and any(k in c.upper()
                for k in ["LOYER","SALAIRE","MAROC TELECOM","PROXY"])]
        charge_cols_var = [c for c in cpc_m.columns
            if c.startswith("chg_") and c not in charge_cols_fixes]

        # Breakeven = charges totales mensuelles
        cpc_a2 = cpc_a.copy()
        cpc_a2["date_str"] = cpc_a2["date"].dt.strftime("%b %Y")

        fig_be = go.Figure()
        # CA réel
        fig_be.add_trace(go.Scatter(x=cpc_a2["date_str"], y=cpc_a2["total_ca"],
            name="CA réel", mode="lines+markers",
            line=dict(color="#2563eb", width=3), marker=dict(size=8)))
        # Total charges = breakeven
        fig_be.add_trace(go.Scatter(x=cpc_a2["date_str"], y=cpc_a2["total_charges"],
            name="Seuil de rentabilité (charges)", mode="lines+markers",
            line=dict(color="#ef4444", width=2, dash="dash"), marker=dict(size=6)))
        # Zone de profit / perte
        for i in range(len(cpc_a2)):
            ca  = cpc_a2.iloc[i]["total_ca"] or 0
            chg = cpc_a2.iloc[i]["total_charges"] or 0
            color = "rgba(16,185,129,0.15)" if ca >= chg else "rgba(239,68,68,0.15)"
        fig_be.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
            yaxis_title="DH", legend=dict(orientation="h",y=1.1),
            title="CA vs Seuil de rentabilité — zone verte = profitable",
            margin=dict(t=60,b=10))
        st.plotly_chart(fig_be, use_container_width=True)

        # Métriques par mois
        st.markdown('<div class="section-titre">Rentabilité mensuelle</div>', unsafe_allow_html=True)
        rows_be = []
        for _, row in cpc_a2.iterrows():
            ca  = row.get("total_ca") or 0
            chg = row.get("total_charges") or 0
            res = ca - chg
            statut = "✅ Profitable" if res > 0 else "🔴 Déficitaire"
            rows_be.append({"Période": row["date_str"],
                "CA (DH)": f"{ca:,.0f}",
                "Charges (DH)": f"{chg:,.0f}",
                "Résultat (DH)": f"{res:+,.0f}",
                "Marge (%)": f"{(res/ca*100):+.1f}%" if ca else "—",
                "Statut": statut})
        df_be = pd.DataFrame(rows_be)
        def color_res(val):
            if not isinstance(val, str): return ""
            if "+" in val and val != "+0": return "background-color:#d1fae5;color:#065f46"
            if "-" in val: return "background-color:#fee2e2;color:#991b1b"
            return ""
        st.dataframe(df_be.style.map(color_res, subset=["Résultat (DH)","Marge (%)"]),
            use_container_width=True, hide_index=True)

        # CA minimum requis
        avg_chg = cpc_a2["total_charges"].mean()
        ca_actuel = cpc_a2["total_ca"].mean()
        nb_jours_mois = ca_j.groupby(["annee","mois"]).size().mean()
        ca_seuil_jour = avg_chg / nb_jours_mois if nb_jours_mois else 0
        c1,c2,c3 = st.columns(3)
        c1.metric("Charges moyennes / mois", f"{avg_chg:,.0f} DH")
        c2.metric("CA minimum / jour requis", f"{ca_seuil_jour:,.0f} DH",
            help="Pour couvrir les charges mensuelles moyennes")
        c3.metric("CA moyen actuel / jour", f"{ca_j['total'].mean():,.0f} DH",
            delta=f"{(ca_j['total'].mean()-ca_seuil_jour):+,.0f} DH vs seuil")

# ══════════════════════════════════════════════
# ONGLET 6 — CPC & CHARGES
# ══════════════════════════════════════════════
with tab_cpc:
    if cpc_a.empty:
        st.warning("Aucune donnée CPC.")
    else:
        st.markdown('<div class="section-titre">CA, Charges et EBITDA</div>', unsafe_allow_html=True)
        lx_cpc = cpc_a["date"].dt.strftime("%b %Y")
        fig_c = make_subplots(specs=[[{"secondary_y": True}]])
        fig_c.add_trace(go.Bar(x=lx_cpc, y=cpc_a["total_ca"], name="CA", marker_color="#2563eb",opacity=.85), secondary_y=False)
        fig_c.add_trace(go.Bar(x=lx_cpc, y=cpc_a["total_charges"], name="Charges", marker_color="#ef4444",opacity=.85), secondary_y=False)
        fig_c.add_trace(go.Scatter(x=lx_cpc, y=cpc_a["marge_ebitda"], name="Marge EBITDA %",
            mode="lines+markers", line=dict(color="#f59e0b",width=3), marker=dict(size=7)), secondary_y=True)
        fig_c.update_layout(height=420, barmode="group", plot_bgcolor="white", paper_bgcolor="white",
            legend=dict(orientation="h",y=1.1), margin=dict(t=50,b=10))
        fig_c.update_yaxes(title_text="DH", secondary_y=False)
        fig_c.update_yaxes(title_text="Marge %", secondary_y=True)
        st.plotly_chart(fig_c, use_container_width=True)

        # Détail charges
        st.markdown('<div class="section-titre">Évolution des postes de charges</div>', unsafe_allow_html=True)
        rows_chg = []
        for m in cpc_brut:
            for chg, val in (m.get("charges") or {}).items():
                if val and val > 0:
                    rows_chg.append({"periode": f"{m['mois']:02d}/{m['annee']}",
                        "poste": chg, "montant": val})
        if rows_chg:
            df_chg = pd.DataFrame(rows_chg)
            top_charges = df_chg.groupby("poste")["montant"].sum().nlargest(8).index.tolist()
            chg_sel = st.multiselect("Postes de charges", top_charges, default=top_charges[:5], key="chg_sel")
            if chg_sel:
                df_chg_f = df_chg[df_chg["poste"].isin(chg_sel)]
                fig_chg = px.line(df_chg_f, x="periode", y="montant", color="poste",
                    color_discrete_sequence=COLORS, markers=True,
                    labels={"periode":"Période","montant":"Montant (DH)","poste":"Poste"})
                fig_chg.update_layout(height=340, plot_bgcolor="white", paper_bgcolor="white",
                    legend=dict(orientation="h",y=1.1), margin=dict(t=50,b=10))
                st.plotly_chart(fig_chg, use_container_width=True)

        # Comparaison MoM ligne par ligne
        st.markdown('<div class="section-titre">Comparaison MoM ligne par ligne</div>', unsafe_allow_html=True)
        if not cpc_l.empty:
            df_lc = cpc_l.copy()
            df_lc["valeur_courante"]   = df_lc["valeur_courante"].apply(lambda v: f"{v:,.0f}")
            df_lc["valeur_precedente"] = df_lc["valeur_precedente"].apply(lambda v: f"{v:,.0f}")
            df_lc["variation_abs"]     = df_lc["variation_abs"].apply(lambda v: f"{v:+,.0f}")
            df_lc["variation_pct"]     = df_lc["variation_pct"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
            df_lc.columns = ["Section","Ligne","Mois courant","Valeur (DH)","Mois préc.","Valeur préc.","Δ DH","Δ %"]
            def col_delta(v):
                try:
                    n = float(str(v).replace("%","").replace("+",""))
                    if n > 20: return "background-color:#fee2e2"
                    if n > 0: return "background-color:#fef9c3"
                    if n < -15: return "background-color:#d1fae5"
                    return ""
                except: return ""
            st.dataframe(df_lc.style.map(col_delta, subset=["Δ %"]),
                use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
# ONGLET 7 — TENDANCE & PRÉVISION
# ══════════════════════════════════════════════
with tab_prev:
    st.markdown('<div class="section-titre">Tendance et prévision CA (3 mois)</div>', unsafe_allow_html=True)
    if len(ca_m) < 3:
        st.info("Besoin d'au moins 3 mois de données pour la prévision.")
    else:
        # Régression linéaire simple sur les N derniers mois
        n_hist = st.slider("Mois historiques pour la tendance", 3, min(24, len(ca_m)), min(12, len(ca_m)))
        df_trend = ca_m.tail(n_hist).copy().reset_index(drop=True)
        df_trend["x"] = range(len(df_trend))

        # Fit linéaire
        coeffs = np.polyfit(df_trend["x"], df_trend["total_ca"], 1)
        slope, intercept = coeffs

        # Prévisions 3 mois
        prev_months = []
        last_date = ca_m["date"].max()
        last_x = len(df_trend) - 1
        for i in range(1, 4):
            future_date = last_date + pd.DateOffset(months=i)
            prev_val = slope * (last_x + i) + intercept
            prev_months.append({"date": future_date, "total_ca": max(0, prev_val),
                "type": "Prévision"})

        df_prev_only = pd.DataFrame(prev_months)
        df_trend["type"] = "Historique"

        fig_prev = go.Figure()
        fig_prev.add_trace(go.Scatter(
            x=df_trend["date"].dt.strftime("%b %Y"), y=df_trend["total_ca"],
            name="CA historique", mode="lines+markers",
            line=dict(color="#2563eb", width=3), marker=dict(size=8)))
        fig_prev.add_trace(go.Scatter(
            x=[df_trend["date"].iloc[-1].strftime("%b %Y")] +
              [d.strftime("%b %Y") for d in df_prev_only["date"]],
            y=[df_trend["total_ca"].iloc[-1]] + list(df_prev_only["total_ca"]),
            name="Prévision (tendance linéaire)", mode="lines+markers",
            line=dict(color="#f59e0b", width=2, dash="dot"),
            marker=dict(size=8, symbol="diamond")))
        # Ligne de tendance
        x_all = range(len(df_trend) + 3)
        trend_vals = [slope * xi + intercept for xi in x_all]
        all_labels = list(df_trend["date"].dt.strftime("%b %Y")) + \
                     [d.strftime("%b %Y") for d in df_prev_only["date"]]
        fig_prev.add_trace(go.Scatter(
            x=all_labels, y=trend_vals[:len(all_labels)],
            name="Droite de tendance", mode="lines",
            line=dict(color="#9ca3af", width=1, dash="longdash")))
        fig_prev.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
            legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=50,b=10))
        st.plotly_chart(fig_prev, use_container_width=True)

        # Métriques prévision
        c1,c2,c3 = st.columns(3)
        for i, row in enumerate(prev_months):
            with [c1,c2,c3][i]:
                st.metric(row["date"].strftime("%B %Y"), f"{row['total_ca']:,.0f} DH",
                    f"{slope:+,.0f} DH/mois")
        tendance = "📈 Hausse" if slope > 0 else "📉 Baisse"
        st.info(f"**Tendance détectée : {tendance}** — variation de {slope:+,.0f} DH par mois sur les {n_hist} derniers mois. "
            f"Note : la prévision est indicative et basée sur une tendance linéaire simple.")

# ══════════════════════════════════════════════
# ONGLET 8 — ESPÈCES VS CB
# ══════════════════════════════════════════════
with tab_mix:
    st.markdown('<div class="section-titre">Évolution du mix de paiement</div>', unsafe_allow_html=True)
    if ca_mix.empty:
        st.warning("Données de mix paiement non disponibles.")
    else:
        lx_m = ca_mix["date"].dt.strftime("%b %Y")
        fig_mix = go.Figure()
        for col, label, color in [
            ("espece","Espèces","#2563eb"),("cb","CB","#10b981"),
            ("paypal","PayPal","#8b5cf6"),("cheque","Chèque","#f59e0b"),
            ("virement","Virement","#ef4444")]:
            if col in ca_mix.columns:
                fig_mix.add_trace(go.Bar(x=lx_m, y=ca_mix[col].fillna(0),
                    name=label, marker_color=color))
        fig_mix.update_layout(barmode="stack", height=320,
            plot_bgcolor="white", paper_bgcolor="white",
            legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=50,b=10))
        st.plotly_chart(fig_mix, use_container_width=True)

        # % espèces dans le temps
        st.markdown('<div class="section-titre">Part des espèces (%) — indicateur de formalisation</div>',
            unsafe_allow_html=True)
        ca_mix["pct_esp"] = (ca_mix["espece"] / ca_mix["total"].replace(0,np.nan) * 100).round(1)
        fig_pct = go.Figure()
        fig_pct.add_trace(go.Scatter(x=lx_m, y=ca_mix["pct_esp"],
            mode="lines+markers", line=dict(color="#2563eb",width=2.5), marker=dict(size=7),
            fill="tozeroy", fillcolor="rgba(37,99,235,0.1)"))
        fig_pct.add_hline(y=50, line_dash="dash", line_color="#9ca3af",
            annotation_text="50%")
        fig_pct.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white",
            yaxis_title="%", yaxis_range=[0,105], margin=dict(t=10,b=10))
        st.plotly_chart(fig_pct, use_container_width=True)

        # Interprétation
        pct_actuel = ca_mix["pct_esp"].iloc[-1] if not ca_mix.empty else 0
        pct_debut  = ca_mix["pct_esp"].iloc[0]  if not ca_mix.empty else 0
        delta_pct  = pct_actuel - pct_debut
        if delta_pct < -5:
            st.success(f"✅ La part des espèces baisse ({delta_pct:+.1f}%) : bonne formalisation des paiements.")
        elif delta_pct > 5:
            st.warning(f"⚠️ La part des espèces augmente ({delta_pct:+.1f}%) : à surveiller.")
        else:
            st.info(f"ℹ️ La part des espèces est stable ({pct_actuel:.0f}%).")

        # Tableau mensuel
        df_mx = ca_mix[["date","espece","cb","paypal","cheque","virement","total","pct_esp"]].copy()
        df_mx["date"] = df_mx["date"].dt.strftime("%b %Y")
        for c in ["espece","cb","paypal","cheque","virement","total"]:
            df_mx[c] = df_mx[c].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
        df_mx["pct_esp"] = df_mx["pct_esp"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
        df_mx.columns = ["Période","Espèces","CB","PayPal","Chèque","Virement","Total","% Espèces"]
        st.dataframe(df_mx.iloc[::-1], use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
# ONGLET 9 — JOURS ANOMALIES
# ══════════════════════════════════════════════
with tab_ano:
    st.markdown('<div class="section-titre">Détection des jours atypiques</div>', unsafe_allow_html=True)

    ca_j2 = ca_j.copy()
    # Calcul statistiques pour détection d'anomalies
    q1, q3 = ca_j2["total"].quantile(0.25), ca_j2["total"].quantile(0.75)
    iqr    = q3 - q1
    borne_basse = q1 - 1.5 * iqr
    borne_haute = q3 + 1.5 * iqr

    ca_j2["anomalie"] = "Normal"
    ca_j2.loc[ca_j2["total"] > borne_haute, "anomalie"] = "🔺 Exceptionnel"
    ca_j2.loc[ca_j2["total"] < max(borne_basse, 500), "anomalie"] = "🔻 Très faible"

    # Graphique avec anomalies
    fig_ano = go.Figure()
    fig_ano.add_trace(go.Scatter(x=ca_j2["date"], y=ca_j2["total"],
        mode="lines", name="CA journalier",
        line=dict(color="#93c5fd", width=1)))
    for cat, color, symbol in [
        ("Normal","#2563eb","circle"),
        ("🔺 Exceptionnel","#10b981","triangle-up"),
        ("🔻 Très faible","#ef4444","triangle-down")]:
        mask = ca_j2["anomalie"] == cat
        fig_ano.add_trace(go.Scatter(
            x=ca_j2[mask]["date"], y=ca_j2[mask]["total"],
            mode="markers", name=cat,
            marker=dict(color=color, size=8 if cat=="Normal" else 12, symbol=symbol)))
    fig_ano.add_hline(y=borne_haute, line_dash="dot", line_color="#10b981",
        annotation_text=f"Seuil haut {borne_haute:,.0f}")
    fig_ano.add_hline(y=max(borne_basse,500), line_dash="dot", line_color="#ef4444",
        annotation_text=f"Seuil bas")
    fig_ano.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=50,b=10))
    st.plotly_chart(fig_ano, use_container_width=True)

    col_exc, col_faib = st.columns(2)
    with col_exc:
        st.markdown(f'<div class="section-titre">Jours exceptionnels ({(ca_j2["anomalie"]=="🔺 Exceptionnel").sum()})</div>',
            unsafe_allow_html=True)
        df_exc = ca_j2[ca_j2["anomalie"]=="🔺 Exceptionnel"][["date","jour_nom","total"]].copy()
        df_exc["date"] = df_exc["date"].dt.strftime("%d/%m/%Y")
        df_exc["total"] = df_exc["total"].apply(lambda v: f"{v:,.0f}")
        df_exc.columns = ["Date","Jour","CA (DH)"]
        st.dataframe(df_exc.sort_values("CA (DH)",ascending=False),
            use_container_width=True, hide_index=True, height=250)
    with col_faib:
        st.markdown(f'<div class="section-titre">Jours très faibles ({(ca_j2["anomalie"]=="🔻 Très faible").sum()})</div>',
            unsafe_allow_html=True)
        df_faib = ca_j2[ca_j2["anomalie"]=="🔻 Très faible"][["date","jour_nom","total"]].copy()
        df_faib["date"] = df_faib["date"].dt.strftime("%d/%m/%Y")
        df_faib["total"] = df_faib["total"].apply(lambda v: f"{v:,.0f}")
        df_faib.columns = ["Date","Jour","CA (DH)"]
        st.dataframe(df_faib.sort_values("CA (DH)"), use_container_width=True,
            hide_index=True, height=250)

    st.markdown('<div class="section-titre">CA journalier — boîte à moustaches</div>', unsafe_allow_html=True)
    fig_box = go.Figure()
    for an in sorted(ca_j2["annee"].unique()):
        data_an = ca_j2[ca_j2["annee"]==an]["total"]
        fig_box.add_trace(go.Box(y=data_an, name=str(int(an)),
            marker_color=COLORS[list(ca_j2["annee"].unique()).index(an)%len(COLORS)]))
    fig_box.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
        yaxis_title="CA (DH)", margin=dict(t=10,b=10))
    st.plotly_chart(fig_box, use_container_width=True)

# ══════════════════════════════════════════════
# ONGLET 10 — CONTRÔLE CAISSES
# ══════════════════════════════════════════════
with tab_cc:
    st.markdown('<div class="section-titre">Cross-check Espèces CA vs Caisses W + B</div>', unsafe_allow_html=True)
    if cc.empty:
        st.warning("Aucune donnée de cross-check.")
    else:
        nb_ok    = (cc["statut"]=="✅ OK").sum()
        nb_rouge = (cc["statut"]=="🔴 CA > Caisses").sum()
        nb_ora   = (cc["statut"]=="🟡 Caisses > CA").sum()
        nb_gris  = (cc["statut"]=="⬜ Pas de caisse").sum()
        tot_ep   = cc[cc["ecart"]>0]["ecart"].sum()
        tot_en   = cc[cc["ecart"]<0]["ecart"].sum()

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("✅ OK", nb_ok)
        c2.metric("🔴 CA > Caisses", nb_rouge)
        c3.metric("🟡 Caisses > CA", nb_ora)
        c4.metric("⬜ Pas de caisse", nb_gris)
        c5.metric("Écarts positifs", fmt(tot_ep))
        c6.metric("Écarts négatifs", fmt(tot_en))

        fig_cc = go.Figure()
        fig_cc.add_trace(go.Scatter(x=cc["date"],y=cc["ca_especes"],
            name="CA Espèces",mode="lines",line=dict(color="#2563eb",width=2)))
        fig_cc.add_trace(go.Scatter(x=cc["date"],y=cc["total_caisses"],
            name="Total Caisses",mode="lines",line=dict(color="#10b981",width=2)))
        fig_cc.add_trace(go.Bar(x=cc["date"],y=cc["ecart"],name="Écart",yaxis="y2",
            opacity=.5,marker_color=["#ef4444" if e>0 else "#f59e0b" for e in cc["ecart"]]))
        fig_cc.update_layout(height=380,plot_bgcolor="white",paper_bgcolor="white",
            yaxis=dict(title="DH"),
            yaxis2=dict(title="Écart",overlaying="y",side="right"),
            legend=dict(orientation="h",y=1.1),margin=dict(t=50,b=10))
        st.plotly_chart(fig_cc, use_container_width=True)

        # Filtre
        f1,f2 = st.columns([1,2])
        with f1:
            filtres = st.multiselect("Statut", cc["statut"].unique().tolist(),
                default=[s for s in cc["statut"].unique() if "OK" not in s])
        with f2:
            dates = cc["date"].dt.date
            plage = st.date_input("Période", (dates.min(), dates.max()),
                min_value=dates.min(), max_value=dates.max())

        cc_f = cc.copy()
        if filtres: cc_f = cc_f[cc_f["statut"].isin(filtres)]
        if isinstance(plage,(list,tuple)) and len(plage)==2:
            cc_f = cc_f[(cc_f["date"].dt.date>=plage[0])&(cc_f["date"].dt.date<=plage[1])]

        df_cc = cc_f[["date","ca_especes","caisse_w","caisse_b","total_caisses","ecart","statut"]].copy()
        df_cc["date"] = df_cc["date"].dt.strftime("%d/%m/%Y")
        for c in ["ca_especes","caisse_w","caisse_b","total_caisses"]:
            df_cc[c] = df_cc[c].apply(lambda v: f"{v:,.0f}")
        df_cc["ecart"] = df_cc["ecart"].apply(lambda v: f"{v:+,.0f}")
        df_cc.columns = ["Date","CA Espèces","Caisse W","Caisse B","Total","Écart","Statut"]
        def row_color(row):
            s = row["Statut"]
            if "OK" in s:     return ["background-color:#d1fae5"]*len(row)
            if "CA >" in s:   return ["background-color:#fee2e2"]*len(row)
            if "Caisses" in s:return ["background-color:#fef3c7"]*len(row)
            return [""]*len(row)
        st.dataframe(df_cc.style.apply(row_color,axis=1),
            use_container_width=True, hide_index=True, height=400)
        st.download_button("📥 Cross-check CSV", cc_f.to_csv(index=False).encode(),
            f"crosscheck_{datetime.date.today()}.csv","text/csv")

# ══════════════════════════════════════════════
# ONGLET 11 — ALERTES & SCORE DE SANTÉ
# ══════════════════════════════════════════════
with tab_alert:
    st.markdown('<div class="section-titre">Score de santé financière</div>', unsafe_allow_html=True)

    # Score détaillé
    # Reprendre les scores deja calcules en haut de page
    marge_val = cpc_a.iloc[-1]["marge_ebitda"] if not cpc_a.empty and pd.notna(cpc_a.iloc[-1].get("marge_ebitda")) else None
    mom_val   = ca_m.iloc[-1].get("ca_mom_pct") if len(ca_m) >= 2 else None
    cc_2026_t = cc[cc["date"].dt.year >= 2026] if not cc.empty else cc
    nb_ok_t   = (cc_2026_t["statut"]=="✅ OK").sum() if not cc_2026_t.empty else 0
    tot_t     = len(cc_2026_t)
    pct_ok_t  = (nb_ok_t/tot_t*100) if tot_t else 0

    composantes = [
        {"Composante": "Rentabilite (marge EBITDA)",
         "Score": s_rent, "Max": 25,
         "Detail": f"Marge = {marge_val:.1f}%" if marge_val else "Pas de donnees CPC"},
        {"Composante": "Croissance CA (MoM)",
         "Score": s_ca,   "Max": 25,
         "Detail": f"MoM = {mom_val:+.1f}%" if pd.notna(mom_val) else "—"},
        {"Composante": "Controle caisses 2026",
         "Score": s_cc,   "Max": 25,
         "Detail": f"{pct_ok_t:.0f}% jours OK ({nb_ok_t}/{tot_t})" if tot_t else "Pas de donnees"},
        {"Composante": "Absence d anomalies critiques",
         "Score": s_anom, "Max": 25,
         "Detail": f"{nb_high} anomalie(s) critique(s)"},
    ]
    score_total = score
    score_cls2 = "score-green" if score_total>=70 else ("score-orange" if score_total>=40 else "score-red")
    st.markdown(f'<div class="{score_cls2}">Score de santé : {score_total} / 100</div>',
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Graphique radar
    if composantes:
        df_score = pd.DataFrame(composantes)
        fig_rad = go.Figure(go.Bar(
            x=df_score["Composante"], y=df_score["Score"],
            marker_color=["#10b981" if v>=20 else ("#f59e0b" if v>=10 else "#ef4444")
                          for v in df_score["Score"]],
            text=df_score.apply(lambda r: f"{r['Score']}/{r['Max']}", axis=1),
            textposition="outside"))
        fig_rad.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
            yaxis_range=[0,30], yaxis_title="Score", margin=dict(t=10,b=10))
        st.plotly_chart(fig_rad, use_container_width=True)
        st.dataframe(pd.DataFrame(composantes)[["Composante","Score","Max","Detail"]],
            use_container_width=True, hide_index=True)

    # Alertes
    st.markdown('<div class="section-titre">Alertes détectées</div>', unsafe_allow_html=True)
    if not anom:
        st.success("✅ Aucune anomalie détectée.")
    else:
        high = [a for a in anom if a["severite"]=="HIGH"]
        med  = [a for a in anom if a["severite"]=="MEDIUM"]
        a_df = pd.DataFrame(anom)
        c_pie, c_bar = st.columns(2)
        with c_pie:
            fig_ap = px.pie(values=a_df["type"].value_counts().values,
                names=a_df["type"].value_counts().index,
                color_discrete_map={"HAUSSE_CHARGES":"#ef4444","BAISSE_MARGE":"#f59e0b",
                    "BAISSE_CA":"#8b5cf6","ECART_CAISSE":"#2563eb"},
                title="Par type")
            fig_ap.update_layout(height=260, margin=dict(t=40))
            st.plotly_chart(fig_ap, use_container_width=True)
        with c_bar:
            sev = a_df["severite"].value_counts()
            fig_as = px.bar(x=sev.index, y=sev.values,
                color=sev.index, color_discrete_map={"HIGH":"#ef4444","MEDIUM":"#f59e0b"},
                text=sev.values, title="Par sévérité")
            fig_as.update_layout(height=260, showlegend=False,
                plot_bgcolor="white", paper_bgcolor="white", margin=dict(t=40))
            st.plotly_chart(fig_as, use_container_width=True)

        if high:
            st.markdown(f"#### 🔴 Alertes critiques ({len(high)})")
            for a in high[:30]:
                st.markdown(f'<div class="alert-high"><strong>{a["type"]}</strong> — {a["periode"]}<br>{a["message"]}</div>',
                    unsafe_allow_html=True)
        if med:
            with st.expander(f"🟡 Alertes moyennes ({len(med)})"):
                for a in med[:40]:
                    st.markdown(f'<div class="alert-med"><strong>{a["type"]}</strong> — {a["periode"]}<br>{a["message"]}</div>',
                        unsafe_allow_html=True)
        st.download_button("📥 Alertes CSV", a_df.to_csv(index=False).encode(),
            f"alertes_{datetime.date.today()}.csv","text/csv")

# ──────────────────────────────────────────────
# PIED DE PAGE
# ──────────────────────────────────────────────
st.divider()
st.caption(f"🎾 Urban Padel · {len(ca_j)} jours CA · {len(cc)} jours cross-check · "
    f"{len(cpc_a)} mois CPC · {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")
