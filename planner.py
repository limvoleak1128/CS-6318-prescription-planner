"""
The Prescription Planner: the main entry points.

  plan(patient)               checks the patient, runs the search, and ranks the options
  why(patient, drug, ...)     explains, by backward chaining, why a drug is rejected or flagged (the trace
                              in the KB's notation, SPEC section 8)
  explain(patient, drug, ...) the same answer in one plain sentence
  patient_report(patient)     the report shown by run_demo.py and enter_patient.py (SPEC section 12, decision 20)
  steps_report(patient)       how the planner searched and how it explains each drug that is not suitable

The report uses plain words for the reader; the "why" trace uses the KB's names, because it shows how the
inference works (step by step, for presenting the method).
This is a course project, not a clinical tool.
"""
import textwrap

import kb
import kb_facts as facts
import search


# ---------------------------------------------------------------------------
# plan(patient)
# ---------------------------------------------------------------------------

def already_treated(patient):
    """
    The needed conditions that a medicine the patient already takes treats, as a dict:
    condition -> the medicines already taken for it. For example {"Type2Diabetes": ["Metformin"]}.
    """
    treated = {}
    for condition in patient["needs"]:
        for drug in patient.get("current_medications", []):
            if drug in facts.CONDITIONS[condition]:
                if condition not in treated:
                    treated[condition] = []
                treated[condition].append(drug)
    return treated


def plan(patient):
    """
    Make a plan for one patient. Returns a dict.
    - If an input check fails (age, unknown medicine), the dict has only "message", and no search is run.
    - Otherwise "message" is None and the dict has the search results (see search.search_and_rank).
    - "already_treated": needed conditions that a medicine already taken treats. They are not planned,
      because the KB has no facts about two drugs for the same condition (SPEC section 12, decision 2).
      "planned_needs" is the list of conditions that were planned. If it is empty, "nothing_to_plan" is True
      and there are no search results.
    - "other_conditions" is filled only when there is no complete regimen but some conditions are
      blocked (SPEC section 12, Idea A): it is the plan for the conditions that are not blocked.
    """
    message = kb.input_problem(patient)
    if message is not None:
        return {"message": message}

    treated = already_treated(patient)
    planned_needs = []
    for condition in patient["needs"]:
        if condition not in treated:
            planned_needs.append(condition)
    if len(planned_needs) == 0:
        return {"message": None, "already_treated": treated, "planned_needs": [], "nothing_to_plan": True}

    patient_to_plan = dict(patient, needs=planned_needs)
    result = search.search_and_rank(patient_to_plan)
    result["message"] = None
    result["already_treated"] = treated
    result["planned_needs"] = planned_needs
    result["nothing_to_plan"] = False
    result["other_conditions"] = None

    if len(result["ranked"]) == 0 and len(result["blocked_conditions"]) > 0:
        other_needs = []
        for condition in planned_needs:
            if condition not in result["blocked_conditions"]:
                other_needs.append(condition)
        if len(other_needs) > 0:
            patient_without_blocked = dict(patient, needs=other_needs)
            result["other_conditions"] = search.search_and_rank(patient_without_blocked)
    return result


# ---------------------------------------------------------------------------
# why(patient, drug): backward chaining
# ---------------------------------------------------------------------------

# The attributes that come from the patient's age. Age only ever flags (SPEC section 11, assumption 8).
AGE_ATTRIBUTES = ["Elderly", "AgeAtLeast80"]


def rule_named(code):
    """Find a rule by the code at the start of its name, for example rule_named("C2")."""
    for rule in kb.ALL_RULES:
        if rule["name"].split(" ")[0] == code:
            return rule
    raise KeyError(code)


def restriction_of(reason):
    """Which of the five restrictions a reason belongs to."""
    if reason == "Allergy":
        return "Allergy"
    if reason == "Pregnancy":
        return "Pregnancy"
    if isinstance(reason, tuple):
        return "Drug-drug"
    if reason in AGE_ATTRIBUTES:
        return "Age"
    return "Drug-condition"


def why_goals(patient_name, drug):
    """
    The goals to explain, grouped into sections. Each goal is tried with the rules listed for it.
    "?reason" and "?other" are open variables: the backward chainer finds their values.
    """
    rejected_goal = ("Rejected", patient_name, drug, "?reason")
    flagged_goal = ("Flagged", patient_name, drug, "?reason")
    other_rejected_goal = ("Rejected", patient_name, "?other", ("InteractionWith", drug))
    other_flagged_goal = ("Flagged", patient_name, "?other", ("InteractionWith", drug))
    dose_goal = ("DoseNote", patient_name, drug, "?note")
    warning_goal = ("CurrentWarning", patient_name, drug, "?reason")
    return [
        ("Allergy (rule C1)", [(rejected_goal, ["C1"])]),
        ("Pregnancy (rules C4, C5)", [(rejected_goal, ["C4"]), (flagged_goal, ["C5"])]),
        ("Drug-condition and age (rules C2, C3)", [(rejected_goal, ["C2"]), (flagged_goal, ["C3"])]),
        ("Drug-drug, with chosen and already-taken drugs (rules C7, C8, F3, F4)",
         [(rejected_goal, ["C7", "F3"]), (flagged_goal, ["C8", "F4"]),
          (other_rejected_goal, ["C7"]), (other_flagged_goal, ["C8"])]),
        ("Dose note (rules D1, D2, D3)", [(dose_goal, ["D1", "D2", "D3"])]),
        ("Warning about a medicine already taken (rules G1, G2, G3, G4)",
         [(warning_goal, ["G1", "G2", "G3", "G4"])]),
    ]


def stored_facts_for_why(patient, drug, regimen):
    """
    The facts the backward chainer may use: stored facts only (the KB tables, the patient's facts, and the
    Chosen facts), never the forward chainer's results. They are kept in a list in a fixed order, so the
    explanation always tries them in the same order. A medicine the patient already takes is not "chosen":
    it is explained with the warning rules (group G).
    Returns the facts and the other chosen drugs.
    """
    name = patient["name"]
    known_facts = kb.static_fact_list() + sorted(kb.patient_facts(patient), key=kb.show_pattern)
    if drug not in patient.get("current_medications", []):
        known_facts.append(("Chosen", name, drug))
    other_drugs = []
    if regimen is not None:
        for other_drug in regimen:
            if other_drug != drug:
                other_drugs.append(other_drug)
                known_facts.append(("Chosen", name, other_drug))
    return known_facts, other_drugs


def why(patient, drug, regimen=None, full=False):
    """
    Explain, by backward chaining, why this drug is rejected or flagged for this patient.
    regimen  the other drugs chosen with it (needed for the drug-drug checks); None means none.
    full     False (the default) shows the steps only for goals that SUCCEED, so it stays short.
             True shows every step, including the goals that fail (useful to show how backward
             chaining works). The answers are the same either way.
    For each goal, like Rejected(Patient3, Metformin, ?reason), the backward chainer finds the rules
    that conclude it and proves their conditions as sub-goals, writing down which succeed or fail.
    Returns a dict with the answers and "text", the explanation.
    """
    message = kb.input_problem(patient)
    if message is not None:
        return {"message": message, "text": message}

    name = patient["name"]
    current_medications = patient.get("current_medications", [])
    known_facts, other_drugs = stored_facts_for_why(patient, drug, regimen)

    lines = [(0, f"Why: {drug} for {name}")]
    if drug in current_medications:
        lines.append((0, f"{drug} is a medicine the patient already takes (not a chosen one)."))
    if len(other_drugs) > 0:
        lines.append((0, "Chosen with: " + ", ".join(other_drugs)))
    else:
        lines.append((0, "Chosen with: no other drugs"))
    if len(current_medications) > 0:
        lines.append((0, "Already takes: " + ", ".join(current_medications)))

    rejected_reasons = []
    flagged_reasons = []
    others_rejected = []
    others_flagged = []
    warning_reasons = []
    dose_note = False

    for section_title, goals in why_goals(name, drug):
        lines.append((0, ""))
        lines.append((0, section_title))
        for goal, rule_codes in goals:
            goal_lines = []
            answers = []
            for code in rule_codes:
                answers = answers + kb.prove_with_rule(goal, rule_named(code), known_facts,
                                                       kb.ALL_RULES, 2, goal_lines)
            if len(goal_lines) == 0:
                # No listed rule can conclude this goal, for example a dose note for a drug other than Apixaban.
                lines.append((1, f"Goal: {kb.show_pattern(goal)}   no rule concludes this for {drug}"))
                continue
            if len(answers) == 0:
                lines.append((1, f"Goal: {kb.show_pattern(goal)}   FAILS"))
                if full:
                    lines.extend(goal_lines)
            else:
                found = []
                for answer in answers:
                    found.append(kb.show_answer(answer))
                lines.append((1, f"Goal: {kb.show_pattern(goal)}   SUCCEEDS ({'; '.join(found)})"))
                lines.extend(goal_lines)
            for answer in answers:
                if goal[0] == "Rejected" and "?reason" in answer:
                    rejected_reasons.append(answer["?reason"])
                elif goal[0] == "Flagged" and "?reason" in answer:
                    flagged_reasons.append(answer["?reason"])
                elif goal[0] == "Rejected" and "?other" in answer:
                    others_rejected.append(answer["?other"])
                elif goal[0] == "Flagged" and "?other" in answer:
                    others_flagged.append(answer["?other"])
                elif goal[0] == "DoseNote":
                    dose_note = True
                elif goal[0] == "CurrentWarning":
                    warning_reasons.append(answer["?reason"])

    lines.append((0, ""))
    lines.extend(why_summary(drug, rejected_reasons, flagged_reasons, others_rejected, others_flagged,
                             dose_note, warning_reasons))

    text_lines = []
    for depth, text in lines:
        text_lines.append("  " * depth + text)
    return {
        "message": None,
        "rejected_reasons": rejected_reasons,
        "flagged_reasons": flagged_reasons,
        "others_rejected": others_rejected,
        "others_flagged": others_flagged,
        "dose_note": dose_note,
        "warning_reasons": warning_reasons,
        "text": "\n".join(text_lines),
    }


def why_summary(drug, rejected_reasons, flagged_reasons, others_rejected, others_flagged, dose_note,
                warning_reasons):
    """The answer, listed under the five restrictions, the dose note, and any warning about a medicine already taken."""
    found = {"Allergy": [], "Pregnancy": [], "Drug-condition": [], "Age": [], "Drug-drug": []}
    for reason in rejected_reasons:
        found[restriction_of(reason)].append("rejected: " + kb.show_term(reason))
    for reason in flagged_reasons:
        found[restriction_of(reason)].append("flagged: " + kb.show_term(reason))
    for other_drug in others_rejected:
        found["Drug-drug"].append(f"{other_drug} is rejected because of InteractionWith({drug})")
    for other_drug in others_flagged:
        found["Drug-drug"].append(f"{other_drug} is flagged because of InteractionWith({drug})")

    lines = [(0, f"Answer for {drug}")]
    for restriction in ["Allergy", "Pregnancy", "Drug-condition", "Age", "Drug-drug"]:
        if len(found[restriction]) == 0:
            lines.append((1, f"{restriction:<16}nothing found"))
        else:
            lines.append((1, f"{restriction:<16}" + "; ".join(found[restriction])))
    if dose_note:
        lines.append((1, f"{'Dose note':<16}ReduceDose (a lower dose may be needed)"))
    else:
        lines.append((1, f"{'Dose note':<16}nothing found"))
    if len(warning_reasons) > 0:
        shown = []
        for reason in warning_reasons:
            shown.append(kb.show_term(reason))
        lines.append((1, f"{'Warning':<16}already taken, not suitable: " + "; ".join(shown)))
    return lines


# ---------------------------------------------------------------------------
# Plain words for the reader
# ---------------------------------------------------------------------------

# How each needed condition is named in the printout.
CONDITION_WORDS = {
    "Hypertension": "Blood pressure",
    "HighCholesterol": "Cholesterol",
    "AtrialFibrillation": "Heart rhythm",
    "Type2Diabetes": "Diabetes",
    "ChronicPain": "Pain",
}

# How each typed yes/no attribute is described. These only restate the attribute's name.
TYPED_ATTRIBUTE_WORDS = {
    "AngioedemaHistory": "history of angioedema (serious swelling)",
    "RenalArteryStenosis": "narrowed kidney artery (renal artery stenosis)",
    "ChronicKidneyDisease": "chronic kidney disease",
    "HeartFailure": "heart failure",
    "SevereHypotension": "severe low blood pressure",
    "HighGradeAorticStenosis": "tight heart valve (high-grade aortic stenosis)",
    "ActiveBleeding": "active bleeding",
    "BleedingTendency": "bleeding tendency",
    "Hyperkalemia": "high potassium (hyperkalemia)",
    "ModerateLiverImpairment": "moderate liver impairment",
    "SevereLiverImpairment": "severe liver impairment",
}

# Separator lines. While a printout is being built, THICK_LINE and THIN_LINE mark where a line of "=" or "-"
# goes. When all the text is ready, draw_separators() replaces them with lines as long as the longest line of
# text (never shorter than SEPARATOR_WIDTH), so the separators always cover the whole printout.
SEPARATOR_WIDTH = 66
THICK_LINE = "<thick separator line>"
THIN_LINE = "<thin separator line>"


def draw_separators(lines):
    """Replace the THICK_LINE and THIN_LINE markers with "=" and "-" lines as long as the longest line of text."""
    width = SEPARATOR_WIDTH
    for line in lines:
        if line != THICK_LINE and line != THIN_LINE:
            width = max(width, len(line))
    drawn = []
    for line in lines:
        if line == THICK_LINE:
            drawn.append("=" * width)
        elif line == THIN_LINE:
            drawn.append("-" * width)
        else:
            drawn.append(line)
    return drawn


def describe_reason(reason, patient):
    """Describe a reason in plain words, using the patient's own numbers where they matter."""
    if reason == "Allergy":
        return "allergy"
    if reason == "Pregnancy":
        return "pregnancy"
    if isinstance(reason, tuple):
        return "serious drug interaction with " + other_drug_words(reason)
    if reason == "Elderly":
        return f"age {facts.ELDERLY_AGE_YEARS} or older ({patient.get('age')})"
    if reason == "AgeAtLeast80":
        return f"age {facts.VERY_OLD_AGE_YEARS} or older ({patient.get('age')})"
    if reason == "SevereKidneyImpairment":
        return f"severely reduced kidney function (eGFR {patient.get('egfr')})"
    if reason == "ModerateKidneyImpairment":
        return f"reduced kidney function (eGFR {patient.get('egfr')})"
    if reason == "LowWeight":
        return f"weight {facts.LOW_WEIGHT_KG_AT_MOST} kg or less ({patient.get('weight')} kg)"
    if reason == "HighCreatinine":
        return f"creatinine {facts.HIGH_CREATININE_AT_LEAST} or higher ({patient.get('creatinine')})"
    if reason == "ActiveLiverDisease":
        # Assumption 1: moderate or severe liver impairment counts as active liver disease.
        # The reader sees the liver impairment the patient actually has, so it reads the same as
        # restrictions that name the liver impairment directly, and they are grouped together.
        grades = []
        for attribute in ["ModerateLiverImpairment", "SevereLiverImpairment"]:
            if attribute in patient.get("has", []):
                grades.append(TYPED_ATTRIBUTE_WORDS[attribute])
        return join_words(grades)
    return TYPED_ATTRIBUTE_WORDS[reason]


def other_drug_words(reason):
    """
    The other drug in an interaction reason. A reason ("InteractionWithCurrent", "Warfarin") is about a
    medicine the patient already takes, so it says "already-taken Warfarin".
    """
    if reason[0] == "InteractionWithCurrent":
        return "already-taken " + reason[1]
    return reason[1]


def pair_name(drug, reason):
    """A drug pair for the printout, for example "Apixaban + Ibuprofen" or "Ibuprofen + already-taken Warfarin"."""
    return f"{drug} + {other_drug_words(reason)}"


def unusual_value_notes(patient):
    """
    A note for each value that was accepted but is unusual, so it may be a typing mistake
    (SPEC section 12, decisions 17 and 24). For example
    "Note: a weight of 22 kg is unusually low (below 35). Please check it is not a typing mistake."
    """
    notes = []
    age = patient.get("age")
    if age is not None and age > kb.AGE_UNUSUALLY_HIGH:
        notes.append(f"Note: an age of {age} is unusually high (above {kb.AGE_UNUSUALLY_HIGH}). "
                     "Please check it is not a typing mistake.")
    egfr = patient.get("egfr")
    if egfr is not None and egfr > kb.EGFR_UNUSUALLY_HIGH:
        notes.append(f"Note: an eGFR of {egfr} is unusually high (above {kb.EGFR_UNUSUALLY_HIGH}). "
                     "Please check it is not a typing mistake.")
    for noun, unit, lowest, highest in [("weight", " kg", kb.WEIGHT_UNUSUALLY_LOW, kb.WEIGHT_UNUSUALLY_HIGH),
                                        ("creatinine", "", kb.CREATININE_UNUSUALLY_LOW, kb.CREATININE_UNUSUALLY_HIGH)]:
        value = patient.get(noun)
        if value is None:
            continue
        if value < lowest:
            notes.append(f"Note: a {noun} of {value}{unit} is unusually low (below {lowest}). "
                         "Please check it is not a typing mistake.")
        elif value > highest:
            notes.append(f"Note: a {noun} of {value}{unit} is unusually high (above {highest}). "
                         "Please check it is not a typing mistake.")
    return notes


def describe_patient(patient):
    """One line with the patient's numbers and recorded items, for example
    "Age 58, weight 80 kg, eGFR 40, creatinine 1.9, not pregnant"."""
    parts = [f"Age {patient.get('age')}"]
    if patient.get("weight") is None:
        parts.append("weight not recorded")
    else:
        parts.append(f"weight {patient['weight']} kg")
    if patient.get("egfr") is None:
        parts.append("eGFR not recorded")
    else:
        parts.append(f"eGFR {patient['egfr']}")
    if patient.get("creatinine") is None:
        parts.append("creatinine not recorded")
    else:
        parts.append(f"creatinine {patient['creatinine']}")
    if patient.get("pregnant", False):
        parts.append("pregnant")
    else:
        parts.append("not pregnant")
    for attribute in patient.get("has", []):
        parts.append(TYPED_ATTRIBUTE_WORDS[attribute])
    for drug in patient.get("allergies", []):
        parts.append("allergic to " + drug)
    return ", ".join(parts)


def count_words(number, word):
    """For example count_words(1, "caution") is "1 caution" and count_words(2, "caution") is "2 cautions"."""
    if number == 1:
        return f"1 {word}"
    return f"{number} {word}s"


def join_words(words):
    """Join words in plain English: ["A"] gives "A", ["A", "B"] gives "A and B", ["A", "B", "C"] gives "A, B and C"."""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def table_lines(rows):
    """Line up rows of text in columns. Each row is a list of strings; the last column is not padded."""
    widths = []
    for column in range(len(rows[0]) - 1):
        widest = 0
        for row in rows:
            widest = max(widest, len(row[column]))
        widths.append(widest + 2)
    lines = []
    for row in rows:
        text = ""
        for column in range(len(row) - 1):
            text = text + row[column].ljust(widths[column])
        lines.append((text + row[-1]).rstrip())
    return lines


# ---------------------------------------------------------------------------
# Parts of the report: the dose check and the medicines already taken
# ---------------------------------------------------------------------------

# The three conditions of the Apixaban dose note: the attribute, the profile field, and its unit.
DOSE_NOTE_PARTS = [("AgeAtLeast80", "age", ""), ("LowWeight", "weight", " kg"), ("HighCreatinine", "creatinine", "")]


# How each dose-note condition is said when it still needs checking, and when it is already true.
DOSE_CONDITION_TO_CHECK = {
    "weight": f"the patient weighs {facts.LOW_WEIGHT_KG_AT_MOST} kg or less",
    "creatinine": f"the patient has creatinine {facts.HIGH_CREATININE_AT_LEAST} or higher",
}


def missing_number_sentence(patient, attributes, missing):
    """
    The reminder when weight or creatinine was not recorded (SPEC section 12, decision 14), for example:
    "Weight was not recorded. Please check it: a lower dose may be needed if the patient weighs 60 kg or less,
    because creatinine is already 1.5 or higher (1.9)."
    """
    if len(missing) == 1:
        opening = f"{missing[0].capitalize()} was not recorded. Please check it:"
    else:
        opening = f"{missing[0].capitalize()} and {missing[1]} were not recorded. Please check them:"

    already_true = []
    if "AgeAtLeast80" in attributes:
        already_true.append(f"the patient is already {facts.VERY_OLD_AGE_YEARS} or older (age {patient['age']})")
    if "LowWeight" in attributes:
        already_true.append(f"the patient already weighs {facts.LOW_WEIGHT_KG_AT_MOST} kg or less ({patient['weight']} kg)")
    if "HighCreatinine" in attributes:
        already_true.append(f"creatinine is already {facts.HIGH_CREATININE_AT_LEAST} or higher ({patient['creatinine']})")

    to_check = []
    for field in missing:
        to_check.append(DOSE_CONDITION_TO_CHECK[field])
    if len(to_check) == 2:
        # "the patient weighs 60 kg or less or has creatinine ...": say "the patient" only once.
        to_check[1] = to_check[1].replace("the patient ", "", 1)
    if len(already_true) == 1:
        # One condition is already true, so any one more makes two: join what to check with "or".
        return (f"{opening} a lower dose may be needed if {' or '.join(to_check)}, "
                f"because {already_true[0]}.")
    # None is true yet, so both missing ones would be needed: join them with "and".
    return f"{opening} a lower dose may be needed if {' and '.join(to_check)}."


def warning_words(reason, patient):
    """Why a medicine the patient already takes is not suitable, for example "pregnancy" or "active bleeding"."""
    if reason == "Pregnancy":
        return "pregnancy"
    if reason == "Allergy":
        return "allergy"
    if isinstance(reason, tuple):
        return f"serious drug interaction with {reason[1]} (also already taken)"
    return describe_reason(reason, patient)


def current_medication_lines(patient):
    """
    What the printout says about the medicines the patient already takes (SPEC section 12, decisions 2 and 3):
    the list, a WARNING for each one that is not suitable (from the group G rules), a note for each needed
    condition that is not planned because a medicine already taken treats it, and a note on what was and
    was not checked.
    """
    current_medications = patient.get("current_medications", [])
    if len(current_medications) == 0:
        return []
    lines = ["Already takes: " + ", ".join(current_medications)]

    # The warnings come from the forward chainer: chain the patient's facts with no drug chosen.
    patient_only_facts = kb.chain_regimen(patient, [])
    for fact in sorted(kb.facts_named(patient_only_facts, "CurrentWarning"), key=kb.show_pattern):
        drug = fact[2]
        lines.append("")
        lines.append(f"WARNING  {drug} (already taken) is not suitable for this patient: "
                     f"{warning_words(fact[3], patient)}.")
        lines.append("         A doctor should review it.")

    lines.append("")
    for condition, drugs in already_treated(patient).items():
        drug_words = join_words(drugs)
        lines.append(f"Note: {CONDITION_WORDS[condition]} is not planned, because the patient already takes "
                     f"{drug_words} for it.")
        lines.append(f"      To plan a replacement instead, enter the patient again without {drug_words} "
                     "in the medicines already taken.")
    lines.append("Note: medicines the patient already takes are checked for interactions with the new medicines and for")
    lines.append("serious problems only. Other cautions about them are not shown. A doctor should review them separately.")
    return lines


# ---------------------------------------------------------------------------
# The plain explanation, for the person running the program
# ---------------------------------------------------------------------------
# why() shows the backward chaining step by step, for presenting the method. explain() uses the SAME
# backward chainer (it calls why()), but writes only the answer and the reason, in one short line where
# possible (SPEC section 12, decision 18).

def short_reason(reason, patient):
    """
    A reason in a few plain words, with the patient's own number where it comes from one, for example
    "reduced kidney function (eGFR 40, between 30 and 44)" or "pregnancy".
    """
    if reason == "Allergy":
        return "allergy"
    if reason == "Pregnancy":
        return "pregnancy"
    if isinstance(reason, tuple):
        return f"serious drug interaction with {other_drug_words(reason)}"
    if reason == "SevereKidneyImpairment":
        return (f"severely reduced kidney function (eGFR {patient.get('egfr')}, "
                f"below {facts.SEVERE_KIDNEY_EGFR_BELOW})")
    if reason == "ModerateKidneyImpairment":
        return (f"reduced kidney function (eGFR {patient.get('egfr')}, between {facts.SEVERE_KIDNEY_EGFR_BELOW} "
                f"and {facts.MODERATE_KIDNEY_EGFR_BELOW - 1})")
    if reason == "Elderly":
        return f"the patient is {facts.ELDERLY_AGE_YEARS} or older (age {patient.get('age')})"
    if reason == "AgeAtLeast80":
        return f"the patient is {facts.VERY_OLD_AGE_YEARS} or older (age {patient.get('age')})"
    return describe_reason(reason, patient)


def reason_clause(reason, patient):
    """
    A caution's reason as part of a sentence, said like a person would, for example
    "the patient is 65 or older (age 82)" or "the patient has reduced kidney function (eGFR 40, between 30 and 44)".
    """
    if reason == "Pregnancy":
        return "the patient is pregnant"
    if isinstance(reason, tuple):
        return f"it can affect {other_drug_words(reason)}"
    if reason in ["Elderly", "AgeAtLeast80"]:
        return short_reason(reason, patient)
    return "the patient has " + short_reason(reason, patient)


def caution_words(reason, patient):
    """A caution in a few plain words. A drug interaction caution says the drugs can affect each other."""
    if isinstance(reason, tuple):
        return f"drug interaction with {other_drug_words(reason)} (they can affect each other)"
    return reason_clause(reason, patient)


def dose_sentence(patient):
    """Why Apixaban gets the dose note, as a sentence."""
    return "Check the dose: a lower dose may be needed, because the patient " + dose_reasons(patient) + "."


def dose_reasons(patient):
    """The dose-note conditions that are true, for example "is 80 or older (age 82) and weighs 60 kg or less (58 kg)"."""
    attributes = kb.attributes_of(kb.forward_chain(kb.patient_facts(patient), kb.ATTRIBUTE_RULES),
                                  patient["name"])
    reasons = []
    if "AgeAtLeast80" in attributes:
        reasons.append(f"is {facts.VERY_OLD_AGE_YEARS} or older (age {patient['age']})")
    if "LowWeight" in attributes:
        reasons.append(f"weighs {facts.LOW_WEIGHT_KG_AT_MOST} kg or less ({patient['weight']} kg)")
    if "HighCreatinine" in attributes:
        reasons.append(f"has creatinine {facts.HIGH_CREATININE_AT_LEAST} or higher ({patient['creatinine']})")
    return join_words(reasons)


def explain(patient, drug, regimen=None):
    """
    Explain one drug for the person running the program, in plain words (no rules or sub-goals):
    NOT SUITABLE with the reason, or CAN BE USED with any cautions and the dose note.
    regimen  the other drugs chosen with it; None means none.
    The answers come from why(), so this is still backward chaining; only the wording is different.
    """
    result = why(patient, drug, regimen)
    if result["message"] is not None:
        return result["message"]
    name = patient["name"]

    # A medicine the patient already takes: only the group G warnings apply to it.
    if drug in patient.get("current_medications", []):
        if len(result["warning_reasons"]) == 0:
            return (f"{drug} is a medicine the patient already takes. No serious problem was found with it.\n"
                    "  (Smaller cautions about medicines already taken are not checked.)")
        lines = [f"{drug} is a medicine the patient already takes."]
        for reason in result["warning_reasons"]:
            lines.append(f"  WARNING: it is not suitable for this patient: {warning_words(reason, patient)}.")
        lines.append("  A doctor should review it.")
        return "\n".join(wrap_lines(lines))

    # The rejections include the case where this drug makes another drug not suitable (a Major pair).
    problems = list(result["rejected_reasons"])
    for other_drug in result["others_rejected"]:
        problems.append(("InteractionWith", other_drug))
    cautions = list(result["flagged_reasons"])
    for other_drug in result["others_flagged"]:
        cautions.append(("InteractionWith", other_drug))

    lines = []
    if len(problems) > 0:
        # Not suitable: only the reason matters, so cautions are not listed.
        only_interactions = True
        for reason in problems:
            if not isinstance(reason, tuple):
                only_interactions = False
        if only_interactions:
            partners = []
            for reason in problems:
                partners.append(other_drug_words(reason))
            lines.append(f"{drug} is NOT SUITABLE together with {join_words(partners)}: "
                         "serious drug interaction, they must not be taken together.")
        else:
            reason_words = []
            for reason in problems:
                reason_words.append(short_reason(reason, patient))
            lines.append(f"{drug} is NOT SUITABLE for {name}: {'; '.join(reason_words)}.")
        return "\n".join(wrap_lines(lines))

    if len(cautions) == 0:
        lines.append(f"{drug} CAN BE USED for {name}. No problems were found.")
    elif len(cautions) == 1:
        lines.append(f"{drug} CAN BE USED for {name}, with 1 caution: {caution_words(cautions[0], patient)}. "
                     "Use with care.")
    else:
        lines.append(f"{drug} CAN BE USED for {name}, with {len(cautions)} cautions. Use with care:")
        for reason in cautions:
            lines.append("  - " + caution_words(reason, patient))
    if result["dose_note"]:
        lines.append("  " + dose_sentence(patient))
    return "\n".join(wrap_lines(lines))


# The longest an explanation line may be before it continues on the next line.
EXPLAIN_WIDTH = 100


def wrap_lines(lines):
    """
    Wrap lines longer than EXPLAIN_WIDTH. A continued line is indented by two more spaces than its first
    line (four for a "- " item), so it is easy to see where each line starts.
    """
    wrapped = []
    for line in lines:
        indent = line[:len(line) - len(line.lstrip())]
        more_indent = indent + "  "
        if line.lstrip().startswith("- "):
            more_indent = indent + "    "
        if len(line) <= EXPLAIN_WIDTH:
            wrapped.append(line)
        else:
            wrapped.extend(textwrap.wrap(line.strip(), width=EXPLAIN_WIDTH,
                                         initial_indent=indent, subsequent_indent=more_indent))
    return wrapped


def wrap_row(label, text):
    """
    Write a row as label + text. If it is too long, the text continues on the next lines, lined up under
    where the text started (not under the label).
    """
    return textwrap.wrap(text, width=EXPLAIN_WIDTH, initial_indent=label,
                         subsequent_indent=" " * len(label))


# ---------------------------------------------------------------------------
# Why the recommended option (forward chaining: comparing the options)
# ---------------------------------------------------------------------------

def concerns_about(drug, regimen_facts, patient):
    """The cautions in a regimen that are about this drug (its own cautions, and its drug interactions)."""
    words = []
    affected = []
    for fact in sorted(kb.facts_named(regimen_facts, "Flagged"), key=kb.show_pattern):
        flagged_drug = fact[2]
        reason = fact[3]
        if flagged_drug == drug and isinstance(reason, tuple):
            affected.append(other_drug_words(reason))
        elif flagged_drug == drug:
            words.append(reason_clause(reason, patient))
        elif isinstance(reason, tuple) and reason[1] == drug:
            affected.append(flagged_drug)
    if len(affected) > 0:
        words.append("it can affect " + join_words(affected))
    return words


def problems_about(drug, regimen_facts, patient):
    """The reasons in a regimen that make this drug not suitable (including a Major pair it is part of)."""
    words = []
    for fact in sorted(kb.facts_named(regimen_facts, "Rejected"), key=kb.show_pattern):
        rejected_drug = fact[2]
        reason = fact[3]
        if rejected_drug == drug and isinstance(reason, tuple):
            words.append(f"serious drug interaction with {other_drug_words(reason)}")
        elif rejected_drug == drug:
            words.append(short_reason(reason, patient))
        elif isinstance(reason, tuple) and reason[1] == drug:
            words.append(f"serious drug interaction with {rejected_drug}")
    return words


def why_this_option_lines(patient, result):
    """
    For the recommended option, one line per condition: why its drug was picked over the other candidate.
    For each condition, the other candidate is swapped in, and the forward chainer judges that regimen:
    either the other drug is not suitable, or it brings more concerns, or it is just as good (a tie).
    """
    best = result["ranked"][0]
    best_regimen = best[0]
    best_score = (best[1], best[2], best[3])
    lines = [f"Why this is the best option ({' + '.join(best_regimen)}):"]
    label_width = 0
    for condition in patient["needs"]:
        label_width = max(label_width, len(CONDITION_WORDS[condition]) + 1)
    for position, condition in enumerate(patient["needs"]):
        chosen = best_regimen[position]
        for other in facts.CONDITIONS[condition]:
            if other == chosen:
                continue
            swapped = list(best_regimen)
            swapped[position] = other
            swapped_facts = kb.chain_regimen(patient, swapped)
            if ("InvalidRegimen", patient["name"]) in swapped_facts:
                reason = f"{other} is not suitable: {'; '.join(problems_about(other, swapped_facts, patient))}"
            elif search.score_regimen(patient, tuple(swapped)) == best_score:
                reason = f"{other} is just as good (a tie; both are listed in the table)"
            else:
                concerns = concerns_about(other, swapped_facts, patient)
                chosen_concerns = concerns_about(chosen, kb.chain_regimen(patient, list(best_regimen)), patient)
                if len(concerns) > 0:
                    reason = f"{other} has more concerns: {'; '.join(concerns)}"
                else:
                    reason = f"{other} has more concerns overall"
                if len(chosen_concerns) > 0:
                    reason = reason + f". {chosen} has fewer: {'; '.join(chosen_concerns)}"
            label = "  " + (CONDITION_WORDS[condition] + ":").ljust(label_width) + "  "
            lines.extend(wrap_row(label, f"{chosen}, because {reason}."))
    return lines


# ---------------------------------------------------------------------------
# How the search went (depth-first search, with forward chaining at each step)
# ---------------------------------------------------------------------------

def search_steps_lines(patient, result):
    """
    Every step of the depth-first search in order, in plain words: which drug was tried for which condition,
    and what the forward chainer said about the drugs chosen so far.
    """
    needs = patient["needs"]
    condition_words = []
    for condition in needs:
        condition_words.append(CONDITION_WORDS[condition])
    lines = [f"Order of the conditions: {', then '.join(condition_words)}.",
             "At each step, the knowledge base rules check the drugs chosen so far (forward chaining).",
             "A drug that is not suitable is a dead end: the planner goes back and tries the next drug."]
    for number, (attempt, outcome, rejected_facts) in enumerate(result["steps"], start=1):
        depth = len(attempt) - 1
        drug = attempt[-1]
        tried = f"{'  ' * depth}{CONDITION_WORDS[needs[depth]]}: try {drug}"
        if outcome == "not suitable":
            reasons = problems_about(drug, rejected_facts, patient)
            for fact in sorted(rejected_facts, key=kb.show_pattern):
                if fact[2] != drug and not (isinstance(fact[3], tuple) and fact[3][1] == drug):
                    reasons.append(f"{fact[2]}: {short_reason(fact[3], patient)}")
            said = "not suitable: " + "; ".join(reasons)
        elif outcome == "complete":
            said = "complete option found"
        else:
            said = "fine so far"
        lines.extend(wrap_row(f"  {number:>2}. {tried:<40} -> ", said))
    found = len(result["ranked"])
    summary = (f"{count_words(found, 'safe option')} found. The search made {result['states_generated']} of the "
               f"{result['full_tree_size']} possible states (counting the start). ")
    if result["states_generated"] < result["full_tree_size"]:
        summary = summary + "Fewer states were needed, because drugs that are not suitable are cut off before going deeper."
    else:
        summary = summary + "Every state was made, because each problem was only found at the last condition."
    lines.extend(wrap_row("Result: ", summary))
    return lines


# ---------------------------------------------------------------------------
# Why some drugs are not suitable (each problem once)
# ---------------------------------------------------------------------------

def problem_summary_lines(patient, result):
    """
    Each problem the search met, said once, with how many complete combinations it ruled out.
    Many dead ends can share one problem (Patient1: Warfarin + Ibuprofen in 8 of them).
    """
    needs = patient["needs"]
    combinations_of = {}
    for regimen, rejected_facts in result["dead_ends"]:
        ruled_out = 1
        for condition in needs[len(regimen):]:
            ruled_out = ruled_out * len(facts.CONDITIONS[condition])
        for fact in sorted(rejected_facts, key=kb.show_pattern):
            drug = fact[2]
            reason = fact[3]
            if isinstance(reason, tuple):
                text = f"{pair_name(drug, reason)}: must not be taken together (serious drug interaction)."
            else:
                text = f"{drug}: {short_reason(reason, patient)}."
            if text not in combinations_of:
                combinations_of[text] = 0
            combinations_of[text] = combinations_of[text] + ruled_out
    if len(combinations_of) == 0:
        return ["No drug was found not suitable."]
    lines = []
    for problem, count in combinations_of.items():
        lines.extend(wrap_row("  ", f"{problem} This ruled out {count_words(count, 'combination')}."))
    return lines


# ---------------------------------------------------------------------------
# How the planner explains a drug that is not suitable (backward chaining, in plain words)
# ---------------------------------------------------------------------------
# Each numbered question below is a sub-goal that the backward chainer (kb.prove) really proves, starting
# from the question "why is this drug not suitable?" and working back to the patient's details. The questions
# are written in plain words instead of the KB notation (SPEC section 12, decision 19).

# Plain names for the attributes, the same for every patient (no numbers in them).
ATTRIBUTE_PLAIN_NAMES = {
    "SevereKidneyImpairment": "severely reduced kidney function",
    "ModerateKidneyImpairment": "reduced kidney function",
    "ActiveLiverDisease": "liver disease",
    "Elderly": f"age {facts.ELDERLY_AGE_YEARS} or older",
    "AgeAtLeast80": f"age {facts.VERY_OLD_AGE_YEARS} or older",
}


def attribute_plain_name(attribute):
    """An attribute's plain name, for example "reduced kidney function" or "heart failure"."""
    if attribute in ATTRIBUTE_PLAIN_NAMES:
        return ATTRIBUTE_PLAIN_NAMES[attribute]
    return TYPED_ATTRIBUTE_WORDS[attribute]


def attribute_question(attribute, patient):
    """
    The question for one attribute, what it needs, and what the patient's profile shows, for example
    ("Reduced kidney function? (eGFR 30 to 44)", "eGFR is 40").
    """
    egfr = patient.get("egfr")
    if egfr is None:
        egfr_words = "eGFR not recorded"
    else:
        egfr_words = f"eGFR is {egfr}"
    if attribute == "SevereKidneyImpairment":
        return f"Severely reduced kidney function? (eGFR below {facts.SEVERE_KIDNEY_EGFR_BELOW})", egfr_words
    if attribute == "ModerateKidneyImpairment":
        return (f"Reduced kidney function? (eGFR {facts.SEVERE_KIDNEY_EGFR_BELOW} to "
                f"{facts.MODERATE_KIDNEY_EGFR_BELOW - 1})", egfr_words)
    if attribute in ["Elderly", "AgeAtLeast80"]:
        name = attribute_plain_name(attribute)
        return name[0].upper() + name[1:] + "?", f"age is {patient.get('age')}"
    if attribute == "ActiveLiverDisease":
        grades = []
        for typed in ["ModerateLiverImpairment", "SevereLiverImpairment"]:
            if typed in patient.get("has", []):
                grades.append(TYPED_ATTRIBUTE_WORDS[typed])
        if len(grades) == 0:
            shown = "none recorded"
        else:
            shown = join_words(grades) + " recorded"
        return "Liver disease? (moderate or severe liver impairment)", shown
    name = attribute_plain_name(attribute)
    if attribute in patient.get("has", []):
        shown = "recorded"
    else:
        shown = "not recorded"
    return name[0].upper() + name[1:] + "?", shown


def yes_or_no_words(answers, details):
    """ "YES, <details>" when the backward chainer proved the sub-goal, otherwise "no, <details>"."""
    if len(answers) > 0:
        return "YES, " + details
    return "no, " + details


def backward_steps_lines(patient, drug, regimen=None):
    """
    How the planner explains why a drug is not suitable, step by step, in plain words.
    Every question is a sub-goal proved by the backward chainer (kb.prove) from the stored facts only.
    """
    name = patient["name"]
    known_facts, other_drugs = stored_facts_for_why(patient, drug, regimen)

    def proved(goal):
        """Ask the backward chainer one sub-goal; it returns the ways the goal is true (empty if it fails)."""
        return kb.prove(goal, known_facts, kb.ALL_RULES, 0, [])

    questions = []

    # 1. Allergy (rule C1).
    allergic = proved(("Allergic", name, drug))
    if len(allergic) > 0:
        questions.append((f"Is the patient allergic to {drug}?", "YES, an allergy is recorded"))
    else:
        questions.append((f"Is the patient allergic to {drug}?", "no allergy recorded"))

    # 2. Pregnancy (rule C4).
    pregnant = proved(("Pregnant", name))
    if len(pregnant) == 0:
        questions.append(("Is the patient pregnant?", "no"))
    elif len(proved(("RejectIfPregnant", drug))) > 0:
        questions.append(("Is the patient pregnant?", f"YES, and {drug} is ruled out in pregnancy"))
    else:
        questions.append(("Is the patient pregnant?", f"yes, but {drug} is not ruled out in pregnancy"))

    # 3. The patient's conditions and test results (rule C2): first what the KB says about the drug,
    #    then each of those attributes, proved back to the patient's details (rules B).
    ruled_out_with = proved(("RejectIfHas", drug, "?attribute"))
    attribute_names = []
    for answer in ruled_out_with:
        attribute_names.append(attribute_plain_name(answer["?attribute"]))
    if len(attribute_names) == 0:
        questions.append((f"What does the knowledge base say about {drug}?", "no condition rules it out"))
    else:
        questions.append((f"What does the knowledge base say about {drug}?",
                          "not suitable with:"))
        questions.append(("    " + ", ".join(attribute_names), None))
    for answer in ruled_out_with:
        attribute = answer["?attribute"]
        question, shown = attribute_question(attribute, patient)
        questions.append(("  " + question, yes_or_no_words(proved(("Has", name, attribute)), shown)))

    # 4. Serious drug interactions (rules C6/C7 with chosen drugs, F1 to F3 with drugs already taken).
    others = []
    for other_drug in other_drugs:
        others.append((other_drug, other_drug))
    for other_drug in patient.get("current_medications", []):
        others.append((other_drug, other_drug + " (already taken)"))
    if len(others) == 0:
        questions.append(("Serious interaction with another drug?", "no other drugs chosen"))
    else:
        listed = []
        found = []
        for other_drug, shown in others:
            listed.append(shown)
            major = proved(("Interacts", drug, other_drug, "Major")) + proved(("Interacts", other_drug, drug, "Major"))
            if len(major) > 0:
                found.append(shown)
        question = "Serious interaction with the other chosen drugs?"
        if len(found) > 0:
            questions.append((question, f"YES, with {join_words(found)} (checked: {', '.join(listed)})"))
        else:
            questions.append((question, f"no (checked: {', '.join(listed)})"))

    lines = [f"Question: why is {drug} not suitable for {name}?",
             "The planner starts from the question and works back to the patient's details:"]
    question_width = 0
    for question, said in questions:
        if said is not None:
            question_width = max(question_width, len(question))
    number = 0
    for question, said in questions:
        if said is None:
            lines.extend(wrap_row("      ", question.strip()))
            continue
        number += 1
        lines.extend(wrap_row(f"  {number:>2}. {question.ljust(question_width)}  -> ", said))

    # The answer comes from the same backward chainer, through why() and explain().
    answer = " ".join(explain(patient, drug, regimen).split())
    lines.extend(wrap_row("Answer: ", answer))
    return lines


def drugs_to_explain(result):
    """Each drug the search found not suitable, once, with the dead end where it was first found."""
    explained = []
    to_explain = []
    for regimen, rejected_facts in result["dead_ends"]:
        for fact in sorted(rejected_facts, key=kb.show_pattern):
            drug = fact[2]
            if drug not in explained:
                explained.append(drug)
                to_explain.append((drug, list(regimen)))
    return to_explain


# ---------------------------------------------------------------------------
# The patient report: used by both `python run_demo.py Patient3` and `python enter_patient.py`
# ---------------------------------------------------------------------------
# One report, so the demo and a typed-in patient look the same (SPEC section 12, decision 20):
# the patient, medicines already taken, the options with points, cautions for the best option,
# why it is the best option, and why some drugs are not suitable.

def yes_or_no(value):
    """True becomes "yes", False becomes "no"."""
    if value:
        return "yes"
    return "no"


# The report's table shows at most this many options, but always every option tied for best
# (SPEC section 12, decision 22). A line under the table says how many more there are.
REPORT_OPTIONS_SHOWN = 10


def ranked_table(needs, result):
    """
    The safe options, best first, with their points, number of cautions and dose note. The best ones are marked
    with *. At most REPORT_OPTIONS_SHOWN rows (more only if more are tied for best); if some are left out, a line
    under the table says how many.
    """
    header = ["Rank"]
    for condition in needs:
        header.append(CONDITION_WORDS[condition])
    header = header + ["Points", "Cautions", "Dose note"]
    rows = [header]
    shown_count = max(REPORT_OPTIONS_SHOWN, len(result["winners"]))
    for rank, (regimen, points, flag_count, dose_note) in enumerate(result["ranked"][:shown_count], start=1):
        label = str(rank)
        if regimen in result["winners"]:
            label = label + " *"
        rows.append([label] + list(regimen) + [str(points), str(flag_count), yes_or_no(dose_note)])
    lines = table_lines(rows)
    total = len(result["ranked"])
    if total > shown_count:
        lines.append(f"Showing the best {shown_count} of {total} safe options. "
                     f"The other {total - shown_count} have more concerns and are not shown.")
    return lines


def join_clauses(clauses):
    """
    Join clauses with "and", saying "the patient" only once:
    ["the patient is 65 or older (age 82)", "the patient has reduced kidney function"] gives
    "the patient is 65 or older (age 82) and has reduced kidney function".
    """
    shortened = [clauses[0]]
    for clause in clauses[1:]:
        if clauses[0].startswith("the patient ") and clause.startswith("the patient "):
            shortened.append(clause[len("the patient "):])
        else:
            shortened.append(clause)
    return join_words(shortened)


def cautions_for_best_lines(patient, result):
    """
    The cautions for the best option only, one row per drug that needs care, said like a person would.
    Apixaban's dose note (or the reminder when a number is missing) is in Apixaban's row.
    """
    best_regimen = result["ranked"][0][0]
    best_facts = kb.chain_regimen(patient, list(best_regimen))
    clauses_of = {}
    for fact in sorted(kb.facts_named(best_facts, "Flagged"), key=kb.show_pattern):
        drug = fact[2]
        if drug not in clauses_of:
            clauses_of[drug] = []
        clauses_of[drug].append(reason_clause(fact[3], patient))

    rows = []
    for drug in best_regimen:
        if drug in clauses_of:
            rows.append((drug, f"use with care, because {join_clauses(clauses_of[drug])}."))
        if drug == "Apixaban" and len(kb.facts_named(best_facts, "DoseNote")) > 0:
            rows.append((drug, f"a lower dose may be needed, because the patient {dose_reasons(patient)}."))
        elif drug == "Apixaban":
            attributes = kb.attributes_of(kb.forward_chain(kb.patient_facts(patient), kb.ATTRIBUTE_RULES),
                                          patient["name"])
            true_count = 0
            missing = []
            for attribute, field, unit in DOSE_NOTE_PARTS:
                if attribute in attributes:
                    true_count += 1
                if patient.get(field) is None:
                    missing.append(field)
            if len(missing) > 0 and true_count + len(missing) >= facts.APIXABAN_DOSE_NOTE_MINIMUM:
                rows.append((drug, missing_number_sentence(patient, attributes, missing)))

    title = f"Cautions for the best option ({' + '.join(best_regimen)}):"
    if len(rows) == 0:
        return [title + " none."]
    label_width = 0
    for drug, words in rows:
        label_width = max(label_width, len(drug) + 1)
    lines = [title]
    previous_drug = None
    for drug, words in rows:
        if drug == previous_drug:
            label = "  " + " " * label_width + "  "
        else:
            label = "  " + (drug + ":").ljust(label_width) + "  "
        lines.extend(wrap_row(label, words))
        previous_drug = drug
    return lines


def egfr_attributes():
    """
    The attributes that come from eGFR, read from the attribute rules (B3 and B4): the rules whose condition is an
    EGFR fact. Today: SevereKidneyImpairment and ModerateKidneyImpairment.
    """
    attributes = []
    for rule in kb.ATTRIBUTE_RULES:
        for condition in rule["conditions"]:
            if condition[0] == "EGFR" and rule["conclusion"][2] not in attributes:
                attributes.append(rule["conclusion"][2])
    return attributes


def kidney_restricted_drugs():
    """
    The drugs whose restrictions depend on eGFR, read from the KB facts (RejectIfHas and FlagIfHas), in the order of
    kb_facts.py. Today: Metformin, Ibuprofen and Glipizide. No drug name is written into the code.
    """
    drugs = []
    for fact in kb.static_fact_list():
        if fact[0] in ["RejectIfHas", "FlagIfHas"] and fact[2] in egfr_attributes() and fact[1] not in drugs:
            drugs.append(fact[1])
    return drugs


def shown_regimens(result):
    """The regimens shown in the report's table: the complete ones, or the ones for the other conditions."""
    if len(result["ranked"]) == 0 and result["other_conditions"] is not None:
        result = result["other_conditions"]
    shown_count = max(REPORT_OPTIONS_SHOWN, len(result["winners"]))
    regimens = []
    for row in result["ranked"][:shown_count]:
        regimens.append(row[0])
    return regimens


def missing_egfr_note(patient, result):
    """
    When eGFR was not recorded, the kidney checks are skipped (closed world), so drugs with kidney restrictions
    look free of concerns. If a shown option has such a drug, remind the reader to check eGFR
    (SPEC section 12, decision 25). This is a plain check in the printout, not a rule (a rule would need
    "not recorded"), and it does not change the ranking.
    """
    if patient.get("egfr") is not None:
        return []
    if result.get("nothing_to_plan"):
        # Every condition is already treated: there is no options table, so no drug to name.
        return []
    named = []
    for drug in kidney_restricted_drugs():
        for regimen in shown_regimens(result):
            if drug in regimen and drug not in named:
                named.append(drug)
    if len(named) == 0:
        return []
    if len(named) == 1:
        verb = "has"
    else:
        verb = "have"
    return [f"Note: eGFR was not recorded. Please check it: {join_words(named)} {verb} kidney restrictions."]


def report_lines(patient):
    """The whole patient report, with the separators still as markers (see draw_separators)."""
    result = plan(patient)
    if result["message"] is not None:
        return [THICK_LINE, result["message"], THICK_LINE]

    needs_words = []
    for condition in patient["needs"]:
        needs_words.append(CONDITION_WORDS[condition])
    lines = [THICK_LINE, f"{patient['name'].upper()}   needs: {', '.join(needs_words)}", THICK_LINE,
             describe_patient(patient)]
    lines.extend(unusual_value_notes(patient))
    lines.extend(missing_egfr_note(patient, result))
    lines.extend(current_medication_lines(patient))
    lines.append(THIN_LINE)
    if result["nothing_to_plan"]:
        lines.append("Nothing else to plan: every condition asked for is already treated.")
        lines.append(THICK_LINE)
        return lines

    planned_patient = dict(patient, needs=result["planned_needs"])
    saved = result["full_tree_size"] - result["states_generated"]
    lines.append(f"Search: {result['states_generated']} of {result['full_tree_size']} states generated "
                 f"({saved} saved by pruning)")
    safe = result["regimen_count"] - result["invalid_count"]
    lines.append(f"Regimens: {result['regimen_count']} complete, {result['invalid_count']} not suitable, {safe} safe")
    lines.append("")

    # The options: the complete ones, or (Idea A) the options for the conditions that are not blocked.
    best_patient = None
    best_result = None
    if len(result["ranked"]) > 0:
        lines.extend(ranked_table(planned_patient["needs"], result))
        lines.append("* = best (tied options are all marked)")
        lines.append("Options are listed from fewest to most concerns.")
        best_patient = planned_patient
        best_result = result
    else:
        blocked_words = []
        for condition in result["blocked_conditions"]:
            blocked_words.append(CONDITION_WORDS[condition])
        if len(blocked_words) > 0:
            lines.append(f"NO COMPLETE PLAN: {join_words(blocked_words)} has no suitable drug in the planner's list. "
                         "A doctor needs to decide.")
        else:
            lines.append("NO COMPLETE PLAN: each condition has an allowed drug, but they cannot be combined. "
                         "A doctor needs to decide.")
        other = result["other_conditions"]
        if other is not None and len(other["ranked"]) > 0:
            other_needs = []
            for condition in planned_patient["needs"]:
                if condition not in result["blocked_conditions"]:
                    other_needs.append(condition)
            lines.append("")
            lines.append("Options for the other conditions:")
            lines.extend(ranked_table(other_needs, other))
            lines.append("* = best (tied options are all marked)")
            lines.append("Options are listed from fewest to most concerns.")
            lines.append(f"The drug chosen later for {join_words(blocked_words)} could not be checked "
                         "against these options.")
            best_patient = dict(patient, needs=other_needs)
            best_result = other

    if best_result is not None:
        lines.append(THIN_LINE)
        lines.extend(cautions_for_best_lines(best_patient, best_result))
        lines.append(THIN_LINE)
        lines.extend(why_this_option_lines(best_patient, best_result))
    lines.append(THIN_LINE)
    lines.append("Why some drugs are not suitable:")
    lines.extend(problem_summary_lines(planned_patient, result))
    lines.append(THICK_LINE)
    return lines


def patient_report(patient):
    """The patient report as lines of text, with the separator lines drawn."""
    return draw_separators(report_lines(patient))


def steps_report(patient):
    """
    The steps, for presenting the method:
    PART 1: how the planner searched (depth-first search, with forward chaining at each step);
    PART 2: how the planner explains each drug that is not suitable (backward chaining), each drug once.
    """
    result = plan(patient)
    if result["message"] is not None:
        return draw_separators([THICK_LINE, result["message"], THICK_LINE])
    if result["nothing_to_plan"]:
        return draw_separators([THICK_LINE, "Nothing was planned, so there are no steps to show.", THICK_LINE])
    planned_patient = dict(patient, needs=result["planned_needs"])
    lines = [THICK_LINE,
             f"{patient['name'].upper()}: STEP BY STEP",
             describe_patient(patient),
             THICK_LINE,
             "PART 1: HOW THE PLANNER SEARCHED (depth-first search, with forward chaining at each step)",
             THIN_LINE]
    lines.extend(search_steps_lines(planned_patient, result))
    lines.append(THICK_LINE)
    lines.append("PART 2: HOW THE PLANNER EXPLAINS EACH DRUG THAT IS NOT SUITABLE (backward chaining)")
    to_explain = drugs_to_explain(result)
    if len(to_explain) == 0:
        lines.append(THIN_LINE)
        lines.append("No drug was found not suitable, so there is nothing to explain.")
    for drug, regimen in to_explain:
        lines.append(THIN_LINE)
        lines.extend(backward_steps_lines(planned_patient, drug, regimen))
    lines.append(THICK_LINE)
    return draw_separators(lines)
