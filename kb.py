"""
The knowledge base (KB) for The Prescription Planner: facts, rules, and the forward chainer.

A fact is a tuple with the predicate name first, for example ("EGFR", "Patient3", 40).
A rule is plain data: a list of condition patterns, a list of number checks, and one conclusion pattern.
Words that start with "?" in a pattern are variables, for example "?patient".

The forward chainer only ever ADDS facts. No rule uses "not", and no fact is ever deleted.
This is a course project, not a clinical tool.
"""
import math

import kb_facts as facts

# Assumption 7: adults only. This is a project choice to keep the planner simple.
ADULT_AGE_YEARS = 18

# eGFR input limits, project choices to catch typing mistakes (for example 400 typed instead of 40).
# They are not clinical limits: the sources give no maximum (a healthy eGFR is around 90 or above).
# An eGFR outside 0 to 200 is refused; above 150 it is accepted, but the user is warned to check it.
EGFR_LOWEST = 0
EGFR_HIGHEST = 200
EGFR_UNUSUALLY_HIGH = 150

# Age, weight and creatinine limits, also project choices to catch typing mistakes. They are not clinical
# limits (SPEC section 12, decision 24). An age above AGE_HIGHEST is refused (no verified person has lived past
# 122). The other values are accepted, but the user is warned and asked to confirm them.
# The low side matters too: weight only changes a result at 60 kg or less, and creatinine only at 1.5 or more,
# so 7 typed for 70 kg, or 0.15 typed for 1.5, would change the result.
AGE_HIGHEST = 130
AGE_UNUSUALLY_HIGH = 110
WEIGHT_UNUSUALLY_LOW = 35
WEIGHT_UNUSUALLY_HIGH = 300
CREATININE_UNUSUALLY_LOW = 0.3
CREATININE_UNUSUALLY_HIGH = 10

# Hard limits for weight and creatinine (decision 27, also project choices to catch typing mistakes, not
# clinical limits): a value outside them is refused and asked again. Values inside them but outside the "unusual"
# limits above are accepted, and the report adds a note asking the reader to check them.
WEIGHT_LOWEST = 20
WEIGHT_HIGHEST = 500
CREATININE_HIGHEST = 20


# ---------------------------------------------------------------------------
# Checking the patient's age before planning
# ---------------------------------------------------------------------------

def age_problem(patient):
    """
    Return a message if the planner cannot make a plan because of the patient's age, otherwise None.
    The age is required: without it we cannot tell if the patient is an adult, and every age-based
    caution would be silently left out.
    """
    age = patient.get("age")
    if age is None:
        return ("The Prescription Planner needs the patient's age. "
                "No age was recorded for this patient, so no plan was made.")
    if age < ADULT_AGE_YEARS:
        return ("The Prescription Planner is designed for adults. "
                f"This patient (age {age}) is outside what it covers, so no plan was made.")
    return None


def all_drug_names():
    """The 10 drugs the KB knows, in the order of CONDITIONS."""
    names = []
    for drugs in facts.CONDITIONS.values():
        for drug in drugs:
            names.append(drug)
    return names


def current_medication_problem(patient):
    """
    Return a message if the patient takes a medicine the KB does not know, otherwise None.
    The KB only has facts about its 10 drugs, so for any other drug it could not check anything.
    Treating an unknown drug as safe would be misleading, so the planner stops instead.
    """
    known_drugs = all_drug_names()
    for drug in patient.get("current_medications", []):
        if drug not in known_drugs:
            return (f"The Prescription Planner only knows these {len(known_drugs)} drugs: "
                    f"{', '.join(known_drugs)}. \"{drug}\" is not one of them, so no plan was made.")
    return None


def egfr_problem(patient):
    """
    Return a message if the eGFR was entered but is not a number from EGFR_LOWEST to EGFR_HIGHEST,
    otherwise None. A missing eGFR is fine (closed world: no kidney attribute is made).
    """
    egfr = patient.get("egfr")
    if egfr is None:
        return None
    if isinstance(egfr, (int, float)) and EGFR_LOWEST <= egfr <= EGFR_HIGHEST:
        return None
    return (f"The eGFR must be a number from {EGFR_LOWEST} to {EGFR_HIGHEST}. "
            f"This patient's eGFR was entered as {egfr}, so no plan was made.")


def is_real_number(value):
    """True for an ordinary number. False for text, and for "not a number" (NaN) or infinity, which are not
    real measurements (math.isfinite is from the standard library)."""
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def number_problem(patient):
    """
    Return a message if the age, weight or creatinine cannot be planned with, otherwise None:
    - NaN or infinity (SPEC section 12, decision 23). Without this, a NaN age would even pass the age check,
      because "NaN < 18" is False. (eGFR is covered by egfr_problem.)
    - an age that is not a whole number, or above AGE_HIGHEST (decision 24). Under 18 is left to age_problem,
      which gives the "designed for adults" message.
    - a weight outside WEIGHT_LOWEST to WEIGHT_HIGHEST, or a creatinine of 0 or less or above CREATININE_HIGHEST
      (decision 27).
    """
    age = patient.get("age")
    if age is not None:
        if not is_real_number(age) or age != int(age) or age > AGE_HIGHEST:
            return (f"The age must be a whole number from {ADULT_AGE_YEARS} to {AGE_HIGHEST}. "
                    "Please correct the age and try again.")
    weight = patient.get("weight")
    if weight is not None and (not is_real_number(weight) or weight < WEIGHT_LOWEST or weight > WEIGHT_HIGHEST):
        return (f"The weight must be a number from {WEIGHT_LOWEST} to {WEIGHT_HIGHEST}. "
                "Please correct the weight and try again.")
    creatinine = patient.get("creatinine")
    if creatinine is not None and (not is_real_number(creatinine) or creatinine <= 0
                                   or creatinine > CREATININE_HIGHEST):
        return (f"The creatinine must be a number above 0 and up to {CREATININE_HIGHEST}. "
                "Please correct the creatinine and try again.")
    return None


def input_problem(patient):
    """Run the input checks before planning: the numbers, the age, the eGFR, then the current medications."""
    message = number_problem(patient)
    if message is not None:
        return message
    message = age_problem(patient)
    if message is not None:
        return message
    message = egfr_problem(patient)
    if message is not None:
        return message
    return current_medication_problem(patient)


# ---------------------------------------------------------------------------
# Building facts
# ---------------------------------------------------------------------------

def static_fact_list():
    """
    Turn the tables in kb_facts.py into fact tuples, as a list in the same order as kb_facts.py.
    These facts are the same for every patient. There are 61 of them:
    Treats, Interacts, RejectIfHas, FlagIfHas, RejectIfPregnant, FlagIfPregnant.
    (The order matters only for the "why?" explanation, so it always tries facts in the same order.)
    """
    fact_list = []
    for condition, drugs in facts.CONDITIONS.items():
        for drug in drugs:
            fact_list.append(("Treats", drug, condition))
    for first_drug, second_drug, severity in facts.INTERACTIONS:
        fact_list.append(("Interacts", first_drug, second_drug, severity))
    for drug, attribute in facts.REJECT_IF_HAS:
        fact_list.append(("RejectIfHas", drug, attribute))
    for drug, attribute in facts.FLAG_IF_HAS:
        fact_list.append(("FlagIfHas", drug, attribute))
    for drug in facts.REJECT_IF_PREGNANT:
        fact_list.append(("RejectIfPregnant", drug))
    for drug in facts.FLAG_IF_PREGNANT:
        fact_list.append(("FlagIfPregnant", drug))
    return fact_list


def static_facts():
    """The 61 static facts as a set (the forward chainer uses sets: no duplicates, fast lookup)."""
    return set(static_fact_list())


# The numbers in a patient profile, and the predicate name used for each one in a fact.
# eGFR is a number for how well the kidneys filter the blood (lower means weaker kidneys).
# Creatinine is a waste product in the blood that the kidneys remove, measured in mg/dL.
NUMBER_FIELDS = [
    ("age", "Age"),                 # years
    ("weight", "Weight"),           # kilograms
    ("egfr", "EGFR"),
    ("creatinine", "Creatinine"),
]


def patient_facts(patient):
    """
    Turn one patient profile (a dict) into fact tuples.
    Closed-world assumption (assumption 6): anything not recorded is treated as absent, so a missing
    number simply produces no fact, and we never guess a value.
    """
    name = patient["name"]
    known_facts = set()
    for condition in patient["needs"]:
        known_facts.add(("Needs", name, condition))
    for field, predicate in NUMBER_FIELDS:
        value = patient.get(field)
        if value is not None:
            known_facts.add((predicate, name, value))
    if patient.get("pregnant", False):
        known_facts.add(("Pregnant", name))
    # Assumption 5: allergies are per drug only (not per drug family).
    for drug in patient.get("allergies", []):
        known_facts.add(("Allergic", name, drug))
    # Assumption 4: yes/no history items (like HeartFailure) are typed in; they cannot be calculated.
    for attribute in patient.get("has", []):
        known_facts.add(("Has", name, attribute))
    # Medicines the patient already takes (missing means none, like allergies).
    for drug in patient.get("current_medications", []):
        known_facts.add(("Taking", name, drug))
    return known_facts


def attributes_of(known_facts, patient_name):
    """Collect the attribute names from every Has(patient, attribute) fact for this patient."""
    attributes = set()
    for fact in known_facts:
        if fact[0] == "Has" and fact[1] == patient_name:
            attributes.add(fact[2])
    return attributes


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------
# Each rule is a dict:
#   "name"        a short label, used when explaining
#   "conditions"  patterns that must ALL match known facts
#   "checks"      number comparisons, written (variable, operator, constant), tested after matching
#   "conclusion"  the pattern for the new fact
# The cut-off numbers come from kb_facts.py. They are project choices, not clinical ratings.

# B. Turning numbers into attributes (8 rules)
ATTRIBUTE_RULES = [
    # ∀patient, years, Age(patient, years), years ≥ 65 ➔ Has(patient, Elderly)
    {"name": "B1 Elderly",
     "conditions": [("Age", "?patient", "?years")],
     "checks": [("?years", ">=", facts.ELDERLY_AGE_YEARS)],
     "conclusion": ("Has", "?patient", "Elderly")},

    # ∀patient, years, Age(patient, years), years ≥ 80 ➔ Has(patient, AgeAtLeast80)
    {"name": "B2 AgeAtLeast80",
     "conditions": [("Age", "?patient", "?years")],
     "checks": [("?years", ">=", facts.VERY_OLD_AGE_YEARS)],
     "conclusion": ("Has", "?patient", "AgeAtLeast80")},

    # ∀patient, score, EGFR(patient, score), score < 30 ➔ Has(patient, SevereKidneyImpairment)
    {"name": "B3 SevereKidneyImpairment",
     "conditions": [("EGFR", "?patient", "?score")],
     "checks": [("?score", "<", facts.SEVERE_KIDNEY_EGFR_BELOW)],
     "conclusion": ("Has", "?patient", "SevereKidneyImpairment")},

    # ∀patient, score, EGFR(patient, score), score ≥ 30, score < 45 ➔ Has(patient, ModerateKidneyImpairment)
    {"name": "B4 ModerateKidneyImpairment",
     "conditions": [("EGFR", "?patient", "?score")],
     "checks": [("?score", ">=", facts.SEVERE_KIDNEY_EGFR_BELOW),
                ("?score", "<", facts.MODERATE_KIDNEY_EGFR_BELOW)],
     "conclusion": ("Has", "?patient", "ModerateKidneyImpairment")},

    # ∀patient, kilograms, Weight(patient, kilograms), kilograms ≤ 60 ➔ Has(patient, LowWeight)
    {"name": "B5 LowWeight",
     "conditions": [("Weight", "?patient", "?kilograms")],
     "checks": [("?kilograms", "<=", facts.LOW_WEIGHT_KG_AT_MOST)],
     "conclusion": ("Has", "?patient", "LowWeight")},

    # ∀patient, level, Creatinine(patient, level), level ≥ 1.5 ➔ Has(patient, HighCreatinine)
    {"name": "B6 HighCreatinine",
     "conditions": [("Creatinine", "?patient", "?level")],
     "checks": [("?level", ">=", facts.HIGH_CREATININE_AT_LEAST)],
     "conclusion": ("Has", "?patient", "HighCreatinine")},

    # Assumption 1: moderate or severe liver impairment counts as active liver disease.
    # ∀patient, Has(patient, ModerateLiverImpairment) ➔ Has(patient, ActiveLiverDisease)
    {"name": "B7 ActiveLiverDisease from moderate",
     "conditions": [("Has", "?patient", "ModerateLiverImpairment")],
     "checks": [],
     "conclusion": ("Has", "?patient", "ActiveLiverDisease")},

    # ∀patient, Has(patient, SevereLiverImpairment) ➔ Has(patient, ActiveLiverDisease)
    {"name": "B8 ActiveLiverDisease from severe",
     "conditions": [("Has", "?patient", "SevereLiverImpairment")],
     "checks": [],
     "conclusion": ("Has", "?patient", "ActiveLiverDisease")},
]

# A. Candidates (1 rule)
CANDIDATE_RULES = [
    # ∀patient, condition, drug, Needs(patient, condition), Treats(drug, condition) ➔ Candidate(patient, drug)
    {"name": "A1 Candidate",
     "conditions": [("Needs", "?patient", "?condition"),
                    ("Treats", "?drug", "?condition")],
     "checks": [],
     "conclusion": ("Candidate", "?patient", "?drug")},
]

# C. Checks on a chosen regimen (8 rules)
# The severity labels "Major" and "Moderate" are project choices, not clinical ratings.
# A Major interaction rejects the FIRST drug of the stored pair (the order used in kb_facts.py).
# Either way the whole regimen becomes invalid.
CHECK_RULES = [
    # ∀patient, drug, Chosen(patient, drug), Allergic(patient, drug) ➔ Rejected(patient, drug, Allergy)
    {"name": "C1 Rejected for allergy",
     "conditions": [("Chosen", "?patient", "?drug"),
                    ("Allergic", "?patient", "?drug")],
     "checks": [],
     "conclusion": ("Rejected", "?patient", "?drug", "Allergy")},

    # ∀patient, drug, attribute, Chosen(patient, drug), Has(patient, attribute), RejectIfHas(drug, attribute)
    #   ➔ Rejected(patient, drug, attribute)
    # In the code, RejectIfHas comes before Has. "And" does not depend on order, so the meaning is the same,
    # but this way the backward chainer (for "why?") first finds which attributes matter for the drug.
    {"name": "C2 Rejected for an attribute",
     "conditions": [("Chosen", "?patient", "?drug"),
                    ("RejectIfHas", "?drug", "?attribute"),
                    ("Has", "?patient", "?attribute")],
     "checks": [],
     "conclusion": ("Rejected", "?patient", "?drug", "?attribute")},

    # ∀patient, drug, attribute, Chosen(patient, drug), Has(patient, attribute), FlagIfHas(drug, attribute)
    #   ➔ Flagged(patient, drug, attribute)
    # FlagIfHas comes before Has, for the same reason as in rule C2.
    {"name": "C3 Flagged for an attribute",
     "conditions": [("Chosen", "?patient", "?drug"),
                    ("FlagIfHas", "?drug", "?attribute"),
                    ("Has", "?patient", "?attribute")],
     "checks": [],
     "conclusion": ("Flagged", "?patient", "?drug", "?attribute")},

    # ∀patient, drug, Chosen(patient, drug), Pregnant(patient), RejectIfPregnant(drug)
    #   ➔ Rejected(patient, drug, Pregnancy)
    {"name": "C4 Rejected for pregnancy",
     "conditions": [("Chosen", "?patient", "?drug"),
                    ("Pregnant", "?patient"),
                    ("RejectIfPregnant", "?drug")],
     "checks": [],
     "conclusion": ("Rejected", "?patient", "?drug", "Pregnancy")},

    # ∀patient, drug, Chosen(patient, drug), Pregnant(patient), FlagIfPregnant(drug)
    #   ➔ Flagged(patient, drug, Pregnancy)
    {"name": "C5 Flagged for pregnancy",
     "conditions": [("Chosen", "?patient", "?drug"),
                    ("Pregnant", "?patient"),
                    ("FlagIfPregnant", "?drug")],
     "checks": [],
     "conclusion": ("Flagged", "?patient", "?drug", "Pregnancy")},

    # ∀patient, first, second, severity, Chosen(patient, first), Chosen(patient, second),
    #   Interacts(first, second, severity) ➔ Conflict(patient, first, second, severity)
    {"name": "C6 Conflict between two chosen drugs",
     "conditions": [("Chosen", "?patient", "?first"),
                    ("Chosen", "?patient", "?second"),
                    ("Interacts", "?first", "?second", "?severity")],
     "checks": [],
     "conclusion": ("Conflict", "?patient", "?first", "?second", "?severity")},

    # ∀patient, first, second, Conflict(patient, first, second, Major)
    #   ➔ Rejected(patient, first, InteractionWith(second))
    {"name": "C7 Rejected for a Major interaction",
     "conditions": [("Conflict", "?patient", "?first", "?second", "Major")],
     "checks": [],
     "conclusion": ("Rejected", "?patient", "?first", ("InteractionWith", "?second"))},

    # ∀patient, first, second, Conflict(patient, first, second, Moderate)
    #   ➔ Flagged(patient, first, InteractionWith(second))
    {"name": "C8 Flagged for a Moderate interaction",
     "conditions": [("Conflict", "?patient", "?first", "?second", "Moderate")],
     "checks": [],
     "conclusion": ("Flagged", "?patient", "?first", ("InteractionWith", "?second"))},
]

# D. Apixaban dose note: two of three conditions (3 rules, one for each pair of conditions)
# Apixaban is one of the two drugs in the KB for atrial fibrillation (an irregular heartbeat).
# The note means "a lower dose may be needed". It does not reject or flag the drug.
DOSE_NOTE_RULES = [
    # ∀patient, Chosen(patient, Apixaban), Has(patient, AgeAtLeast80), Has(patient, LowWeight)
    #   ➔ DoseNote(patient, Apixaban, ReduceDose)
    {"name": "D1 Dose note: age and weight",
     "conditions": [("Chosen", "?patient", "Apixaban"),
                    ("Has", "?patient", "AgeAtLeast80"),
                    ("Has", "?patient", "LowWeight")],
     "checks": [],
     "conclusion": ("DoseNote", "?patient", "Apixaban", "ReduceDose")},

    # ∀patient, Chosen(patient, Apixaban), Has(patient, AgeAtLeast80), Has(patient, HighCreatinine)
    #   ➔ DoseNote(patient, Apixaban, ReduceDose)
    {"name": "D2 Dose note: age and creatinine",
     "conditions": [("Chosen", "?patient", "Apixaban"),
                    ("Has", "?patient", "AgeAtLeast80"),
                    ("Has", "?patient", "HighCreatinine")],
     "checks": [],
     "conclusion": ("DoseNote", "?patient", "Apixaban", "ReduceDose")},

    # ∀patient, Chosen(patient, Apixaban), Has(patient, LowWeight), Has(patient, HighCreatinine)
    #   ➔ DoseNote(patient, Apixaban, ReduceDose)
    {"name": "D3 Dose note: weight and creatinine",
     "conditions": [("Chosen", "?patient", "Apixaban"),
                    ("Has", "?patient", "LowWeight"),
                    ("Has", "?patient", "HighCreatinine")],
     "checks": [],
     "conclusion": ("DoseNote", "?patient", "Apixaban", "ReduceDose")},
]

# E. Verdict (1 rule)
VERDICT_RULES = [
    # ∀patient, drug, reason, Rejected(patient, drug, reason) ➔ InvalidRegimen(patient)
    {"name": "E1 Invalid regimen",
     "conditions": [("Rejected", "?patient", "?drug", "?reason")],
     "checks": [],
     "conclusion": ("InvalidRegimen", "?patient")},
]

# F. Current medications (4 rules): each newly chosen drug is checked against the drugs the patient
# already takes. The new drug is the one rejected or flagged, because the planner cannot change the
# medicines the patient already takes.
CURRENT_MEDICATION_RULES = [
    # ∀patient, current, chosen, severity, Taking(patient, current), Chosen(patient, chosen),
    #   Interacts(current, chosen, severity) ➔ CurrentConflict(patient, chosen, current, severity)
    {"name": "F1 Conflict with a current medication (stored as current, chosen)",
     "conditions": [("Taking", "?patient", "?current"),
                    ("Chosen", "?patient", "?chosen"),
                    ("Interacts", "?current", "?chosen", "?severity")],
     "checks": [],
     "conclusion": ("CurrentConflict", "?patient", "?chosen", "?current", "?severity")},

    # Each interaction pair is stored once, in one order, so this rule covers the other order.
    # ∀patient, current, chosen, severity, Taking(patient, current), Chosen(patient, chosen),
    #   Interacts(chosen, current, severity) ➔ CurrentConflict(patient, chosen, current, severity)
    {"name": "F2 Conflict with a current medication (stored as chosen, current)",
     "conditions": [("Taking", "?patient", "?current"),
                    ("Chosen", "?patient", "?chosen"),
                    ("Interacts", "?chosen", "?current", "?severity")],
     "checks": [],
     "conclusion": ("CurrentConflict", "?patient", "?chosen", "?current", "?severity")},

    # ∀patient, chosen, current, CurrentConflict(patient, chosen, current, Major)
    #   ➔ Rejected(patient, chosen, InteractionWithCurrent(current))
    {"name": "F3 Rejected for a Major interaction with a current medication",
     "conditions": [("CurrentConflict", "?patient", "?chosen", "?current", "Major")],
     "checks": [],
     "conclusion": ("Rejected", "?patient", "?chosen", ("InteractionWithCurrent", "?current"))},

    # ∀patient, chosen, current, CurrentConflict(patient, chosen, current, Moderate)
    #   ➔ Flagged(patient, chosen, InteractionWithCurrent(current))
    {"name": "F4 Flagged for a Moderate interaction with a current medication",
     "conditions": [("CurrentConflict", "?patient", "?chosen", "?current", "Moderate")],
     "checks": [],
     "conclusion": ("Flagged", "?patient", "?chosen", ("InteractionWithCurrent", "?current"))},
]

# G. Warnings about current medications (4 rules): the same "not suitable" checks as rules C1, C2, C4 and
# C6/C7, but for medicines the patient ALREADY takes.
# Current medications affect the plan in two ways:
#   - Group F (above): a NEW drug that interacts with a current medication is rejected or flagged, so
#     current medications DO change which options are safe and how they are ranked.
#   - Group G (here): a problem with a CURRENT medication itself gives a warning only. It does not reject
#     options or change the ranking (rule E only looks at Rejected facts), because the current medication
#     is the same in every option, so it cannot make one option better than another.
# Cautions about current medications themselves are not checked (SPEC section 12, decision 3).
CURRENT_WARNING_RULES = [
    # ∀patient, drug, Taking(patient, drug), Allergic(patient, drug) ➔ CurrentWarning(patient, drug, Allergy)
    {"name": "G1 Warning: allergic to a current medication",
     "conditions": [("Taking", "?patient", "?drug"),
                    ("Allergic", "?patient", "?drug")],
     "checks": [],
     "conclusion": ("CurrentWarning", "?patient", "?drug", "Allergy")},

    # ∀patient, drug, attribute, Taking(patient, drug), RejectIfHas(drug, attribute), Has(patient, attribute)
    #   ➔ CurrentWarning(patient, drug, attribute)
    {"name": "G2 Warning: a current medication is ruled out by an attribute",
     "conditions": [("Taking", "?patient", "?drug"),
                    ("RejectIfHas", "?drug", "?attribute"),
                    ("Has", "?patient", "?attribute")],
     "checks": [],
     "conclusion": ("CurrentWarning", "?patient", "?drug", "?attribute")},

    # ∀patient, drug, Taking(patient, drug), Pregnant(patient), RejectIfPregnant(drug)
    #   ➔ CurrentWarning(patient, drug, Pregnancy)
    {"name": "G3 Warning: a current medication is ruled out in pregnancy",
     "conditions": [("Taking", "?patient", "?drug"),
                    ("Pregnant", "?patient"),
                    ("RejectIfPregnant", "?drug")],
     "checks": [],
     "conclusion": ("CurrentWarning", "?patient", "?drug", "Pregnancy")},

    # ∀patient, first, second, Taking(patient, first), Taking(patient, second), Interacts(first, second, Major)
    #   ➔ CurrentWarning(patient, first, InteractionWith(second))
    {"name": "G4 Warning: two current medications have a Major interaction",
     "conditions": [("Taking", "?patient", "?first"),
                    ("Taking", "?patient", "?second"),
                    ("Interacts", "?first", "?second", "Major")],
     "checks": [],
     "conclusion": ("CurrentWarning", "?patient", "?first", ("InteractionWith", "?second"))},
]

# All 29 rules together, in the order of SPEC section 5.2.
ALL_RULES = (CANDIDATE_RULES + ATTRIBUTE_RULES + CHECK_RULES + DOSE_NOTE_RULES + VERDICT_RULES
             + CURRENT_MEDICATION_RULES + CURRENT_WARNING_RULES)


# ---------------------------------------------------------------------------
# The forward chainer
# ---------------------------------------------------------------------------

def is_variable(term):
    """A term is a variable if it is a word that starts with "?", like "?patient"."""
    return isinstance(term, str) and term.startswith("?")


def match_pattern(pattern, fact, bindings):
    """
    Try to line up one pattern with one fact. This is Universal Elimination (SUBST): each variable
    in the pattern is replaced by the constant in the same place in the fact.
    A variable that already has a value must agree with the fact.
    Returns the new bindings (a dict from variable to value), or None if they do not match.
    Example: ("EGFR", "?patient", "?score") with ("EGFR", "Patient3", 40)
             gives {"?patient": "Patient3", "?score": 40}.
    """
    if len(pattern) != len(fact):
        return None
    new_bindings = dict(bindings)
    for pattern_term, fact_term in zip(pattern, fact):
        if isinstance(pattern_term, tuple):
            # A small inner tuple, like ("InteractionWith", "?other"): match it the same way.
            if not isinstance(fact_term, tuple):
                return None
            new_bindings = match_pattern(pattern_term, fact_term, new_bindings)
            if new_bindings is None:
                return None
        elif is_variable(pattern_term):
            if pattern_term in new_bindings:
                if new_bindings[pattern_term] != fact_term:
                    return None
            else:
                new_bindings[pattern_term] = fact_term
        elif pattern_term != fact_term:
            return None
    return new_bindings


def group_by_predicate(known_facts):
    """
    Sort the facts into groups by predicate name, like tabs in a filing cabinet:
    {"EGFR": [("EGFR", "Patient3", 40)], "Treats": [...], ...}.
    A condition like ("EGFR", "?patient", "?score") can only match facts named "EGFR",
    so the chainer only needs to look in that one group. This makes it about 4 times faster.
    """
    facts_by_predicate = {}
    for fact in known_facts:
        add_to_predicate_group(facts_by_predicate, fact)
    return facts_by_predicate


def add_to_predicate_group(facts_by_predicate, fact):
    """Put one fact into the group for its predicate name (making the group if it is the first one)."""
    predicate = fact[0]
    if predicate not in facts_by_predicate:
        facts_by_predicate[predicate] = []
    facts_by_predicate[predicate].append(fact)


def find_all_matches(conditions, facts_by_predicate):
    """
    Find every set of bindings that makes ALL the conditions match known facts at the same time.
    This is And-Introduction: the conditions are joined, one at a time, keeping only the bindings
    that still agree. Returns a list of bindings (it is empty if there is no match).
    Each condition is only compared with the facts that have the same predicate name.
    """
    partial_matches = [{}]
    for condition in conditions:
        next_matches = []
        same_name_facts = facts_by_predicate.get(condition[0], [])
        for bindings in partial_matches:
            for fact in same_name_facts:
                new_bindings = match_pattern(condition, fact, bindings)
                if new_bindings is not None:
                    next_matches.append(new_bindings)
        partial_matches = next_matches
    return partial_matches


def compare(left, operator, right):
    """Do one number comparison, for example compare(40, "<", 45) is True."""
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">=":
        return left >= right
    raise ValueError(f"Unknown comparison operator: {operator}")


def passes_checks(checks, bindings):
    """Replace the variables in each check with their values and test it. All checks must pass."""
    for variable, operator, limit in checks:
        if not compare(bindings[variable], operator, limit):
            return False
    return True


def substitute(pattern, bindings):
    """
    Build a new fact from a pattern by replacing every variable with its value.
    A term can itself be a small tuple, like ("InteractionWith", "?second") in rules C7 and C8.
    Then the same function is used on that small tuple, so its variable is replaced too.
    A variable that has no value yet is left as it is (the backward chainer needs this; in the
    forward chainer every variable always has a value by this point).
    """
    new_fact = []
    for term in pattern:
        if isinstance(term, tuple):
            new_fact.append(substitute(term, bindings))
        elif is_variable(term) and term in bindings:
            new_fact.append(bindings[term])
        else:
            new_fact.append(term)
    return tuple(new_fact)


def forward_chain(starting_facts, rules):
    """
    The forward chainer. Starts from a copy of the given facts and repeats passes over all rules.
    For each rule, every way its conditions all match (And-Introduction) that also passes its checks
    gives a conclusion, which is added as a new fact (Implication-Elimination).
    Stops when a full pass adds no new fact. Returns the full set of facts.
    The starting facts are copied, never changed, and nothing is ever deleted.
    """
    known_facts = set(starting_facts)
    facts_by_predicate = group_by_predicate(known_facts)
    while True:
        added_this_pass = False
        for rule in rules:
            for bindings in find_all_matches(rule["conditions"], facts_by_predicate):
                if passes_checks(rule["checks"], bindings):
                    new_fact = substitute(rule["conclusion"], bindings)
                    if new_fact not in known_facts:
                        known_facts.add(new_fact)
                        add_to_predicate_group(facts_by_predicate, new_fact)
                        added_this_pass = True
        if not added_this_pass:
            return known_facts


# ---------------------------------------------------------------------------
# Trying a regimen
# ---------------------------------------------------------------------------

def chain_regimen(patient, regimen):
    """
    Try a regimen (a list of drug names, complete or partial) for this patient.
    Builds a FRESH fact set every time: the static facts, the patient's facts, and one
    Chosen(patient, drug) fact for each drug. Then runs the forward chainer with all the rules.
    Nothing shared is changed, so there is never anything to undo.
    """
    starting_facts = static_facts() | patient_facts(patient)
    for drug in regimen:
        starting_facts.add(("Chosen", patient["name"], drug))
    return forward_chain(starting_facts, ALL_RULES)


def facts_named(known_facts, predicate):
    """Return the facts whose predicate (first item) is the given name, for example all "Rejected" facts."""
    found = set()
    for fact in known_facts:
        if fact[0] == predicate:
            found.add(fact)
    return found


# ---------------------------------------------------------------------------
# The backward chainer (used to answer "why?")
# ---------------------------------------------------------------------------
# Forward chaining starts from the facts and adds every conclusion it can.
# Backward chaining starts from ONE goal, for example Rejected(Patient3, Metformin, ?reason):
#   1. it looks for stored facts that match the goal;
#   2. it finds each rule whose conclusion matches the goal;
#   3. it makes that rule's conditions into sub-goals and proves them the same way, one at a time.
# It writes down every step, so the program can show which sub-goals succeed and which fail.
# It only uses stored facts (the KB tables, the patient's facts and the Chosen facts), never the
# forward chainer's results, so it is a separate way of reaching the same answers.

def show_term(term):
    """Write one term for people: "?score" becomes "score", ("InteractionWith", "Ibuprofen") becomes
    "InteractionWith(Ibuprofen)"."""
    if isinstance(term, tuple):
        return show_pattern(term)
    if is_variable(term):
        return term[1:]
    return str(term)


def show_pattern(pattern):
    """Write a fact or goal in the course's notation, for example "EGFR(Patient3, 40)"."""
    terms = []
    for term in pattern[1:]:
        terms.append(show_term(term))
    return pattern[0] + "(" + ", ".join(terms) + ")"


def match_conclusion(conclusion, goal, rule_bindings):
    """
    Line up a rule's conclusion with a goal: can this rule conclude this goal?
    The goal's own variables (like "?reason") are left open, because they are what we want to find.
    Returns the rule's bindings, or None if the rule cannot conclude the goal.
    Example: the conclusion ("Rejected", "?patient", "?drug", "?attribute") with the goal
             ("Rejected", "Patient3", "Metformin", "?reason") gives {"?patient": "Patient3", "?drug": "Metformin"}.
    """
    if len(conclusion) != len(goal):
        return None
    new_bindings = dict(rule_bindings)
    for rule_term, goal_term in zip(conclusion, goal):
        if is_variable(goal_term):
            continue
        if isinstance(rule_term, tuple):
            if not isinstance(goal_term, tuple):
                return None
            new_bindings = match_conclusion(rule_term, goal_term, new_bindings)
            if new_bindings is None:
                return None
        elif is_variable(rule_term):
            if rule_term in new_bindings and new_bindings[rule_term] != goal_term:
                return None
            new_bindings[rule_term] = goal_term
        elif rule_term != goal_term:
            return None
    return new_bindings


def show_answer(answer):
    """Write the values found for open variables, for example "attribute = ModerateKidneyImpairment"."""
    parts = []
    for variable, value in answer.items():
        parts.append(f"{show_term(variable)} = {show_term(value)}")
    return ", ".join(parts)


def prove(goal, known_facts, rules, depth, lines):
    """
    Backward chaining: find every way the goal can be true.
    Returns a list of answers. Each answer is a dict with values for the goal's open variables
    (an empty dict means "true, and there was nothing to find"). An empty list means the goal FAILS.
    Each step is written into `lines` as (depth, text), where depth is how far to indent it.
    """
    answers = []
    for fact in known_facts:
        answer = match_pattern(goal, fact, {})
        if answer is not None:
            answers.append(answer)
    for rule in rules:
        answers = answers + prove_with_rule(goal, rule, known_facts, rules, depth, lines)
    return answers


def prove_with_rule(goal, rule, known_facts, rules, depth, lines):
    """
    Try to prove the goal with one rule. If the rule's conclusion matches the goal, its conditions
    become sub-goals. Returns the answers for the goal's open variables (empty if the rule fails).
    """
    rule_bindings = match_conclusion(rule["conclusion"], goal, {})
    if rule_bindings is None:
        return []
    lines.append((depth, f"Try rule {rule['name']}"))
    answers = []
    for complete_bindings in prove_conditions(rule, 0, rule_bindings, known_facts, rules, depth + 1, lines):
        # Implication-Elimination: the conditions hold, so the conclusion holds. Read off the goal's values.
        conclusion = substitute(rule["conclusion"], complete_bindings)
        answers.append(match_pattern(goal, conclusion, {}))
    return answers


def prove_conditions(rule, position, bindings, known_facts, rules, depth, lines):
    """
    Prove the rule's conditions as sub-goals, one at a time, starting at `position`.
    This is And-Introduction done backward: every condition must succeed with the same bindings.
    If a sub-goal has several answers (for example the KB has three RejectIfHas facts for the drug),
    each answer is tried in turn. Returns every set of bindings that makes all conditions and checks true.
    """
    conditions = rule["conditions"]
    if position == len(conditions):
        return check_numbers(rule, bindings, depth, lines)

    sub_goal = substitute(conditions[position], bindings)
    sub_goal_lines = []
    answers = prove(sub_goal, known_facts, rules, depth + 1, sub_goal_lines)

    if len(answers) == 0:
        if len(sub_goal_lines) == 0:
            lines.append((depth, f"Sub-goal {show_pattern(sub_goal)}   FAILS (no such fact, and no rule concludes it)"))
        else:
            lines.append((depth, f"Sub-goal {show_pattern(sub_goal)}   FAILS"))
        lines.extend(sub_goal_lines)
        return []

    if len(answers) == 1:
        found = show_answer(answers[0])
        if found:
            lines.append((depth, f"Sub-goal {show_pattern(sub_goal)}   true ({found})"))
        else:
            lines.append((depth, f"Sub-goal {show_pattern(sub_goal)}   true"))
        lines.extend(sub_goal_lines)
        next_bindings = dict(bindings)
        next_bindings.update(answers[0])
        return prove_conditions(rule, position + 1, next_bindings, known_facts, rules, depth, lines)

    lines.append((depth, f"Sub-goal {show_pattern(sub_goal)}   {len(answers)} answers, so try each"))
    lines.extend(sub_goal_lines)
    results = []
    for answer in answers:
        lines.append((depth + 1, show_answer(answer)))
        next_bindings = dict(bindings)
        next_bindings.update(answer)
        results = results + prove_conditions(rule, position + 1, next_bindings,
                                             known_facts, rules, depth + 2, lines)
    return results


def check_numbers(rule, bindings, depth, lines):
    """Test the rule's number checks (like score < 30) and write each result down."""
    for variable, operator, limit in rule["checks"]:
        value = bindings[variable]
        if compare(value, operator, limit):
            lines.append((depth, f"Check {show_term(variable)} {operator} {limit}: {value} {operator} {limit}   true"))
        else:
            lines.append((depth, f"Check {show_term(variable)} {operator} {limit}: {value} {operator} {limit}   FAILS"))
            return []
    return [bindings]
