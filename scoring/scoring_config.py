"""
scoring_config.py  (v2 — ANEM real data)
-----------------------------------------
Single source of truth for all scoring matrices, strategy weights,
and thresholds. All values come directly from Apparaiment-Strategy.xlsx.

Criteria (C1–C6):
    C1  Niveau d'instruction    FUZZY  (matrix M_NI)
    C2  Diplômes                FUZZY  (M6.1 specialité × M6.2 grade)
    C3  Expériences             FUZZY  (M5.1 years × M5.2 métier match)
    C4  Langues                 EXACT  (matrix M_LANG — absent in dataset → 1.0)
    C5  Ancienneté inscription  EXACT  (banded lookup table)
    C6  Résidence               EXACT  (matrix M_RESIDENCE, 3 portée scopes)

Strategies (S0–S3):
    S3  Orientée cadre           → University graduates / executives
    S2  Orientée professionalité → Mid-level professionals
    S1  Orientée exécution       → Blue-collar / execution workers
    S0  Distribution uniforme    → Default / unknown

Final score:
    TE = Σ (w_i × score_i) / Σ w_i    (normalized weighted avg, 0–100)
"""

# ── C1: Niveau d'instruction — fuzzy matrix ───────────────────────────────────
# Source: sheet "Niveau Instruction"
# M_NI[required][found] → score ∈ [0, 1]
# Rows = what the OFFER requires; Cols = what the CANDIDATE has.

NI_CANONICAL = {
    "sans niveau":      "sans",
    "sans instruction": "sans",
    "primaire":         "primaire",
    "moyen":            "moyen",
    "secondaire 1as":   "secondaire",
    "secondaire 2as":   "secondaire",
    "secondaire 3as":   "secondaire",
    "supérieur 1":      "universitaire",
    "supérieur 2":      "universitaire",
    "universitaire":    "universitaire",
}

M_NI = {
    "sans":          {"sans": 1.0, "primaire": 0.7,  "moyen": 0.3,  "secondaire": 0.1,  "universitaire": 0.0},
    "primaire":      {"sans": 0.3, "primaire": 1.0,  "moyen": 0.5,  "secondaire": 0.2,  "universitaire": 0.0},
    "moyen":         {"sans": 0.0, "primaire": 0.3,  "moyen": 1.0,  "secondaire": 0.5,  "universitaire": 0.0},
    "secondaire":    {"sans": 0.0, "primaire": 0.0,  "moyen": 0.3,  "secondaire": 1.0,  "universitaire": 0.5},
    "universitaire": {"sans": 0.0, "primaire": 0.0,  "moyen": 0.0,  "secondaire": 0.5,  "universitaire": 1.0},
}


# ── C2: Diplôme — specialité similarity ──────────────────────────────────────
# Source: sheet "Diplômes" M6.1
# SP(Diplôme) = M6.1 (specialité match) — grade (M6.2) approximated via C1.
# Specialité match is inferred from string similarity (see scoring_engine.py).

DIPLOME_MEME_SPECIALITE = 1.0   # exact diploma string match
DIPLOME_MEME_FILIERE    = 0.7   # first word (field) matches
DIPLOME_MEME_DOMAINE    = 0.4   # NI level matches (domain-level similarity)
DIPLOME_AUTRES          = 0.1   # fallback — completely different


# ── C3: Expérience — years × métier match ─────────────────────────────────────
# Source: sheet "Expériences" M5.1 and M5.2
# SP(Expérience) = M5.1[years_band] × M5.2[métier_proximity]

def years_to_band(years: int) -> str:
    """Maps raw year count to the 5-band system used in M5.1."""
    if years <= 1:  return "<=1"
    if years <= 3:  return "<=3"
    if years <= 5:  return "<=5"
    if years < 10:  return "<10"
    return "10+"

# M_EXP_YEARS[required_band][found_band] → score ∈ [0, 1]
M_EXP_YEARS = {
    "<=1": {"<=1": 1.00, "<=3": 0.95, "<=5": 0.85, "<10": 0.70, "10+": 0.60},
    "<=3": {"<=1": 0.95, "<=3": 1.00, "<=5": 0.90, "<10": 0.80, "10+": 0.70},
    "<=5": {"<=1": 0.75, "<=3": 0.90, "<=5": 1.00, "<10": 0.90, "10+": 0.80},
    "<10": {"<=1": 0.40, "<=3": 0.65, "<=5": 0.85, "<10": 1.00, "10+": 0.95},
    "10+": {"<=1": 0.20, "<=3": 0.40, "<=5": 0.65, "<10": 0.90, "10+": 1.00},
}

# M_EXP_METIER[proximity_key] → score ∈ [0, 1]
M_EXP_METIER = {
    "meme_emploi":  1.00,   # candidate job title == offer job title
    "meme_metier":  0.85,   # first word of job title matches
    "meme_domaine": 0.40,   # NI-level domain overlap (heuristic)
    "autre":        0.20,   # no obvious match
}


# ── C5: Ancienneté inscription ────────────────────────────────────────────────
# Source: sheet "Ancienneté"
# anciennete_days = Date_Offre − Demande_date_Inscription

def score_anciennete(days: int) -> float:
    """Returns ancienneté score ∈ [0, 1] from registration seniority in days."""
    if days < 0:      return 0.00   # Registered AFTER offer — penalised
    if days < 180:    return 0.35   # < 6 months
    if days < 365:    return 0.55   # 6–12 months
    if days < 545:    return 0.70   # 12–18 months
    if days < 730:    return 0.80   # 18–24 months
    if days < 1095:   return 0.90   # 2–3 years
    return 1.00                     # 3+ years


# ── C6: Résidence / mobilité géographique ─────────────────────────────────────
# Source: sheet "Résidence"
# All 57 work locations in dataset are within Wilaya 16 (Alger).
# Proximity classification:
#   meme_commune → exact string match between Lieu_Travail and Commune_Residence
#   meme_wilaya  → both in WILAYA_ALGER_COMMUNES set
#   autres       → candidate lives outside Alger

# M_RESIDENCE[portee_scope][proximity] → score ∈ [0, 1]
M_RESIDENCE = {
    "S1": {"meme_commune": 1.0, "meme_wilaya": 0.7, "limitrophe": 0.0, "meme_region": 0.0, "autres": 0.0},
    "S2": {"meme_commune": 1.0, "meme_wilaya": 1.0, "limitrophe": 0.7, "meme_region": 0.2, "autres": 0.0},
    "S3": {"meme_commune": 1.0, "meme_wilaya": 1.0, "limitrophe": 1.0, "meme_region": 1.0, "autres": 0.2},
}

DEFAULT_RESIDENCE_SCOPE = "S2"   # most Alger-area jobs

WILAYA_ALGER_COMMUNES = {
    "ALGER", "EL ACHOUR", "OUED SMAR", "CHERAGA", "EL HARRACH",
    "BIR MOURAD RAIS", "BIR KHADEM", "BORDJ EL BAHRI", "DAR EL BEIDA",
    "BIRTOUTA", "LES EUCALYPTUS", "TASSALA EL MERDJA", "DJISR KSENTINA",
    "SAOULA", "BABA ALI", "BABA HASSEN", "BEN AKNOUN", "BENI MESSOUS",
    "BOLOUGINE", "BOUZAREAH", "BIRKHADEM", "DELY BRAHIM", "DRARIA",
    "EL BIAR", "EL MARSA", "HAMMAMET", "HERAOUA", "HUSSEIN DEY",
    "KHRAICIA", "KOUBA", "MAHELMA", "MOHAMMADIA", "OULED CHEBEL",
    "OULED FAYET", "RAHMANIA", "RAIS HAMIDOU", "REGHAÏA", "ROUIBA",
    "SAID HAMDINE", "SIDI ABDELLAH", "SIDI MOUSSA", "SOUIDANIA",
    "STAOUELI", "TESSALA EL MERDJA", "ZERALDA",
}


# ── Strategy weights (C1–C6) ──────────────────────────────────────────────────
# Source: sheet "Stratégies" — raw integer weights, normalised to sum=1.

RAW_STRATEGY_WEIGHTS = {
    "S3": {"C1": 3, "C2": 2, "C3": 1, "C4": 1, "C5": 1, "C6": 1},
    "S2": {"C1": 2, "C2": 1, "C3": 2, "C4": 1, "C5": 2, "C6": 2},
    "S1": {"C1": 2, "C2": 1, "C3": 1, "C4": 0, "C5": 3, "C6": 3},
    "S0": {"C1": 1, "C2": 1, "C3": 1, "C4": 1, "C5": 1, "C6": 1},
}

def get_normalized_weights(strategy: str) -> dict:
    """Returns weights normalised to sum=1 for a given strategy code."""
    raw   = RAW_STRATEGY_WEIGHTS.get(strategy, RAW_STRATEGY_WEIGHTS["S0"])
    total = sum(raw.values())
    return {k: round(v / total, 4) for k, v in raw.items()}


# ── Strategy auto-detection from NI level ─────────────────────────────────────
NI_TO_STRATEGY = {
    "universitaire": "S3",
    "secondaire":    "S2",
    "moyen":         "S1",
    "primaire":      "S1",
    "sans":          "S0",
}


# ── Classification thresholds ─────────────────────────────────────────────────
CLASSIFICATION_THRESHOLDS = [
    (75, "Optimale"),
    (50, "Bonne"),
    (25, "Faible"),
    (0,  "Nulle"),
]
