"""
dashboard.py — ANEM Intelligent Job Recommender
------------------------------------------------
Candidate uploads their CV → system automatically finds their top 3 best offers.
No manual configuration. No offer selection. Fully automatic.

Run:
    streamlit run dashboard.py
"""

import json
import sys
import os
from pathlib import Path
from datetime import date

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from resume_parser.parser   import parse_resume_text
from agent.dynamic_scorer   import DynamicScorer
from agent.offer_matcher    import find_best_offers, find_best_offers_offline
from agent.trainer          import CACHE_PATH
from scoring.scoring_config import get_normalized_weights

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ANEM — Recommandation d'emploi",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.block-container { padding: 2rem 3rem 3rem 3rem; max-width: 1100px; margin: auto; }

/* ── Hero ── */
.hero {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2f4a 50%, #0d1b2a 100%);
    border-radius: 20px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    border: 1px solid #1e3a5f;
    text-align: center;
}
.hero h1 { font-size: 2.2rem; font-weight: 800; color: #fff; margin: 0 0 0.4rem 0; }
.hero p  { color: #8aa8c8; font-size: 1.05rem; margin: 0; }

/* ── Upload zone ── */
.upload-zone {
    background: #0f1923;
    border: 2px dashed #1e3a5f;
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    transition: border-color 0.2s;
}

/* ── Profile card ── */
.profile-card {
    background: #111d2e;
    border-radius: 14px;
    padding: 1.4rem 1.8rem;
    border: 1px solid #1e3a5f;
    margin-bottom: 1.5rem;
}
.profile-card h3 { color: #e2eaf4; margin: 0 0 1rem 0; font-size: 1rem; font-weight: 700;
                   text-transform: uppercase; letter-spacing: 0.08em; }
.profile-tag {
    display: inline-block;
    background: #1a2f4a;
    color: #8aa8c8;
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 0.82rem;
    margin: 3px;
}
.profile-tag b { color: #e2eaf4; }

/* ── Offer cards ── */
.offer-wrapper { margin-bottom: 1.2rem; }

.offer-card {
    background: #111d2e;
    border-radius: 16px;
    padding: 1.6rem 2rem;
    border: 1px solid #1e3a5f;
    position: relative;
    overflow: hidden;
    transition: transform 0.15s;
}
.offer-card:hover { transform: translateY(-2px); }

.offer-card-gold   { border-left: 5px solid #f5c542; }
.offer-card-silver { border-left: 5px solid #a8b8c8; }
.offer-card-bronze { border-left: 5px solid #c87533; }

.rank-medal {
    position: absolute;
    top: 1.4rem; right: 1.8rem;
    font-size: 2.2rem;
    opacity: 0.9;
}

.offer-title { font-size: 1.25rem; font-weight: 700; color: #e2eaf4; margin: 0 0 0.3rem 0; }
.offer-sub   { color: #8aa8c8; font-size: 0.88rem; margin-bottom: 1rem; }

.score-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
.score-num {
    font-size: 2.6rem;
    font-weight: 800;
    line-height: 1;
}
.score-optimale { color: #00d4aa; }
.score-bonne    { color: #4fc3f7; }
.score-faible   { color: #ffa726; }
.score-nulle    { color: #ef5350; }

.score-label {
    font-size: 0.75rem;
    color: #8aa8c8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.classif-badge {
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 700;
}
.classif-Optimale { background: #00d4aa22; color: #00d4aa; }
.classif-Bonne    { background: #4fc3f722; color: #4fc3f7; }
.classif-Faible   { background: #ffa72622; color: #ffa726; }
.classif-Nulle    { background: #ef535022; color: #ef5350; }

.offer-meta {
    display: flex; flex-wrap: wrap; gap: 10px;
    font-size: 0.82rem; color: #8aa8c8;
    border-top: 1px solid #1e3a5f;
    padding-top: 0.9rem; margin-top: 0.4rem;
}
.offer-meta span { display: flex; align-items: center; gap: 5px; }
.offer-meta b    { color: #c8daf0; }

/* ── Progress bar for criteria ── */
.crit-row { margin-bottom: 0.55rem; }
.crit-label {
    display: flex; justify-content: space-between;
    font-size: 0.78rem; color: #8aa8c8; margin-bottom: 3px;
}
.crit-bar-bg {
    background: #1a2f4a; border-radius: 4px; height: 7px; overflow: hidden;
}
.crit-bar-fill { height: 100%; border-radius: 4px; }

/* ── Match strength ring ── */
.match-ring {
    width: 90px; height: 90px;
    border-radius: 50%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    font-weight: 800;
    flex-shrink: 0;
}

/* ── Section headers ── */
.section-header {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #4a7fa8;
    margin: 1.8rem 0 0.8rem 0;
}

/* ── Why matched box ── */
.why-box {
    background: #0d1923;
    border-radius: 10px;
    padding: 1rem 1.3rem;
    font-size: 0.83rem;
    color: #8aa8c8;
    border: 1px solid #1a2f4a;
    margin-top: 0.8rem;
}
.why-box b { color: #c8daf0; }

/* ── No results ── */
.no-result {
    text-align: center;
    padding: 3rem;
    color: #4a7fa8;
    font-size: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def score_css(te: float) -> str:
    if te >= 75: return "score-optimale"
    if te >= 50: return "score-bonne"
    if te >= 25: return "score-faible"
    return "score-nulle"

def score_hex(te: float) -> str:
    if te >= 75: return "#00d4aa"
    if te >= 50: return "#4fc3f7"
    if te >= 25: return "#ffa726"
    return "#ef5350"

def bar_color(score: float) -> str:
    if score >= 0.75: return "#00d4aa"
    if score >= 0.50: return "#4fc3f7"
    if score >= 0.25: return "#ffa726"
    return "#ef5350"

MEDAL = ["🥇", "🥈", "🥉"]
CARD_CSS = ["offer-card-gold", "offer-card-silver", "offer-card-bronze"]

CRITERION_LABELS = {
    "C1": "Niveau d'instruction",
    "C2": "Diplômes",
    "C3": "Expériences",
    "C4": "Langues",
    "C5": "Ancienneté",
    "C6": "Résidence",
}

def why_matched(match: dict, parsed: dict) -> str:
    """Generate a plain-language explanation of why this offer matched."""
    reasons = []
    cs = match["criterion_scores"]
    strat = match["strategy"]

    if cs.get("C1", 0) >= 0.7:
        reasons.append(f"votre niveau d'instruction (<b>{parsed['demandeur_ni']}</b>) correspond bien au poste")
    if cs.get("C2", 0) >= 0.7:
        reasons.append(f"votre diplôme (<b>{parsed['demandeur_diplome'] or 'non précisé'}</b>) est aligné avec le domaine requis")
    if cs.get("C3", 0) >= 0.5:
        reasons.append(f"vos <b>{parsed['demandeur_exp_years']} ans d'expérience</b> répondent aux exigences du poste")
    if cs.get("C5", 0) >= 0.7:
        reasons.append("votre ancienneté d'inscription vous donne priorité dans ce profil")
    if cs.get("C6", 0) >= 0.7:
        reasons.append(f"votre commune de résidence (<b>{parsed['demandeur_commune']}</b>) est proche du lieu de travail")
    if not reasons:
        reasons.append("le profil global du poste correspond à votre dossier")

    return "Ce poste vous correspond car " + ", et ".join(reasons[:3]) + "."


# ── Load scorer & DB ──────────────────────────────────────────────────────────

@st.cache_resource
def load_scorer():
    return DynamicScorer.from_cache()

@st.cache_resource
def get_db():
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv()
        uri = os.getenv("MONGODB_URI")
        if not uri:
            return None
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client["employability_db"]
    except Exception:
        return None

scorer = load_scorer()
db     = get_db()

cache_ok = CACHE_PATH.exists()
if cache_ok:
    with open(CACHE_PATH) as f:
        cache = json.load(f)
else:
    cache = {}


# ════════════════════════════════════════════════════════════════════════════════
# MAIN UI
# ════════════════════════════════════════════════════════════════════════════════

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <h1>🎯 Recommandation d'Offres d'Emploi</h1>
    <p>Déposez votre CV — notre système analyse votre profil et vous propose les <b>3 meilleures offres</b> qui vous correspondent.</p>
</div>
""", unsafe_allow_html=True)

# ── Connection status (small, unobtrusive) ────────────────────────────────────
status_col1, status_col2, _ = st.columns([1, 1, 4])
with status_col1:
    if db is not None:
        try:
            n = db["placements"].estimated_document_count()
            st.caption(f"🟢 Base de données : **{n:,}** placements")
        except Exception:
            st.caption("🟢 MongoDB connecté")
    else:
        st.caption("🟡 Mode démo (sans MongoDB)")
with status_col2:
    if cache_ok:
        st.caption("🟢 Modèle ML : chargé")
    else:
        st.caption("🔴 Modèle ML non entraîné")

st.markdown("---")

# ── CV Input ──────────────────────────────────────────────────────────────────
col_form, col_upload = st.columns([1.7, 1.3])

with col_form:
    st.markdown('<div class="section-header">📝 Remplir le formulaire</div>', unsafe_allow_html=True)
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            f_name = st.text_input("Nom Complet", placeholder="Ex: Ahmed Benali")
            f_address = st.text_input("Adresse (Commune, Wilaya)", placeholder="Ex: Kouba, Alger")
        with col2:
            f_date = st.date_input("Date d'inscription", value=date.today())
            f_lang = st.text_input("Langues", placeholder="Ex: Français, Anglais, Arabe")
        
        f_formation = st.text_area("Formation / Diplômes", placeholder="Ex: Ingénieur d'État en Informatique - USTHB", height=100)
        f_experience = st.text_area("Expérience Professionnelle", placeholder="Ex: Développeur chez TechAlger (2014-2019)", height=150)

with col_upload:
    st.markdown('<div class="section-header">📎 Ou importer un fichier (.txt)</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("", type=["txt"], label_visibility="collapsed")
    resume_text_uploaded = ""
    if uploaded:
        resume_text_uploaded = uploaded.read().decode("utf-8", errors="replace")
        st.success(f"✅ **{uploaded.name}** chargé ({len(resume_text_uploaded)} caractères)")
    
    st.markdown('<div class="section-header">À propos du système</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="why-box">
        <b>Comment ça marche ?</b><br><br>
        1. Votre CV est analysé automatiquement<br>
        2. Le modèle ML évalue votre profil sur 6 critères<br>
        3. Chaque offre dans la base est scorée<br>
        4. Les 3 meilleures vous sont présentées<br><br>
        <b>Critères d'analyse :</b><br>
        C1 Niveau d'instruction · C2 Diplômes<br>
        C3 Expériences · C4 Langues<br>
        C5 Ancienneté · C6 Résidence
    </div>
    """, unsafe_allow_html=True)

resume_text = ""
if uploaded:
    resume_text = resume_text_uploaded
elif f_name or f_address or f_formation or f_experience or f_lang:
    resume_text = f"""Nom: {f_name}
Adresse: {f_address}
Date d'inscription: {f_date.strftime('%d/%m/%Y')}

FORMATION
{f_formation}

EXPERIENCE PROFESSIONNELLE
{f_experience}

LANGUES
{f_lang}"""

st.markdown("")
btn = st.button("🔍  Trouver mes 3 meilleures offres", type="primary", use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# RESULTS
# ════════════════════════════════════════════════════════════════════════════════
if btn:
    if not resume_text.strip():
        st.error("Veuillez fournir votre CV avant de continuer.")
        st.stop()

    # ── Step 1: Parse ─────────────────────────────────────────────────────────
    with st.spinner("Analyse du CV en cours..."):
        parsed = parse_resume_text(resume_text, "cv_input")

    # ── Candidate profile card ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">Profil détecté</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="profile-card">
        <h3>Votre profil analysé</h3>
        <span class="profile-tag">🎓 Niveau : <b>{parsed['demandeur_ni']}</b></span>
        <span class="profile-tag">📁 Diplôme : <b>{parsed['demandeur_diplome'] or '—'}</b></span>
        <span class="profile-tag">⏱ Expérience : <b>{parsed['demandeur_exp_years']} ans</b></span>
        <span class="profile-tag">💼 Métier : <b>{(parsed['demandeur_metier'] or '—')[:35]}</b></span>
        <span class="profile-tag">📍 Commune : <b>{parsed['demandeur_commune']}</b></span>
        <span class="profile-tag">🌐 Langues : <b>{', '.join(parsed['languages']) or '—'}</b></span>
        <span class="profile-tag">📅 Inscrit le : <b>{parsed['date_inscription']}</b></span>
    </div>
    """, unsafe_allow_html=True)

    # ── Step 2: Match ─────────────────────────────────────────────────────────
    with st.spinner("Recherche des meilleures offres dans la base de données..."):
        if db is not None:
            matches = find_best_offers(parsed, db, scorer, top_n=3, min_score=0)
            source  = "MongoDB Atlas"
        else:
            matches = find_best_offers_offline(parsed, scorer, top_n=3)
            source  = "mode démo"

    if not matches:
        st.markdown("""
        <div class="no-result">
            😕 Aucune offre correspondante trouvée.<br>
            <small>Essayez d'enrichir votre CV avec plus d'informations.</small>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Step 3: Display top 3 ─────────────────────────────────────────────────
    st.markdown(f'<div class="section-header">Top 3 offres recommandées · source : {source}</div>',
                unsafe_allow_html=True)

    for i, match in enumerate(matches):
        te      = match["employability_score"]
        classif = match["classification"]
        strat   = match["strategy"]
        cs      = match["criterion_scores"]
        ws      = match["weights"]
        color   = score_hex(te)
        css_s   = score_css(te)
        medal   = MEDAL[i]
        card_c  = CARD_CSS[i]
        reason  = why_matched(match, parsed)

        # ── Card HTML ─────────────────────────────────────────────────────────
        st.markdown(f"""
        <div class="offer-card {card_c}">
            <span class="rank-medal">{medal}</span>

            <div class="offer-title">{match['offre_metier']}</div>
            <div class="offer-sub">
                📍 {match['offre_lieu']} &nbsp;·&nbsp;
                🎓 {match['offre_ni']} &nbsp;·&nbsp;
                ⏱ {match['offre_exp_years']} ans requis &nbsp;·&nbsp;
                📁 {match['offre_diplome'] or 'Diplôme non spécifié'}
            </div>

            <div class="score-row">
                <div>
                    <div class="score-num {css_s}">{te:.1f}<span style="font-size:1.2rem;color:#4a7fa8">/100</span></div>
                    <div class="score-label">Score d'employabilité</div>
                </div>
                <span class="classif-badge classif-{classif}">{classif}</span>
                <div style="margin-left:auto;font-size:0.8rem;color:#4a7fa8">
                    Stratégie <b style="color:#8aa8c8">{strat}</b> &nbsp;·&nbsp;
                    {'<span style="color:#00d4aa">ML actif</span>' if match.get("ml_override_active") else '<span style="color:#4a7fa8">poids de base</span>'}
                    &nbsp;·&nbsp; {match.get('offer_frequency', 0)} placements historiques
                </div>
            </div>

            <div class="why-box">{reason}</div>

            <div class="offer-meta">
                <span>📊 C1 <b>{cs.get('C1',0):.2f}</b></span>
                <span>📋 C2 <b>{cs.get('C2',0):.2f}</b></span>
                <span>💼 C3 <b>{cs.get('C3',0):.2f}</b></span>
                <span>🌐 C4 <b>{cs.get('C4',0):.2f}</b></span>
                <span>📅 C5 <b>{cs.get('C5',0):.2f}</b></span>
                <span>📍 C6 <b>{cs.get('C6',0):.2f}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Expandable criterion breakdown ────────────────────────────────────
        with st.expander(f"Détail des critères — Offre #{i+1}"):
            for crit, label in CRITERION_LABELS.items():
                sc   = cs.get(crit, 0)
                w    = ws.get(crit, 0)
                cont = sc * w
                bc   = bar_color(sc)
                pct  = int(sc * 100)
                contrib_pct = round(cont * 100, 1)

                st.markdown(f"""
                <div class="crit-row">
                    <div class="crit-label">
                        <span><b>{crit}</b> — {label}</span>
                        <span>score {sc:.2f} · poids {w:.3f} · contribution <b style="color:{bc}">{contrib_pct:.1f} pts</b></span>
                    </div>
                    <div class="crit-bar-bg">
                        <div class="crit-bar-fill" style="width:{pct}%;background:{bc};"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("")  # spacing between cards

    # ── Summary comparison ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">Comparaison des 3 offres</div>', unsafe_allow_html=True)

    try:
        import pandas as pd

        comp_data = {
            "": [f"{MEDAL[i]} Offre #{i+1}" for i in range(len(matches))],
            "Poste":      [m["offre_metier"][:30] for m in matches],
            "Lieu":       [m["offre_lieu"] for m in matches],
            "TE Score":   [m["employability_score"] for m in matches],
            "Classif.":   [m["classification"] for m in matches],
            "C1":         [round(m["criterion_scores"]["C1"], 2) for m in matches],
            "C2":         [round(m["criterion_scores"]["C2"], 2) for m in matches],
            "C3":         [round(m["criterion_scores"]["C3"], 2) for m in matches],
            "C5":         [round(m["criterion_scores"]["C5"], 2) for m in matches],
            "C6":         [round(m["criterion_scores"]["C6"], 2) for m in matches],
        }
        df = pd.DataFrame(comp_data).set_index("")

        def hl(val):
            if isinstance(val, float):
                c = score_hex(val if val > 1 else val * 100).replace("#", "")
                r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
                return f"color:rgb({r},{g},{b});font-weight:bold"
            return ""

        st.dataframe(
            df.style.applymap(hl, subset=["TE Score"]),
            use_container_width=True,
        )

        csv = df.to_csv().encode("utf-8")
        st.download_button(
            "⬇️  Télécharger les résultats (CSV)",
            csv, "recommandations.csv", "text/csv",
        )

    except ImportError:
        for i, m in enumerate(matches):
            st.write(f"Offre #{i+1}: {m['offre_metier']} — {m['employability_score']:.1f}/100")

    # ── Footer note ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "Recommandations générées par le modèle ML (Logistic Regression) entraîné sur "
        f"{sum(cache.get(s,{}).get('n_samples',0) for s in ['S0','S1','S2','S3']):,} "
        "placements réels ANEM. Les scores reflètent la compatibilité statistique entre "
        "votre profil et les offres historiques."
    )
