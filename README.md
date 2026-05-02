# ANEM ML Agent — Resume Scoring with Logistic Regression

## Architecture

```
ml_agent/
├── ml_agent.py                  ← Main entry point (CLI)
├── requirements.txt
├── ml_weight_cache.json         ← Auto-generated after training
│
├── scoring/                     ← Your existing scoring engine (unchanged)
│   ├── scoring_config.py
│   ├── scoring_engine.py
│   └── score_profiles.py
│
├── resume_parser/
│   └── parser.py                ← Extracts fields from .txt resumes
│
└── agent/
    ├── features.py              ← Converts records → 20-feature numpy vectors
    ├── trainer.py               ← Trains LR per strategy, extracts importances
    └── dynamic_scorer.py        ← Drop-in scorer with ML weight overrides
```

## Setup

```bash
cd ml_agent
pip install -r requirements.txt

# Create .env with your MongoDB Atlas URI:
echo "MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/" > .env
```

## Usage

### 1 — Train on the 37,358 real placements
```bash
python ml_agent.py --train
```
This will:
- Fetch all placement records from `employability_db.placements`
- Generate synthetic negative samples (shuffled mismatches, 1:1 ratio)
- Train one `LogisticRegression` per strategy (S0, S1, S2, S3)
- Extract per-strategy feature importances from |LR coefficients|
- Blend ML importances (50%) with hand-tuned base weights (50%)
- Push `ml_weight_override` documents back to `referential` collection
- Save `ml_weight_cache.json` locally

### 2 — Score a new .txt resume
```bash
python ml_agent.py --resume /path/to/candidate.txt \
    --offre-ni "Supérieur 1" \
    --offre-diplome "Génie civil" \
    --offre-exp 2 \
    --offre-metier "Ingénieur" \
    --offre-lieu "CHERAGA" \
    --date-offre "2025-06-01"
```

### 3 — Train then immediately score
```bash
python ml_agent.py --train --resume /path/to/candidate.txt ...
```

### 4 — Show current ML weight overrides
```bash
python ml_agent.py --show-weights
```

### 5 — Demo mode (no MongoDB, uses synthetic data)
```bash
python ml_agent.py --demo
```

## How the ML loop works

```
MongoDB placements (37,358 rows)
           │
           ▼
  Positive samples (placed = 1)
  +
  Synthetic negatives (shuffled demandeur↔offre fields, label = 0)
           │
           ▼
  20-feature vector per sample:
    • C1–C6 criterion scores (5 floats)
    • offre_exp_years_norm, dem_exp_years_norm, anciennete_days_norm (3)
    • Strategy one-hot S0–S3 (4)
    • NI level one-hot (5)
    • Residence proximity one-hot (3)
           │
           ▼
  LogisticRegression (lbfgs, C=1.0, balanced)
  — one model per strategy —
           │
           ▼
  |LR coefficients| → per-criterion importances
  (features that map to C1–C6 are averaged)
           │
           ▼
  Blend: 50% ML + 50% base weights → normalise → weight overrides
           │
  ┌────────┴────────┐
  ▼                 ▼
MongoDB           local JSON
referential       ml_weight_cache.json
(upsert)
           │
           ▼
  DynamicScorer picks up overrides
  and uses them for all future scoring
```

## Weight override schema (stored in referential)

```json
{
  "type": "ml_weight_override",
  "strategy": "S2",
  "trained_at": "2025-06-01T12:00:00",
  "n_samples": 12483,
  "accuracy": 0.871,
  "feature_importances": {
    "c1_ni_match": 0.18,
    "c2_diplome_match": 0.09,
    "c3_exp_match": 0.22,
    ...
  },
  "criterion_importances": {
    "C1": 0.18, "C2": 0.09, "C3": 0.22,
    "C4": 1.00, "C5": 0.14, "C6": 0.11
  },
  "weight_overrides": {
    "C1": 0.2891, "C2": 0.1423, "C3": 0.2634,
    "C4": 0.0833, "C5": 0.1267, "C6": 0.0952
  }
}
```

## Resume parser fields extracted

| Field | Method |
|---|---|
| `demandeur_ni` | Regex keyword scan (bac levels, licence, master…) |
| `demandeur_diplome` | Regex field keywords (génie, informatique…) |
| `demandeur_exp_years` | Explicit "X ans d'expérience" OR sum of date ranges |
| `demandeur_metier` | "Poste:" lines, then job-title keyword scan |
| `demandeur_commune` | "Adresse/Commune:" prefix, then known commune lookup |
| `date_inscription` | "Date d'inscription:" prefix |
| `languages` | Language keyword scan |

## Integration in your existing code

```python
from agent.dynamic_scorer import DynamicScorer
from resume_parser.parser import parse_resume

# Load ML weights (from cache or DB)
scorer = DynamicScorer.from_cache()          # offline
scorer = DynamicScorer.from_mongo(db)        # live

# Score a parsed resume against an offer
parsed = parse_resume("candidate.txt")
result = scorer.score_resume(parsed, offer_record)
# → same schema as scoring_engine.compute_employability_score()
#   plus ml_override_active, ml_meta, parsed_fields
```
