"""
Knowledge base facts for The Prescription Planner.

Every fact here comes from the Restriction Table PDF. The "ref" numbers in the comments are the
reference numbers in that PDF, so each fact can be traced to a source.

These facts were checked against sources (see the ref numbers). Do not change them without re-checking the source.
This is a course project, not a clinical tool.
"""

# ---- Conditions and their two candidate drugs (these are the Treats facts) ----
CONDITIONS = {
    "Hypertension": ["Lisinopril", "Amlodipine"],
    "HighCholesterol": ["Atorvastatin", "Simvastatin"],
    "AtrialFibrillation": ["Warfarin", "Apixaban"],
    "Type2Diabetes": ["Metformin", "Glipizide"],
    "ChronicPain": ["Ibuprofen", "Acetaminophen"],
}

# ---- Interacts(first, second, severity). Each pair is stored once, in this order. ----
INTERACTIONS = [
    ("Warfarin", "Ibuprofen", "Major"),         # ref 9
    ("Lisinopril", "Ibuprofen", "Moderate"),    # ref 1
    ("Apixaban", "Ibuprofen", "Moderate"),      # ref 15, 16
    ("Amlodipine", "Simvastatin", "Moderate"),  # ref 3, 8
    ("Simvastatin", "Warfarin", "Moderate"),    # ref 8
    ("Warfarin", "Acetaminophen", "Moderate"),  # ref 10
    ("Warfarin", "Glipizide", "Moderate"),      # ref 11, 25
    ("Warfarin", "Metformin", "Moderate"),      # ref 12, 25
]

# ---- RejectIfHas(drug, attribute): the drug is rejected if the patient has the attribute ----
REJECT_IF_HAS = [
    ("Lisinopril", "AngioedemaHistory"),                # ref 2
    ("Amlodipine", "SevereHypotension"),                # ref 5, 22
    ("Amlodipine", "HighGradeAorticStenosis"),          # ref 5, 22
    ("Atorvastatin", "ActiveLiverDisease"),             # ref 6, 7
    ("Simvastatin", "ActiveLiverDisease"),              # ref 8
    ("Warfarin", "ActiveBleeding"),                     # ref 13, 14
    ("Warfarin", "BleedingTendency"),                   # ref 13, 14
    ("Apixaban", "ActiveBleeding"),                     # ref 16
    ("Apixaban", "SevereLiverImpairment"),              # ref 16
    ("Metformin", "SevereKidneyImpairment"),            # ref 17
    ("Metformin", "ModerateKidneyImpairment"),          # ref 17
    ("Metformin", "ActiveLiverDisease"),                # ref 17
    ("Ibuprofen", "ChronicKidneyDisease"),              # ref 20
    ("Ibuprofen", "SevereKidneyImpairment"),            # ref 20
    ("Ibuprofen", "ActiveLiverDisease"),                # ref 20
    ("Ibuprofen", "Hyperkalemia"),                      # ref 20
    ("Acetaminophen", "SevereLiverImpairment"),         # ref 20
]

# ---- FlagIfHas(drug, attribute): the drug is allowed but flagged if the patient has the attribute ----
FLAG_IF_HAS = [
    ("Lisinopril", "RenalArteryStenosis"),              # ref 2
    ("Lisinopril", "ChronicKidneyDisease"),             # ref 2
    ("Lisinopril", "HeartFailure"),                     # ref 2
    ("Amlodipine", "HeartFailure"),                     # ref 5, 22
    ("Amlodipine", "SevereLiverImpairment"),            # ref 5, 22
    ("Amlodipine", "Elderly"),                          # ref 5, 22
    ("Atorvastatin", "Elderly"),                        # ref 6, 7
    ("Simvastatin", "Elderly"),                         # ref 8
    ("Warfarin", "Elderly"),                            # ref 13, 14
    ("Apixaban", "ModerateLiverImpairment"),            # ref 16
    ("Metformin", "AgeAtLeast80"),                      # ref 17
    ("Glipizide", "ChronicKidneyDisease"),              # ref 18, 19
    ("Glipizide", "SevereKidneyImpairment"),            # ref 18, 19
    ("Glipizide", "ModerateKidneyImpairment"),          # ref 18, 19
    ("Glipizide", "ActiveLiverDisease"),                # ref 18, 19
    ("Glipizide", "Elderly"),                           # ref 18, 19
    ("Ibuprofen", "ModerateKidneyImpairment"),          # ref 20
]

# ---- Pregnancy facts ----
REJECT_IF_PREGNANT = [
    "Lisinopril",       # ref 2
    "Atorvastatin",     # ref 23
    "Simvastatin",      # ref 23, 8
    "Warfarin",         # ref 14
    "Apixaban",         # ref 16
    "Ibuprofen",        # ref 21
]
FLAG_IF_PREGNANT = [
    "Amlodipine",       # ref 22
    "Glipizide",        # ref 19
    "Acetaminophen",    # ref 24
]

# ---- Attributes ----
# Yes/no history items that the user types into the patient profile (the "has" list).
TYPED_ATTRIBUTES = [
    "AngioedemaHistory",
    "RenalArteryStenosis",
    "ChronicKidneyDisease",
    "HeartFailure",
    "SevereHypotension",
    "HighGradeAorticStenosis",
    "ActiveBleeding",
    "BleedingTendency",
    "Hyperkalemia",
    "ModerateLiverImpairment",
    "SevereLiverImpairment",
]

# Attributes the program builds from numbers (rules in SPEC.md, section 5).
BUILT_ATTRIBUTES = [
    "Elderly",
    "AgeAtLeast80",
    "SevereKidneyImpairment",
    "ModerateKidneyImpairment",
    "LowWeight",
    "HighCreatinine",
    "ActiveLiverDisease",
]

# ---- Number cut-offs (project choices, see SPEC.md) ----
ELDERLY_AGE_YEARS = 65             # Elderly if age >= 65
VERY_OLD_AGE_YEARS = 80            # AgeAtLeast80 if age >= 80
SEVERE_KIDNEY_EGFR_BELOW = 30      # SevereKidneyImpairment if eGFR < 30
MODERATE_KIDNEY_EGFR_BELOW = 45    # ModerateKidneyImpairment if 30 <= eGFR < 45
LOW_WEIGHT_KG_AT_MOST = 60         # LowWeight if weight <= 60 kg
HIGH_CREATININE_AT_LEAST = 1.5     # HighCreatinine if creatinine >= 1.5 mg/dL

# ---- Ranking weights (project choices, not clinical ratings) ----
MODERATE_INTERACTION_POINTS = 3
OTHER_FLAG_POINTS = 1
DOSE_NOTE_POINTS = 0

# Apixaban dose note: needs at least 2 of these 3 attributes.
APIXABAN_DOSE_NOTE_ATTRIBUTES = ["AgeAtLeast80", "LowWeight", "HighCreatinine"]
APIXABAN_DOSE_NOTE_MINIMUM = 2
