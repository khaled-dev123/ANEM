"""
dashboard.py — ANEM Intelligent Job Recommender
------------------------------------------------
Two modes:
  👤 Candidat  — upload CV or fill form → top-N best matching offers (MMR reranked)
  🏢 Employeur — fill offer form → top-N best matching candidate profiles

Run:
    streamlit run dashboard.py
"""

import json
import sys
import os
import tempfile
from pathlib import Path
from datetime import date, datetime

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from resume_parser.parser   import parse_resume_text
from agent.dynamic_scorer   import DynamicScorer
from agent.offer_matcher    import find_best_offers, find_best_offers_offline, find_best_candidates
from agent.trainer          import CACHE_PATH
from scoring.scoring_config import get_normalized_weights

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ANEM — Recommandation Intelligente",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.block-container { padding: 1.5rem 2.5rem 3rem 2.5rem; max-width: 1200px; margin: auto; }

/* HERO */
.hero {
    background: linear-gradient(135deg, #080e1c 0%, #0c1a30 55%, #080e1c 100%);
    border-radius: 20px;
    padding: 2rem 2.8rem;
    margin-bottom: 1.5rem;
    border: 1px solid #162a45;
    position: relative; overflow: hidden;
}
.hero::after {
    content: '';
    position: absolute; top: -60px; right: -60px;
    width: 260px; height: 260px;
    background: radial-gradient(circle, #1a4d8822 0%, transparent 65%);
    border-radius: 50%; pointer-events: none;
}
.hero h1 {
    font-family: 'Syne', sans-serif;
    font-size: 1.9rem; font-weight: 800;
    color: #e8f0fc; margin: 0 0 0.25rem 0;
    letter-spacing: -0.025em;
}
.hero p { color: #6888a8; font-size: 0.9rem; margin: 0; }

/* FILE UPLOADER */
[data-testid="stFileUploadDropzone"] {
    min-height: 120px !important;
    border: 2px dashed #1c3554 !important;
    background: rgba(8,14,28,0.6) !important;
    border-radius: 12px !important;
}
[data-testid="stFileUploadDropzone"]:hover {
    border-color: #3070b8 !important;
    background: rgba(16,32,58,0.5) !important;
}

/* PROFILE CARD */
.profile-card {
    background: #0c1828;
    border-radius: 12px;
    padding: 1.1rem 1.5rem;
    border: 1px solid #162a45;
    margin-bottom: 1rem;
}
.profile-card h3 {
    font-family: 'Syne', sans-serif;
    color: #a8c4e0; margin: 0 0 0.7rem 0;
    font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.12em;
}
.profile-tag {
    display: inline-block;
    background: #111e30; color: #6888a8;
    border-radius: 6px; padding: 3px 9px;
    font-size: 0.78rem; margin: 2px 2px;
}
.profile-tag b { color: #c8dcf4; }

/* SECTION HEADERS */
.shdr {
    font-family: 'Syne', sans-serif;
    font-size: 0.68rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.14em;
    color: #3070b8; margin: 1.4rem 0 0.6rem 0;
}

/* MATCH CARDS */
.mcard {
    background: #0c1828;
    border-radius: 14px;
    padding: 1.4rem 1.7rem;
    border: 1px solid #162a45;
    position: relative; overflow: hidden;
    margin-bottom: 0.9rem;
    transition: transform 0.12s ease, border-color 0.12s ease;
}
.mcard:hover { transform: translateY(-2px); border-color: #214468; }
.mcard-1 { border-left: 4px solid #f5c542; }
.mcard-2 { border-left: 4px solid #9ab8cc; }
.mcard-3 { border-left: 4px solid #b87440; }
.mcard-4 { border-left: 4px solid #5880a0; }
.mcard-5 { border-left: 4px solid #3a6080; }
.mcard-n { border-left: 4px solid #2a4060; }

.rnk {
    position: absolute; top: 1.1rem; right: 1.4rem;
    font-size: 1.7rem; opacity: 0.88; line-height: 1;
}
.ctitle {
    font-family: 'Syne', sans-serif;
    font-size: 1.1rem; font-weight: 700;
    color: #dce8f8; margin: 0 0 0.2rem 0;
    padding-right: 3rem;
}
.csub { color: #6888a8; font-size: 0.8rem; margin-bottom: 0.8rem; }

.srow { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 0.7rem; flex-wrap: wrap; }
.snum {
    font-family: 'Syne', sans-serif;
    font-size: 2.2rem; font-weight: 800; line-height: 1;
}
.s-opt { color: #00cc9e; }
.s-bon { color: #38b2f0; }
.s-fai { color: #f0962a; }
.s-nul { color: #e84040; }

.cbadge { padding: 3px 11px; border-radius: 16px; font-size: 0.76rem; font-weight: 700; }
.cb-Optimale { background: #00cc9e18; color: #00cc9e; }
.cb-Bonne    { background: #38b2f018; color: #38b2f0; }
.cb-Faible   { background: #f0962a18; color: #f0962a; }
.cb-Nulle    { background: #e8404018; color: #e84040; }

.dpill {
    background: #162a45; color: #4090cc;
    border-radius: 14px; padding: 2px 9px;
    font-size: 0.7rem; font-weight: 600; white-space: nowrap;
}
.mlpill {
    background: #001a10; color: #00cc9e;
    border-radius: 14px; padding: 2px 9px;
    font-size: 0.7rem; font-weight: 600;
}
.bpill {
    background: #1a1a2e; color: #6868a8;
    border-radius: 14px; padding: 2px 9px;
    font-size: 0.7rem;
}

.whybox {
    background: #080e1c;
    border-radius: 8px; padding: 0.7rem 1rem;
    font-size: 0.79rem; color: #6888a8;
    border: 1px solid #111e30; margin: 0.5rem 0;
    line-height: 1.55;
}
.whybox b { color: #a8c4e0; }

.cmeta {
    display: flex; flex-wrap: wrap; gap: 7px;
    font-size: 0.76rem; color: #6888a8;
    border-top: 1px solid #162a45;
    padding-top: 0.7rem; margin-top: 0.4rem;
}
.cmeta span b { color: #a8c4e0; }

/* CRITERION BARS */
.crrow { margin-bottom: 0.45rem; }
.crlbl {
    display: flex; justify-content: space-between;
    font-size: 0.73rem; color: #6888a8; margin-bottom: 2px;
}
.crbg { background: #111e30; border-radius: 3px; height: 5px; overflow: hidden; }
.crfill { height: 100%; border-radius: 3px; }

/* FORM WRAPPER */
.fwrap {
    background: #0c1828;
    border-radius: 12px;
    padding: 1.3rem 1.7rem;
    border: 1px solid #162a45;
    margin-bottom: 0.8rem;
}

/* NO RESULT */
.nores {
    text-align: center; padding: 2.5rem;
    color: #2e5070; font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)


# ── Utilities ─────────────────────────────────────────────────────────────────

from resume_parser.extractor import extract_text, ExtractionError, UnsupportedFileTypeError

def extract_text_from_upload(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    try:
        return extract_text(tmp_path)
    except UnsupportedFileTypeError:
        st.error(f"Type de fichier non supporté : {uploaded_file.name}")
        return ""
    except ExtractionError as e:
        st.error(f"Erreur d'extraction : {e}")
        return ""
    except Exception as e:
        st.error(f"Erreur inattendue : {e}")
        return ""
    finally:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except OSError: pass


def score_css(te):
    if te >= 75: return "s-opt"
    if te >= 50: return "s-bon"
    if te >= 25: return "s-fai"
    return "s-nul"

def score_hex(te):
    if te >= 75: return "#00cc9e"
    if te >= 50: return "#38b2f0"
    if te >= 25: return "#f0962a"
    return "#e84040"

def bar_color(v):
    if v >= 0.75: return "#00cc9e"
    if v >= 0.50: return "#38b2f0"
    if v >= 0.25: return "#f0962a"
    return "#e84040"

MEDALS   = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
CARD_CSS = ["mcard-1","mcard-2","mcard-3","mcard-4","mcard-5"]

CRIT_LABELS = {
    "C1": "Niveau d'instruction",
    "C2": "Diplômes",
    "C3": "Expériences",
    "C4": "Langues",
    "C5": "Ancienneté",
    "C6": "Résidence",
}

NI_OPTIONS = [
    "Sans niveau","Primaire","Moyen",
    "Secondaire 1AS","Secondaire 2AS","Secondaire 3AS",
    "Supérieur 1","Supérieur 2","Supérieur 3","Universitaire",
]


def why_offer(match, parsed):
    cs = match["criterion_scores"]
    bits = []
    if cs.get("C1",0) >= 0.7:
        bits.append(f"votre niveau (<b>{parsed['demandeur_ni']}</b>) correspond au poste")
    if cs.get("C2",0) >= 0.9:
        bits.append(f"votre diplôme (<b>{parsed.get('demandeur_diplome') or 'non précisé'}</b>) correspond exactement")
    elif cs.get("C2",0) >= 0.5:
        bits.append(f"votre diplôme (<b>{parsed.get('demandeur_diplome') or 'non précisé'}</b>) est dans un domaine proche")
    if cs.get("C3",0) >= 0.7:
        bits.append(f"vos <b>{parsed.get('demandeur_exp_years',0)} ans</b> d'exp. répondent aux exigences")
    elif cs.get("C3",0) >= 0.4:
        bits.append("votre expérience est partiellement alignée")
    if cs.get("C5",0) >= 0.7:
        bits.append("votre ancienneté d'inscription vous donne priorité")
    if cs.get("C6",0) >= 0.7:
        bits.append(f"votre commune (<b>{parsed.get('demandeur_commune','')}</b>) est proche du lieu de travail")
    if not bits:
        bits.append("le profil global correspond à votre dossier")
    return "Ce poste vous correspond car " + ", et ".join(bits[:3]) + "."


def why_candidate(match, offer):
    cs = match["criterion_scores"]
    bits = []
    if cs.get("C1",0) >= 0.7:
        bits.append(f"son niveau (<b>{match['demandeur_ni']}</b>) correspond à votre offre")
    if cs.get("C2",0) >= 0.9:
        bits.append(f"son diplôme (<b>{match.get('demandeur_diplome') or 'non précisé'}</b>) correspond exactement")
    elif cs.get("C2",0) >= 0.5:
        bits.append(f"son diplôme (<b>{match.get('demandeur_diplome') or 'non précisé'}</b>) est dans un domaine proche")
    if cs.get("C3",0) >= 0.7:
        bits.append(f"ses <b>{match.get('demandeur_exp_years',0)} ans</b> d'exp. répondent aux exigences")
    elif cs.get("C3",0) >= 0.4:
        bits.append("son expérience est partiellement alignée")
    if cs.get("C6",0) >= 0.7:
        bits.append(f"sa commune (<b>{match.get('demandeur_commune','')}</b>) est proche du lieu de travail")
    if not bits:
        bits.append("le profil global correspond à votre offre")
    return "Ce candidat correspond car " + ", et ".join(bits[:3]) + "."


def render_crit_bars(cs, ws):
    for crit, label in CRIT_LABELS.items():
        sc  = cs.get(crit, 0)
        w   = ws.get(crit, 0)
        bc  = bar_color(sc)
        pct = int(sc * 100)
        contrib = round(sc * w * 100, 1)
        st.markdown(f"""
        <div class="crrow">
          <div class="crlbl">
            <span><b>{crit}</b> — {label}</span>
            <span>score {sc:.2f} &nbsp;·&nbsp; poids {w:.3f} &nbsp;·&nbsp;
              <b style="color:{bc}">{contrib:.1f} pts</b></span>
          </div>
          <div class="crbg"><div class="crfill" style="width:{pct}%;background:{bc}"></div></div>
        </div>""", unsafe_allow_html=True)


def render_card(match, idx, title, subtitle, why_html, meta_items):
    te      = match["employability_score"]
    classif = match["classification"]
    strat   = match["strategy"]
    cs      = match["criterion_scores"]
    ws      = match["weights"]
    medal   = MEDALS[idx] if idx < len(MEDALS) else f"#{idx+1}"
    card_c  = CARD_CSS[min(idx, len(CARD_CSS)-1)]
    sc_c    = score_css(te)
    ml_pill = ('<span class="mlpill">ML actif</span>'
               if match.get("ml_override_active")
               else '<span class="bpill">poids de base</span>')
    div_pill = ('<span class="dpill">🔀 diversifié</span>'
                if match.get("diversity_reranked") else "")
    mmr_note = (f'<span style="color:#2e5070;font-size:0.7rem">MMR {match["mmr_score"]:.3f}</span>'
                if match.get("mmr_score") is not None else "")
    meta_html = "".join(f'<span>{it}</span>' for it in meta_items)

    st.markdown(f"""
    <div class="mcard {card_c}">
      <span class="rnk">{medal}</span>
      <div class="ctitle">{title}</div>
      <div class="csub">{subtitle}</div>
      <div class="srow">
        <div>
          <div class="snum {sc_c}">{te:.1f}<span style="font-size:1rem;color:#2e5070">/100</span></div>
          <div style="font-size:0.65rem;color:#3070b8;text-transform:uppercase;letter-spacing:0.07em">
            Score d'employabilité</div>
        </div>
        <span class="cbadge cb-{classif}">{classif}</span>
        <div style="margin-left:auto;display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <span style="font-size:0.74rem;color:#3070b8">Strat. <b style="color:#6888a8">{strat}</b></span>
          {ml_pill} {div_pill} {mmr_note}
        </div>
      </div>
      <div class="whybox">{why_html}</div>
      <div class="cmeta">{meta_html}</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander(f"Détail des critères — #{idx+1}"):
        render_crit_bars(cs, ws)


# ── Resources ─────────────────────────────────────────────────────────────────

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

scorer   = load_scorer()
db       = get_db()
cache_ok = CACHE_PATH.exists()
cache    = {}
if cache_ok:
    with open(CACHE_PATH) as f:
        cache = json.load(f)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:800;
                color:#dce8f8;margin-bottom:1.2rem;letter-spacing:-0.01em;">
        🎯 ANEM Recommandation
    </div>
    """, unsafe_allow_html=True)

    mode = st.radio("Mode", ["👤 Candidat", "🏢 Employeur"], label_visibility="collapsed")

    st.markdown("---")
    top_n     = st.slider("Recommandations", 3, 10, 5)
    lambda_   = st.slider("Diversité (λ)", 0.0, 1.0, 0.7, 0.05,
                           help="1.0 = tri pur par score  ·  0.0 = diversité maximale")
    min_score = st.slider("Score minimum", 0, 60, 25)
    st.markdown("---")

    if db is not None:
        try:
            n = db["placements"].estimated_document_count()
            st.caption(f"🟢 MongoDB · **{n:,}** placements")
        except Exception:
            st.caption("🟢 MongoDB connecté")
    else:
        st.caption("🟡 Mode démo (sans MongoDB)")

    total_samples = sum(cache.get(s,{}).get("n_samples",0) for s in ["S0","S1","S2","S3"])
    if cache_ok:
        st.caption(f"🟢 Modèle ML · {total_samples:,} échantillons")
    else:
        st.caption("🔴 Modèle ML non entraîné")


is_candidate = (mode == "👤 Candidat")


# ════════════════════════════════════════════════════════════════════════════════
# CANDIDATE MODE
# ════════════════════════════════════════════════════════════════════════════════

if is_candidate:

    st.markdown("""
    <div class="hero">
      <h1>👤 Recommandation d'Offres</h1>
      <p>Déposez votre CV ou remplissez le formulaire — le système analyse votre profil
      et vous propose les meilleures offres correspondantes.</p>
    </div>
    """, unsafe_allow_html=True)

    # Session state init
    for k, v in [("f_name",""),("f_address",""),("f_date",date.today()),
                 ("f_lang",""),("f_formation",""),("f_experience",""),
                 ("last_uploaded",None)]:
        if k not in st.session_state:
            st.session_state[k] = v

    col_form, col_up = st.columns([1.3, 1.0])

    with col_up:
        st.markdown('<div class="shdr">📎 Importer un fichier (.txt · .pdf · .docx)</div>',
                    unsafe_allow_html=True)
        uploaded = st.file_uploader("", type=["txt","pdf","docx"], label_visibility="collapsed")

        if uploaded:
            fid = f"{uploaded.name}_{uploaded.size}"
            if st.session_state.last_uploaded != fid:
                st.session_state.last_uploaded = fid
                with st.spinner("Analyse du CV…"):
                    raw = extract_text_from_upload(uploaded)
                    if raw:
                        pd_ = parse_resume_text(raw)
                        st.session_state.f_address   = pd_.get("demandeur_commune","")
                        st.session_state.f_lang      = ", ".join(pd_.get("languages",[]))
                        st.session_state.f_formation = pd_.get("demandeur_diplome","")
                        exp_yr = pd_.get("demandeur_exp_years", 0)
                        metier = pd_.get("demandeur_metier","")
                        st.session_state.f_experience = (
                            f"{exp_yr} ans d'expérience" +
                            (f" — {metier}" if metier else "")
                        )
                        try:
                            st.session_state.f_date = datetime.strptime(
                                pd_.get("date_inscription",""), "%Y-%m-%d").date()
                        except Exception:
                            st.session_state.f_date = date.today()
            st.success(f"✅ {uploaded.name} analysé")
        else:
            st.session_state.last_uploaded = None

    with col_form:
        st.markdown('<div class="shdr">📝 Formulaire candidat</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Nom Complet",    key="f_name",    placeholder="Ahmed Benali")
            st.text_input("Commune",         key="f_address", placeholder="Kouba")
        with c2:
            st.date_input("Date d'inscription", key="f_date")
            st.text_input("Langues",         key="f_lang",    placeholder="Français, Anglais")
        st.text_area("Formation / Diplôme",          key="f_formation",  height=90,
                     placeholder="Ingénieur en Informatique — USTHB")
        st.text_area("Expérience Professionnelle",   key="f_experience", height=120,
                     placeholder="Développeur chez TechAlger (2014–2019)")

    # Build resume text from form
    resume_text = ""
    if any([st.session_state.f_name, st.session_state.f_address,
            st.session_state.f_formation, st.session_state.f_experience]):
        resume_text = f"""Nom: {st.session_state.f_name}
Adresse: {st.session_state.f_address}
Date d'inscription: {st.session_state.f_date.strftime('%d/%m/%Y')}

FORMATION
{st.session_state.f_formation}

EXPERIENCE PROFESSIONNELLE
{st.session_state.f_experience}

LANGUES
{st.session_state.f_lang}"""

    if st.button("🔍  Trouver mes meilleures offres", type="primary", use_container_width=True):
        if not resume_text.strip():
            st.error("Veuillez fournir votre CV avant de continuer.")
            st.stop()

        with st.spinner("Analyse du profil…"):
            parsed = parse_resume_text(resume_text, "cv_input")

        st.markdown("---")
        st.markdown('<div class="shdr">Profil détecté</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="profile-card">
          <h3>Votre profil analysé</h3>
          <span class="profile-tag">🎓 <b>{parsed['demandeur_ni']}</b></span>
          <span class="profile-tag">📁 Diplôme : <b>{parsed['demandeur_diplome'] or '—'}</b></span>
          <span class="profile-tag">⏱ <b>{parsed['demandeur_exp_years']} ans</b> d'exp.</span>
          <span class="profile-tag">💼 <b>{(parsed['demandeur_metier'] or '—')[:40]}</b></span>
          <span class="profile-tag">📍 <b>{parsed['demandeur_commune']}</b></span>
          <span class="profile-tag">🌐 <b>{', '.join(parsed['languages']) or '—'}</b></span>
          <span class="profile-tag">📅 Inscrit le <b>{parsed['date_inscription']}</b></span>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Recherche des meilleures offres…"):
            if db is not None:
                matches = find_best_offers(
                    parsed, db, scorer,
                    top_n=top_n, min_score=float(min_score), lambda_=lambda_,
                )
                source = "MongoDB Atlas"
            else:
                matches = find_best_offers_offline(parsed, scorer, top_n=top_n)
                source  = "mode démo"

        if not matches:
            st.markdown('<div class="nores">😕 Aucune offre correspondante trouvée.<br>'
                        '<small>Enrichissez votre CV avec plus d\'informations.</small></div>',
                        unsafe_allow_html=True)
            st.stop()

        st.markdown(
            f'<div class="shdr">Top {len(matches)} offres · {source} · λ={lambda_:.2f}</div>',
            unsafe_allow_html=True)

        for i, m in enumerate(matches):
            render_card(
                match    = m,
                idx      = i,
                title    = m["offre_metier"],
                subtitle = (f"📍 {m['offre_lieu']} &nbsp;·&nbsp; "
                            f"🎓 {m['offre_ni']} &nbsp;·&nbsp; "
                            f"⏱ {m['offre_exp_years']} ans requis &nbsp;·&nbsp; "
                            f"📁 {m['offre_diplome'] or 'Diplôme non spécifié'}"),
                why_html = why_offer(m, parsed),
                meta_items = [
                    f"C1 <b>{m['criterion_scores'].get('C1',0):.2f}</b>",
                    f"C2 <b>{m['criterion_scores'].get('C2',0):.2f}</b>",
                    f"C3 <b>{m['criterion_scores'].get('C3',0):.2f}</b>",
                    f"C5 <b>{m['criterion_scores'].get('C5',0):.2f}</b>",
                    f"C6 <b>{m['criterion_scores'].get('C6',0):.2f}</b>",
                    f"📈 {m.get('offer_frequency',0)} hist.",
                ],
            )

        # Comparison table
        st.markdown("---")
        st.markdown('<div class="shdr">Comparaison</div>', unsafe_allow_html=True)
        try:
            import pandas as pd
            df = pd.DataFrame({
                "":         [f"{MEDALS[i]} #{i+1}" for i in range(len(matches))],
                "Poste":    [m["offre_metier"][:32] for m in matches],
                "Lieu":     [m["offre_lieu"] for m in matches],
                "TE":       [m["employability_score"] for m in matches],
                "Classif.": [m["classification"] for m in matches],
                "C1": [round(m["criterion_scores"]["C1"],2) for m in matches],
                "C2": [round(m["criterion_scores"]["C2"],2) for m in matches],
                "C3": [round(m["criterion_scores"]["C3"],2) for m in matches],
                "C5": [round(m["criterion_scores"]["C5"],2) for m in matches],
                "C6": [round(m["criterion_scores"]["C6"],2) for m in matches],
                "MMR":[round(m.get("mmr_score",0),3) for m in matches],
            }).set_index("")

            def _hl(val):
                if isinstance(val, float) and val > 1:
                    h = score_hex(val).lstrip("#")
                    r,g,b = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
                    return f"color:rgb({r},{g},{b});font-weight:bold"
                return ""

            st.dataframe(df.style.applymap(_hl, subset=["TE"]), use_container_width=True)
            st.download_button("⬇️ Télécharger CSV",
                               df.to_csv().encode("utf-8"),
                               "recommandations_offres.csv", "text/csv")
        except ImportError:
            for i, m in enumerate(matches):
                st.write(f"#{i+1}: {m['offre_metier']} — {m['employability_score']:.1f}/100")


# ════════════════════════════════════════════════════════════════════════════════
# EMPLOYER MODE
# ════════════════════════════════════════════════════════════════════════════════

else:

    st.markdown("""
    <div class="hero">
      <h1>🏢 Recherche de Candidats</h1>
      <p>Décrivez votre offre d'emploi — le système identifie les profils candidats
      les plus compatibles dans la base de données.</p>
    </div>
    """, unsafe_allow_html=True)

    if db is None:
        st.warning("⚠️ MongoDB non connecté. La recherche de candidats nécessite la base de données.")
        st.stop()

    st.markdown('<div class="shdr">📋 Décrire votre offre d\'emploi</div>',
                unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="fwrap">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            offre_ni    = st.selectbox("Niveau d'instruction requis", NI_OPTIONS, index=6)
            offre_lieu  = st.text_input("Lieu du poste (commune)", placeholder="CHERAGA")
        with c2:
            offre_diplome = st.text_input("Diplôme requis", placeholder="Génie informatique")
            offre_exp     = st.number_input("Expérience requise (années)", 0, 30, 2)
        with c3:
            offre_metier = st.text_input("Intitulé du poste", placeholder="Développeur logiciel")
            offre_date   = st.date_input("Date de l'offre", value=date.today())
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔍  Trouver les meilleurs candidats", type="primary", use_container_width=True):
        if not offre_metier.strip():
            st.error("Veuillez renseigner au minimum l'intitulé du poste.")
            st.stop()

        offer_dict = {
            "offre_ni":        offre_ni,
            "offre_diplome":   offre_diplome,
            "offre_exp_years": int(offre_exp),
            "offre_metier":    offre_metier,
            "offre_lieu":      offre_lieu,
            "date_offre":      offre_date.isoformat(),
        }

        st.markdown("---")
        st.markdown('<div class="shdr">Offre soumise</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="profile-card">
          <h3>Détails de votre offre</h3>
          <span class="profile-tag">💼 <b>{offre_metier or '—'}</b></span>
          <span class="profile-tag">🎓 <b>{offre_ni}</b></span>
          <span class="profile-tag">📁 <b>{offre_diplome or 'Non spécifié'}</b></span>
          <span class="profile-tag">⏱ <b>{offre_exp} ans</b> requis</span>
          <span class="profile-tag">📍 <b>{offre_lieu or 'Non spécifié'}</b></span>
          <span class="profile-tag">📅 <b>{offre_date.strftime('%d/%m/%Y')}</b></span>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Recherche des candidats compatibles…"):
            matches = find_best_candidates(
                offer_dict, db, scorer,
                top_n=top_n, min_score=float(min_score), lambda_=lambda_,
            )

        if not matches:
            st.markdown('<div class="nores">😕 Aucun candidat correspondant trouvé.<br>'
                        '<small>Essayez d\'élargir les critères ou de réduire le score minimum.</small></div>',
                        unsafe_allow_html=True)
            st.stop()

        st.markdown(
            f'<div class="shdr">Top {len(matches)} candidats · λ={lambda_:.2f}</div>',
            unsafe_allow_html=True)

        for i, m in enumerate(matches):
            anc     = m.get("anciennete_days", 0)
            anc_str = f"{anc // 365} ans" if anc >= 365 else f"{anc} jours"
            render_card(
                match    = m,
                idx      = i,
                title    = m["demandeur_metier"] or "Profil sans métier",
                subtitle = (f"📍 {m['demandeur_commune']} &nbsp;·&nbsp; "
                            f"🎓 {m['demandeur_ni']} &nbsp;·&nbsp; "
                            f"⏱ {m['demandeur_exp_years']} ans d'exp. &nbsp;·&nbsp; "
                            f"📁 {m['demandeur_diplome'] or 'Diplôme non spécifié'}"),
                why_html = why_candidate(m, offer_dict),
                meta_items = [
                    f"C1 <b>{m['criterion_scores'].get('C1',0):.2f}</b>",
                    f"C2 <b>{m['criterion_scores'].get('C2',0):.2f}</b>",
                    f"C3 <b>{m['criterion_scores'].get('C3',0):.2f}</b>",
                    f"Ancienneté : <b>{anc_str}</b>",
                    f"C6 <b>{m['criterion_scores'].get('C6',0):.2f}</b>",
                    f"📈 {m.get('candidate_frequency',0)} hist.",
                ],
            )

        # Comparison table
        st.markdown("---")
        st.markdown('<div class="shdr">Comparaison</div>', unsafe_allow_html=True)
        try:
            import pandas as pd
            df = pd.DataFrame({
                "":         [f"{MEDALS[i]} #{i+1}" for i in range(len(matches))],
                "Métier":   [m["demandeur_metier"][:32] for m in matches],
                "Commune":  [m["demandeur_commune"] for m in matches],
                "TE":       [m["employability_score"] for m in matches],
                "Classif.": [m["classification"] for m in matches],
                "C1": [round(m["criterion_scores"]["C1"],2) for m in matches],
                "C2": [round(m["criterion_scores"]["C2"],2) for m in matches],
                "C3": [round(m["criterion_scores"]["C3"],2) for m in matches],
                "C6": [round(m["criterion_scores"]["C6"],2) for m in matches],
                "MMR":[round(m.get("mmr_score",0),3) for m in matches],
            }).set_index("")

            def _hl(val):
                if isinstance(val, float) and val > 1:
                    h = score_hex(val).lstrip("#")
                    r,g,b = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
                    return f"color:rgb({r},{g},{b});font-weight:bold"
                return ""

            st.dataframe(df.style.applymap(_hl, subset=["TE"]), use_container_width=True)
            st.download_button("⬇️ Télécharger CSV",
                               df.to_csv().encode("utf-8"),
                               "recommandations_candidats.csv", "text/csv")
        except ImportError:
            for i, m in enumerate(matches):
                st.write(f"#{i+1}: {m['demandeur_metier']} — {m['employability_score']:.1f}/100")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"Modèle ML (Logistic Regression) · {total_samples:,} placements réels ANEM · "
    f"Diversité MMR (λ={lambda_:.2f}) · Scoring C1–C6 avec correspondance floue (thefuzz)"
)