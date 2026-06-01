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
.kpi-card{background:linear-gradient(135deg,#1e3a5f,#2563eb);border-radius:12px;
  padding:16px 18px;color:white;text-align:center;}
.kpi-label{font-size:.78rem;opacity:.85;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px;}
.kpi-value{font-size:1.6rem;font-weight:800;line-height:1.1;}
.kpi-delta{font-size:.8rem;margin-top:5px;opacity:.9;}
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
cc, cpc_m, cpc_a   = D["cc"],   D["cpc_m"], D["cpc_a"]
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

def kpi(label, value, delta=None):
    d = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    return f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>{d}</div>'

COLORS = ["#2563eb","#10b981","#f59e0b","#8b5cf6","#ef4444","#06b6d4","#ec4899"]

# ──────────────────────────────────────────────
# EN-TÊTE + KPIs GLOBAUX
# ──────────────────────────────────────────────
st.title("🎾 Urban Padel — Dashboard Financier")
st.caption(f"Mis à jour le {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')} — {len(ca_j)} jours analysés")

if not ca_m.empty:
    last = ca_m.iloc[-1]
    prev = ca_m.iloc[-2] if len(ca_m) > 1 else None

    # Score de santé
    score = 100
    nb_high = sum(1 for a in anom if a["severite"]=="HIGH")
    score -= nb_high * 10
    if not cpc_a.empty and pd.notna(cpc_a.iloc[-1].get("marge_ebitda")):
        marge = cpc_a.iloc[-1]["marge_ebitda"]
        if marge < 10: score -= 20
        elif marge < 20: score -= 10
    if not cc.empty:
        pct_ok = (cc["statut"]=="✅ OK").sum() / len(cc) * 100
        if pct_ok < 50: score -= 15
    score = max(0, min(100, score))
    score_cls = "score-green" if score>=70 else ("score-orange" if score>=40 else "score-red")
    score_emoji = "🟢" if score>=70 else ("🟡" if score>=40 else "🔴")

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1:
        st.markdown(kpi(f"CA {int(last['mois']):02d}/{int(last['annee'])}",
            fmt(last["total_ca"]), fpct(last.get("ca_mom_pct")) if prev is not None else None), unsafe_allow_html=True)
    with c2:
        avg_jour = ca_j["total"].mean()
        st.markdown(kpi("CA moyen / jour", fmt(avg_jour)), unsafe_allow_html=True)
    with c3:
        taux = ca_j["taux_rempli"].mean()
        st.markdown(kpi("Taux remplissage moyen", f"{taux:.0f}%"), unsafe_allow_html=True)
    with c4:
        if not cpc_a.empty:
            lc = cpc_a.iloc[-1]
            st.markdown(kpi("EBITDA dernier mois", fmt(lc.get("ebitda")),
                f"Marge {lc.get('marge_ebitda',0):.1f}%" if pd.notna(lc.get("marge_ebitda")) else None),
                unsafe_allow_html=True)
        else:
            st.markdown(kpi("EBITDA", "—"), unsafe_allow_html=True)
    with c5:
        nb_ok = (cc["statut"]=="✅ OK").sum() if not cc.empty else 0
        tot_cc = len(cc)
        st.markdown(kpi("Cross-check caisses", f"{nb_ok}/{tot_cc} OK",
            f"{tot_cc-nb_ok} écart(s)"), unsafe_allow_html=True)
    with c6:
        st.markdown(f'<div class="kpi-card"><div class="kpi-label">Score santé</div>'
            f'<div class="kpi-value">{score_emoji} {score}/100</div>'
            f'<div class="kpi-delta">{len(anom)} anomalie(s)</div></div>', unsafe_allow_html=True)

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
        st.warning("Aucune donnée CA.")
    else:
        st.markdown('<div class="section-titre">Évolution du CA mensuel</div>', unsafe_allow_html=True)
        lx = ca_m["date"].dt.strftime("%b %Y")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=lx, y=ca_m["total_ca"], name="CA", marker_color="#2563eb",
            text=ca_m["total_ca"].apply(lambda v: f"{v/1000:.0f}k"), textposition="outside"))
        fig.add_trace(go.Scatter(x=lx, y=ca_m["total_ca"].rolling(3,min_periods=1).mean(),
            name="Moy. 3 mois", line=dict(color="#f59e0b",width=2,dash="dash")))
        fig.update_layout(height=360, plot_bgcolor="white", paper_bgcolor="white",
            legend=dict(orientation="h",y=1.1), yaxis_title="DH", margin=dict(t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="section-titre">MoM (%)</div>', unsafe_allow_html=True)
            fig_m = go.Figure(go.Bar(x=lx, y=ca_m["ca_mom_pct"],
                marker_color=["#10b981" if v>=0 else "#ef4444" for v in ca_m["ca_mom_pct"].fillna(0)],
                text=ca_m["ca_mom_pct"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else ""),
                textposition="outside"))
            fig_m.add_hline(y=0, line_color="#9ca3af")
            fig_m.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white",
                yaxis_title="%", margin=dict(t=10,b=10))
            st.plotly_chart(fig_m, use_container_width=True)

        with col_b:
            st.markdown('<div class="section-titre">YoY (%)</div>', unsafe_allow_html=True)
            fig_y = go.Figure(go.Bar(x=lx, y=ca_m["ca_yoy_pct"],
                marker_color=["#10b981" if v>=0 else "#ef4444" for v in ca_m["ca_yoy_pct"].fillna(0)],
                text=ca_m["ca_yoy_pct"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else ""),
                textposition="outside"))
            fig_y.add_hline(y=0, line_color="#9ca3af")
            fig_y.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white",
                yaxis_title="%", margin=dict(t=10,b=10))
            st.plotly_chart(fig_y, use_container_width=True)

        # Comparaison inter-annuelle — tableau côte à côte
        st.markdown('<div class="section-titre">Comparaison mensuelle N vs N-1</div>',
                    unsafe_allow_html=True)

        annees_dispo = sorted(ca_m["annee"].unique().astype(int), reverse=True)

        if len(annees_dispo) >= 2:
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                annee_ref = st.selectbox("Année de référence", annees_dispo,
                    index=0, key="annee_ref")
            with col_a2:
                annees_comp = [a for a in annees_dispo if a != annee_ref]
                annee_comp = st.selectbox("Année de comparaison (N-1)",
                    annees_comp, index=0, key="annee_comp")

            # Données des deux années
            df_ref  = ca_m[ca_m["annee"] == annee_ref].set_index("mois")
            df_comp = ca_m[ca_m["annee"] == annee_comp].set_index("mois")

            # Mois communs aux deux années
            mois_communs = sorted(set(df_ref.index) & set(df_comp.index))
            # Mois dans l'une ou l'autre
            tous_mois = sorted(set(df_ref.index) | set(df_comp.index))

            rows = []
            for mois in tous_mois:
                ca_r = df_ref.loc[mois, "total_ca"]  if mois in df_ref.index  else None
                ca_c = df_comp.loc[mois, "total_ca"] if mois in df_comp.index else None
                if ca_r is not None and ca_c is not None:
                    var_abs = ca_r - ca_c
                    var_pct = (var_abs / ca_c * 100) if ca_c else None
                else:
                    var_abs = None
                    var_pct = None
                rows.append({
                    "Mois": MOIS_NOMS.get(int(mois), str(mois)),
                    f"CA {annee_ref} (DH)":  f"{ca_r:,.0f}" if ca_r is not None else "—",
                    f"CA {annee_comp} (DH)": f"{ca_c:,.0f}" if ca_c is not None else "—",
                    "vs N-1 (DH)":   f"{var_abs:+,.0f}" if var_abs is not None else "—",
                    "Évolution %":   f"{var_pct:+.1f}%" if var_pct is not None else "—",
                })

            df_comp_table = pd.DataFrame(rows)

            # Graphique côte à côte
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(
                x=df_comp_table["Mois"],
                y=[float(r.replace(",","").replace(" DH","")) if r != "—" else 0
                   for r in df_comp_table[f"CA {annee_ref} (DH)"]],
                name=str(annee_ref),
                marker_color="#2563eb",
                text=df_comp_table[f"CA {annee_ref} (DH)"],
                textposition="outside",
            ))
            fig_comp.add_trace(go.Bar(
                x=df_comp_table["Mois"],
                y=[float(r.replace(",","").replace(" DH","")) if r != "—" else 0
                   for r in df_comp_table[f"CA {annee_comp} (DH)"]],
                name=str(annee_comp),
                marker_color="#93c5fd",
                text=df_comp_table[f"CA {annee_comp} (DH)"],
                textposition="outside",
            ))
            fig_comp.update_layout(
                barmode="group",
                height=400,
                title=f"CA mensuel : {annee_ref} vs {annee_comp}",
                plot_bgcolor="white", paper_bgcolor="white",
                legend=dict(orientation="h", y=1.1),
                yaxis_title="DH",
                margin=dict(t=60, b=10),
            )
            st.plotly_chart(fig_comp, use_container_width=True)

            # Tableau comparatif
            def color_evol(v):
                try:
                    n = float(str(v).replace("%","").replace("+",""))
                    if n > 0: return "background-color:#d1fae5;color:#065f46"
                    if n < 0: return "background-color:#fee2e2;color:#991b1b"
                    return ""
                except: return ""

            st.dataframe(
                df_comp_table.style.map(color_evol, subset=["Évolution %", "vs N-1 (DH)"]),
                use_container_width=True,
                hide_index=True,
            )

            # Totaux
            ca_ref_total  = ca_m[ca_m["annee"]==annee_ref]["total_ca"].sum()
            ca_comp_total = ca_m[ca_m["annee"]==annee_comp]["total_ca"].sum()
            var_total = ca_ref_total - ca_comp_total
            var_pct_total = (var_total / ca_comp_total * 100) if ca_comp_total else 0
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Total CA {annee_ref}",  f"{ca_ref_total:,.0f} DH")
            c2.metric(f"Total CA {annee_comp}", f"{ca_comp_total:,.0f} DH")
            c3.metric("Évolution globale", f"{var_pct_total:+.1f}%",
                      f"{var_total:+,.0f} DH")
        else:
            st.info("Pas assez d'années disponibles pour la comparaison N vs N-1.")

        # Tableau récap mensuel
        st.markdown('<div class="section-titre">Tableau récapitulatif mensuel</div>', unsafe_allow_html=True)
        df_t = ca_m[["annee","mois","total_ca","total_especes","total_cb","nb_jours","ca_mom_pct","ca_yoy_pct"]].copy()
        df_t.columns = ["Année","Mois","CA Total","Espèces","CB","Nb jours","MoM %","YoY %"]
        for c in ["CA Total","Espèces","CB"]:
            df_t[c] = df_t[c].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
        for c in ["MoM %","YoY %"]:
            df_t[c] = df_t[c].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
        df_t["Mois"] = df_t["Mois"].apply(lambda m: f"{int(m):02d}")
        st.dataframe(df_t.iloc[::-1], use_container_width=True, hide_index=True)
        st.download_button("📥 CA mensuel CSV", ca_m.to_csv(index=False).encode(),
            f"ca_mensuel_{datetime.date.today()}.csv", "text/csv")

# ══════════════════════════════════════════════
# ONGLET 2 — JOURS & SAISONNALITÉ
# ══════════════════════════════════════════════
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
    st.markdown('<div class="section-titre">Taux de remplissage journalier</div>', unsafe_allow_html=True)
    st.info(f"Basé sur un CA max théorique de **{ca_max_jour:,} DH/jour** (modifiable dans la sidebar)")

    # Distribution du taux
    fig_hist = px.histogram(ca_j, x="taux_rempli", nbins=20,
        color_discrete_sequence=["#2563eb"],
        labels={"taux_rempli":"Taux de remplissage (%)"},
        title="Distribution des taux de remplissage journaliers")
    fig_hist.add_vline(x=ca_j["taux_rempli"].mean(), line_dash="dash",
        line_color="#ef4444", annotation_text=f"Moyenne {ca_j['taux_rempli'].mean():.0f}%")
    fig_hist.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=50,b=10))
    st.plotly_chart(fig_hist, use_container_width=True)

    # Taux moyen par mois
    st.markdown('<div class="section-titre">Taux de remplissage moyen par mois</div>', unsafe_allow_html=True)
    rem_m = ca_j.groupby(["annee","mois"])["taux_rempli"].mean().reset_index()
    rem_m["periode"] = rem_m.apply(lambda r: f"{int(r['mois']):02d}/{int(r['annee'])}", axis=1)
    fig_rem = go.Figure()
    fig_rem.add_trace(go.Bar(x=rem_m["periode"], y=rem_m["taux_rempli"],
        marker_color=["#10b981" if v>=70 else ("#f59e0b" if v>=50 else "#ef4444")
                      for v in rem_m["taux_rempli"]],
        text=rem_m["taux_rempli"].apply(lambda v: f"{v:.0f}%"), textposition="outside"))
    fig_rem.add_hline(y=70, line_dash="dash", line_color="#10b981",
        annotation_text="Objectif 70%")
    fig_rem.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
        yaxis_title="%", yaxis_range=[0,110], margin=dict(t=10,b=10))
    st.plotly_chart(fig_rem, use_container_width=True)

    # Taux par jour de semaine
    st.markdown('<div class="section-titre">Taux de remplissage par jour de la semaine</div>', unsafe_allow_html=True)
    rem_dow = ca_j.groupby(["dow","jour_nom"])["taux_rempli"].mean().reset_index().sort_values("dow")
    fig_rdow = go.Figure(go.Bar(x=rem_dow["jour_nom"], y=rem_dow["taux_rempli"],
        marker_color=["#2563eb" if v==rem_dow["taux_rempli"].max() else "#93c5fd"
                      for v in rem_dow["taux_rempli"]],
        text=rem_dow["taux_rempli"].apply(lambda v: f"{v:.0f}%"), textposition="outside"))
    fig_rdow.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
        yaxis_title="%", yaxis_range=[0,110], margin=dict(t=10,b=10))
    st.plotly_chart(fig_rdow, use_container_width=True)

    # Jours sous 50%
    jours_faibles = ca_j[ca_j["taux_rempli"] < 50].copy()
    jours_faibles["date_str"] = jours_faibles["date"].dt.strftime("%d/%m/%Y")
    st.markdown(f'<div class="section-titre">Jours sous 50% de remplissage ({len(jours_faibles)} jours)</div>',
        unsafe_allow_html=True)
    if not jours_faibles.empty:
        df_jf = jours_faibles[["date_str","jour_nom","total","taux_rempli"]].copy()
        df_jf.columns = ["Date","Jour","CA (DH)","Taux (%)"]
        df_jf["CA (DH)"] = df_jf["CA (DH)"].apply(lambda v: f"{v:,.0f}")
        df_jf["Taux (%)"] = df_jf["Taux (%)"].apply(lambda v: f"{v:.0f}%")
        st.dataframe(df_jf.iloc[::-1], use_container_width=True, hide_index=True, height=300)

# ══════════════════════════════════════════════
# ONGLET 5 — SEUIL DE RENTABILITÉ
# ══════════════════════════════════════════════
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
    composantes = []
    # 1. Rentabilité
    if not cpc_a.empty and pd.notna(cpc_a.iloc[-1].get("marge_ebitda")):
        marge = cpc_a.iloc[-1]["marge_ebitda"]
        s_rent = 25 if marge >= 25 else (20 if marge >= 15 else (10 if marge >= 5 else 0))
        composantes.append({"Composante":"Rentabilité (marge EBITDA)","Score":s_rent,"Max":25,
            "Détail":f"Marge = {marge:.1f}%"})
    # 2. Croissance CA
    if len(ca_m) >= 2:
        mom = ca_m.iloc[-1].get("ca_mom_pct")
        if pd.notna(mom):
            s_ca = 25 if mom >= 5 else (20 if mom >= 0 else (10 if mom >= -10 else 0))
            composantes.append({"Composante":"Croissance CA (MoM)","Score":s_ca,"Max":25,
                "Détail":f"MoM = {mom:+.1f}%"})
    # 3. Contrôle caisses
    if not cc.empty:
        pct_ok = nb_ok / len(cc) * 100
        s_cc = 25 if pct_ok >= 90 else (20 if pct_ok >= 70 else (10 if pct_ok >= 50 else 0))
        composantes.append({"Composante":"Contrôle caisses","Score":s_cc,"Max":25,
            "Détail":f"{pct_ok:.0f}% jours OK"})
    # 4. Anomalies
    s_anom = 25 if nb_high == 0 else (15 if nb_high <= 2 else (5 if nb_high <= 5 else 0))
    composantes.append({"Composante":"Absence d'anomalies","Score":s_anom,"Max":25,
        "Détail":f"{nb_high} anomalie(s) critique(s)"})

    score_total = sum(c["Score"] for c in composantes)
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
        st.dataframe(pd.DataFrame(composantes)[["Composante","Score","Max","Détail"]],
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
