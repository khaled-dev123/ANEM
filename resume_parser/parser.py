"""
resume_parser/parser.py
-----------------------
Extracts structured fields from a plain-text resume (.txt file).

Handles French / Arabic-influenced Algerian CV conventions.
All logic is regex + keyword heuristics — no external NLP dependency.

Output dict is compatible with scoring_engine.compute_employability_score().

Fields extracted:
    demandeur_ni          str   NI level (e.g. "Supérieur 1")
    demandeur_diplome     str   Diploma / field of study
    demandeur_exp_years   int   Total years of professional experience
    demandeur_metier      str   Most recent / primary job title
    demandeur_commune     str   City / commune of residence
    date_inscription      str   Registration date (ISO, today if absent)
    languages             list  Detected languages

    raw_text              str   Full normalised text (for ML feature extraction)
"""

import re
import os
from datetime import date, datetime
from pathlib import Path


# ── NI level keywords (French/Arabic transliterated) ─────────────────────────

_NI_PATTERNS = [
    (r"\bdoctorat\b",                          "Universitaire"),
    (r"\bph\.?d\b",                            "Universitaire"),
    (r"\bmaster\b|\bmagist(er|ère|re)\b",      "Supérieur 2"),
    (r"\bingénieur\b|\bengineer\b",            "Supérieur 2"),
    (r"\blicen[cs]e?\b|\bbac\s*\+\s*3\b",     "Supérieur 1"),
    (r"\bbac\s*\+\s*5\b",                      "Supérieur 2"),
    (r"\bbac\s*\+\s*4\b",                      "Supérieur 1"),
    (r"\bbac\s*\+\s*2\b|\bbts\b|\bdut\b",      "Supérieur 1"),
    (r"\bbaccalauréat\b|\bbac\s*\+\s*0\b|\bterminale\b", "Secondaire 3AS"),
    (r"\bsecondaire\b|\blycée\b",              "Secondaire 2AS"),
    (r"\bcollège\b|\bmoyen\b|\bbem\b",         "Moyen"),
    (r"\bprimaire\b|\bécole\s+primaire\b",     "Primaire"),
    (r"\bsans\s+(niveau|instruction|diplôme)\b", "Sans niveau"),
]

_DIPLOME_SECTION = re.compile(
    r"(formation|éducation|diplôme|études|scolarité|instruction)",
    re.IGNORECASE,
)
_FIELD_RE = re.compile(
    r"(génie\s+\w+|informatique|gestion|commerce|droit|médecine|économie"
    r"|finance|comptabilit[eé]|électronique|mécanique|chimie|physique"
    r"|biologie|architecture|agronomie|psychologie|sociologie"
    r"|management|marketing|ressources\s+humaines|logistique)",
    re.IGNORECASE,
)


# ── Experience year extractor ─────────────────────────────────────────────────

_EXP_EXPLICIT = re.compile(
    r"(\d+)\s*(?:ans?|années?|an[s]?\s+d.expérience|years?\s+of\s+exp)",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"(\d{4})\s*[-–]\s*(\d{4}|aujourd.hui|présent|en\s+cours|actuel\w*|present|current)",
    re.IGNORECASE,
)


def _extract_exp_years(text: str) -> int:
    """Returns total years of experience from text."""
    # 1. Explicit mention: "5 ans d'expérience"
    explicit = _EXP_EXPLICIT.findall(text)
    if explicit:
        return max(int(x) for x in explicit)

    # 2. Sum date ranges
    current_year = date.today().year
    total = 0
    for m in _DATE_RANGE_RE.finditer(text):
        start = int(m.group(1))
        end_raw = m.group(2).strip()
        if re.match(r"\d{4}", end_raw):
            end = int(end_raw)
        else:
            end = current_year
        if 1970 <= start <= current_year and start <= end <= current_year + 1:
            total += end - start
    return min(total, 40)   # cap at 40 to match scoring_engine


# ── Job title / métier extractor ──────────────────────────────────────────────

_METIER_SECTION = re.compile(
    r"(expérience\s+professionnelle|parcours\s+professionnel|emploi|poste|"
    r"fonction|titre|position|expérience\s+de\s+travail|work\s+experience)",
    re.IGNORECASE,
)
_TITLE_LINE_RE = re.compile(
    r"^(?:poste\s*:?\s*|titre\s*:?\s*|fonction\s*:?\s*|position\s*:?\s*)(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_JOB_KEYWORDS = re.compile(
    r"\b(ingénieur|technicien|responsable|directeur|chef|gestionnaire|"
    r"comptable|analyst[e]?|développeur|programmeur|consultant|formateur|"
    r"commercial|vendeur|assistant[e]?|agent|opérateur|agent|"
    r"chargé\s+de|manager|expert|conseiller|infirmier|médecin|professeur"
    r"|enseignant|architecte|juriste|auditeur|contrôleur|logisticien)\b",
    re.IGNORECASE,
)


def _extract_metier(text: str) -> str:
    """Returns the most prominent job title found in text."""
    # Explicit "Poste: ..." lines
    m = _TITLE_LINE_RE.search(text)
    if m:
        return m.group(1).strip()[:80]

    # Keyword scan — return first matching line that contains a job keyword
    for line in text.splitlines():
        line = line.strip()
        if _JOB_KEYWORDS.search(line) and 3 <= len(line.split()) <= 10:
            return line[:80]

    return ""


# ── Commune / city extractor ──────────────────────────────────────────────────

_ALGER_COMMUNES = {
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

_COMMUNE_RE = re.compile(
    r"(?:adresse|commune|résidence|ville|wilaya|localité)\s*:?\s*([^\n,;]+)",
    re.IGNORECASE,
)


def _extract_commune(text: str) -> str:
    m = _COMMUNE_RE.search(text)
    if m:
        candidate = m.group(1).strip().upper()[:40]
        return candidate
    # Scan for known communes directly
    upper = text.upper()
    for c in _ALGER_COMMUNES:
        if c in upper:
            return c
    return "ALGER"   # default


# ── Language detector ─────────────────────────────────────────────────────────

_LANG_KEYWORDS = {
    "français":  re.compile(r"\bfranc[eé]ais\b|\bfrench\b|\bFLE\b", re.IGNORECASE),
    "anglais":   re.compile(r"\banglais\b|\benglish\b|\bTOEIC\b|\bIELTS\b|\bTOEFL\b", re.IGNORECASE),
    "arabe":     re.compile(r"\barabe\b|\barabic\b", re.IGNORECASE),
    "espagnol":  re.compile(r"\bespagnol\b|\bspanish\b", re.IGNORECASE),
    "allemand":  re.compile(r"\ballemand\b|\bgerman\b|\bdeutsch\b", re.IGNORECASE),
    "tamazight": re.compile(r"\btamazight\b|\bberbère\b", re.IGNORECASE),
}


def _extract_languages(text: str) -> list:
    return [lang for lang, pat in _LANG_KEYWORDS.items() if pat.search(text)]


# ── Registration date ─────────────────────────────────────────────────────────

_DATE_RE = re.compile(
    r"(?:date\s+d.inscription|inscrit\s+le|enregistré\s+le)\s*:?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _extract_registration_date(text: str) -> str:
    m = _DATE_RE.search(text)
    if m:
        raw = m.group(1)
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
    return date.today().isoformat()   # fallback = today


# ── NI level extractor ────────────────────────────────────────────────────────

def _extract_ni(text: str) -> str:
    for pattern, ni_label in _NI_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ni_label
    return "Moyen"   # conservative default


# ── Diploma / field extractor ─────────────────────────────────────────────────

def _extract_diplome(text: str) -> str:
    m = _FIELD_RE.search(text)
    if m:
        return m.group(0).strip()
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def parse_resume(path: str | Path) -> dict:
    """
    Parse a plain-text resume file and return a structured dict.

    Args:
        path: Path to the .txt resume file.

    Returns:
        Dict compatible with compute_employability_score() (demandeur_* fields
        pre-filled; offre_* fields left empty for the caller to fill).
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # Normalise whitespace
    text_clean = re.sub(r"\r\n", "\n", text)
    text_clean = re.sub(r"[ \t]+", " ", text_clean)

    ni             = _extract_ni(text_clean)
    diplome        = _extract_diplome(text_clean)
    exp_years      = _extract_exp_years(text_clean)
    metier         = _extract_metier(text_clean)
    commune        = _extract_commune(text_clean)
    date_inscr     = _extract_registration_date(text_clean)
    languages      = _extract_languages(text_clean)

    return {
        # Demandeur fields (scoring engine compatible)
        "demandeur_ni":          ni,
        "demandeur_diplome":     diplome,
        "demandeur_exp_years":   exp_years,
        "demandeur_metier":      metier,
        "demandeur_commune":     commune,
        "date_inscription":      date_inscr,
        # Extras
        "languages":             languages,
        "source_file":           str(path),
        "raw_text":              text_clean,
    }


def parse_resume_text(text: str, source_name: str = "<inline>") -> dict:
    """
    Same as parse_resume() but accepts raw text directly.
    Useful for tests and the ML feature extractor.
    """
    text_clean = re.sub(r"\r\n", "\n", text)
    text_clean = re.sub(r"[ \t]+", " ", text_clean)

    return {
        "demandeur_ni":         _extract_ni(text_clean),
        "demandeur_diplome":    _extract_diplome(text_clean),
        "demandeur_exp_years":  _extract_exp_years(text_clean),
        "demandeur_metier":     _extract_metier(text_clean),
        "demandeur_commune":    _extract_commune(text_clean),
        "date_inscription":     _extract_registration_date(text_clean),
        "languages":            _extract_languages(text_clean),
        "source_file":          source_name,
        "raw_text":             text_clean,
    }
