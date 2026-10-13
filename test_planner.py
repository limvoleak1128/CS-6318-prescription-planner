"""
Tests for The Prescription Planner. Run with: python -m unittest
"""
import random
import unittest
from itertools import product

import enter_patient
import kb
import kb_facts
import planner
import reference_evaluator
import search
from test_patients import EXPECTED, PATIENTS


def find_patient(name):
    """Return the test patient with this name from test_patients.py."""
    for patient in PATIENTS:
        if patient["name"] == name:
            return patient
    raise KeyError(name)


def report_text(patient):
    """The patient report (planner.patient_report) as one string."""
    return "\n".join(planner.patient_report(patient))


def derived_attributes(patient):
    """Chain the patient's facts with rules B, and return the attributes the patient ends up with."""
    all_facts = kb.forward_chain(kb.patient_facts(patient), kb.ATTRIBUTE_RULES)
    return kb.attributes_of(all_facts, patient["name"])


def reason_label(reason):
    """Write a reason the way reference_evaluator.py writes it, for example "InteractionWith(Ibuprofen)"."""
    if isinstance(reason, tuple):
        return f"{reason[0]}({reason[1]})"
    return reason


def verdict_in_reference_format(known_facts):
    """
    Turn the chainer's Rejected, Flagged and DoseNote facts into the same shape that
    reference_evaluator.judge_regimen returns, so the two can be compared directly.
    """
    # Each fact looks like (predicate, patient, drug, reason), so the drug is at place 2 and the reason at 3.
    rejected = set()
    for fact in kb.facts_named(known_facts, "Rejected"):
        drug = fact[2]
        reason = fact[3]
        rejected.add((drug, reason_label(reason)))
    flag_labels = set()
    for fact in kb.facts_named(known_facts, "Flagged"):
        drug = fact[2]
        reason = fact[3]
        if isinstance(reason, tuple):
            flag_labels.add(f"{drug}+{reason[1]}:Moderate")
        else:
            flag_labels.add(f"{drug}:{reason}")
    for fact in kb.facts_named(known_facts, "DoseNote"):
        drug = fact[2]
        flag_labels.add(f"{drug}:DoseNote")
    return rejected, flag_labels


def single_drugs_and_pairs(patient):
    """Every single candidate drug, and every pair of drugs for two different needed conditions."""
    candidate_lists = reference_evaluator.candidate_lists(patient)
    regimens = []
    for drugs in candidate_lists:
        for drug in drugs:
            regimens.append((drug,))
    for first_index in range(len(candidate_lists)):
        for second_index in range(first_index + 1, len(candidate_lists)):
            for first_drug in candidate_lists[first_index]:
                for second_drug in candidate_lists[second_index]:
                    regimens.append((first_drug, second_drug))
    return regimens


class TestStep1FactsAndAttributes(unittest.TestCase):
    """Step 1: building facts, matching, and the attribute rules (rules B)."""

    def test_static_facts_count(self):
        """kb_facts.py holds 61 facts."""
        self.assertEqual(len(kb.static_facts()), 61)

    def test_static_facts_examples(self):
        """A few facts look the way SPEC section 5.1 describes."""
        known_facts = kb.static_facts()
        self.assertIn(("Treats", "Metformin", "Type2Diabetes"), known_facts)
        self.assertIn(("Interacts", "Warfarin", "Ibuprofen", "Major"), known_facts)
        self.assertIn(("RejectIfHas", "Metformin", "ModerateKidneyImpairment"), known_facts)
        self.assertIn(("FlagIfHas", "Glipizide", "Elderly"), known_facts)
        self.assertIn(("RejectIfPregnant", "Warfarin"), known_facts)
        self.assertIn(("FlagIfPregnant", "Acetaminophen"), known_facts)

    def test_patient3_facts(self):
        """Patient3's profile becomes exactly these facts. Not pregnant, so no Pregnant fact."""
        expected = {
            ("Needs", "Patient3", "Type2Diabetes"),
            ("Needs", "Patient3", "ChronicPain"),
            ("Needs", "Patient3", "AtrialFibrillation"),
            ("Age", "Patient3", 58),
            ("Weight", "Patient3", 80),
            ("EGFR", "Patient3", 40),
            ("Creatinine", "Patient3", 1.9),
        }
        self.assertEqual(kb.patient_facts(find_patient("Patient3")), expected)

    def test_match_pattern_binds_variables(self):
        """SUBST: variables take the values in the same places in the fact."""
        bindings = kb.match_pattern(("EGFR", "?patient", "?score"), ("EGFR", "Patient3", 40), {})
        self.assertEqual(bindings, {"?patient": "Patient3", "?score": 40})

    def test_match_pattern_rejects_disagreement(self):
        """A variable that already has a value must agree with the fact."""
        self.assertIsNone(kb.match_pattern(("EGFR", "?patient", "?score"),
                                           ("EGFR", "Patient3", 40), {"?patient": "Patient1"}))
        self.assertIsNone(kb.match_pattern(("Age", "?patient", "?years"),
                                           ("EGFR", "Patient3", 40), {}))
        self.assertIsNone(kb.match_pattern(("Pregnant", "?patient"),
                                           ("EGFR", "Patient3", 40), {}))

    def test_patient3_attributes(self):
        """eGFR 40 gives ModerateKidneyImpairment, creatinine 1.9 gives HighCreatinine. Nothing else."""
        self.assertEqual(derived_attributes(find_patient("Patient3")),
                         {"ModerateKidneyImpairment", "HighCreatinine"})

    def test_liver_impairment_gives_active_liver_disease(self):
        """Assumption 1: Patient4 has ModerateLiverImpairment, so also ActiveLiverDisease."""
        self.assertEqual(derived_attributes(find_patient("Patient4")),
                         {"ModerateLiverImpairment", "ActiveLiverDisease"})

    def test_attributes_agree_with_reference_for_all_patients(self):
        """For all 8 test patients, rules B give the same attributes as the reference evaluator."""
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.assertEqual(derived_attributes(patient),
                                 reference_evaluator.build_attributes(patient))

    def test_forward_chain_only_adds(self):
        """The chainer keeps every starting fact and does not change the set it was given."""
        starting_facts = kb.patient_facts(find_patient("Patient3"))
        copy_before = set(starting_facts)
        all_facts = kb.forward_chain(starting_facts, kb.ATTRIBUTE_RULES)
        self.assertTrue(copy_before.issubset(all_facts))
        self.assertEqual(starting_facts, copy_before)

    def test_age_under_18_is_refused(self):
        """Adults only: a 15-year-old gets the agreed message, with the age as entered."""
        patient = dict(find_patient("Patient3"), age=15)
        self.assertEqual(kb.age_problem(patient),
                         "The Prescription Planner is designed for adults. "
                         "This patient (age 15) is outside what it covers, so no plan was made.")

    def test_missing_age_is_refused(self):
        """Age is required."""
        patient = dict(find_patient("Patient3"))
        del patient["age"]
        self.assertEqual(kb.age_problem(patient),
                         "The Prescription Planner needs the patient's age. "
                         "No age was recorded for this patient, so no plan was made.")

    def test_adults_are_accepted(self):
        """Age 18 is accepted (the boundary), and so are all 8 test patients."""
        self.assertIsNone(kb.age_problem(dict(find_patient("Patient3"), age=18)))
        for patient in PATIENTS:
            self.assertIsNone(kb.age_problem(patient))


class TestStep2Rules(unittest.TestCase):
    """Step 2: rules A, C, D, E, tried on single drugs and pairs."""

    def test_rule_count(self):
        """SPEC section 5.2 lists 29 rules: 21 in groups A to E, plus 4 in group F and 4 in group G (step 6)."""
        self.assertEqual(len(kb.ALL_RULES), 29)

    def test_patient3_candidates(self):
        """Rule A: Patient3 needs three conditions, so the six drugs that treat them are candidates."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), [])
        candidates = set()
        for fact in kb.facts_named(all_facts, "Candidate"):
            candidates.add(fact[2])
        self.assertEqual(candidates, {"Metformin", "Glipizide", "Ibuprofen", "Acetaminophen",
                                      "Warfarin", "Apixaban"})

    def test_nothing_chosen_gives_no_verdict(self):
        """With no drug chosen, no check rule can fire, so the regimen is not invalid."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), [])
        self.assertEqual(kb.facts_named(all_facts, "Rejected"), set())
        self.assertEqual(kb.facts_named(all_facts, "InvalidRegimen"), set())

    def test_patient3_metformin_rejected(self):
        """Rule C2 then E: eGFR 40 means ModerateKidneyImpairment, which rejects Metformin."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), ["Metformin"])
        self.assertEqual(kb.facts_named(all_facts, "Rejected"),
                         {("Rejected", "Patient3", "Metformin", "ModerateKidneyImpairment")})
        self.assertIn(("InvalidRegimen", "Patient3"), all_facts)

    def test_patient3_glipizide_flagged_not_rejected(self):
        """Rule C3: ModerateKidneyImpairment flags Glipizide, but does not reject it."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), ["Glipizide"])
        self.assertEqual(kb.facts_named(all_facts, "Flagged"),
                         {("Flagged", "Patient3", "Glipizide", "ModerateKidneyImpairment")})
        self.assertNotIn(("InvalidRegimen", "Patient3"), all_facts)

    def test_patient3_major_interaction(self):
        """Rules C6 and C7: Warfarin with Ibuprofen is a Major conflict, so Warfarin is rejected."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), ["Ibuprofen", "Warfarin"])
        self.assertIn(("Conflict", "Patient3", "Warfarin", "Ibuprofen", "Major"), all_facts)
        self.assertIn(("Rejected", "Patient3", "Warfarin", ("InteractionWith", "Ibuprofen")), all_facts)
        self.assertIn(("InvalidRegimen", "Patient3"), all_facts)

    def test_patient3_moderate_interaction(self):
        """Rules C6 and C8: Apixaban with Ibuprofen is a Moderate conflict, so Apixaban is flagged."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), ["Ibuprofen", "Apixaban"])
        self.assertIn(("Flagged", "Patient3", "Apixaban", ("InteractionWith", "Ibuprofen")), all_facts)
        self.assertNotIn(("InvalidRegimen", "Patient3"), all_facts)

    def test_allergy_rejects(self):
        """Rule C1: a drug the patient is allergic to is rejected."""
        patient = dict(find_patient("Patient3"), allergies=["Glipizide"])
        all_facts = kb.chain_regimen(patient, ["Glipizide"])
        self.assertIn(("Rejected", "Patient3", "Glipizide", "Allergy"), all_facts)

    def test_pregnancy_rejects_and_flags(self):
        """Rules C4 and C5: Patient6 is pregnant, so Lisinopril is rejected and Amlodipine is flagged."""
        patient = find_patient("Patient6")
        self.assertIn(("Rejected", "Patient6", "Lisinopril", "Pregnancy"),
                      kb.chain_regimen(patient, ["Lisinopril"]))
        self.assertIn(("Flagged", "Patient6", "Amlodipine", "Pregnancy"),
                      kb.chain_regimen(patient, ["Amlodipine"]))

    def test_dose_note_for_patient1(self):
        """Rule D1: Patient1 is 82 and weighs 58 kg (two of the three), so Apixaban gets the dose note."""
        all_facts = kb.chain_regimen(find_patient("Patient1"), ["Apixaban"])
        self.assertIn(("DoseNote", "Patient1", "Apixaban", "ReduceDose"), all_facts)
        self.assertNotIn(("InvalidRegimen", "Patient1"), all_facts)

    def test_no_dose_note_for_patient3(self):
        """Patient3 has only one of the three (high creatinine), so there is no dose note."""
        all_facts = kb.chain_regimen(find_patient("Patient3"), ["Apixaban"])
        self.assertEqual(kb.facts_named(all_facts, "DoseNote"), set())

    def test_chain_regimen_does_not_change_static_facts(self):
        """Each try starts fresh: trying a regimen leaves the static facts as they were."""
        before = kb.static_facts()
        kb.chain_regimen(find_patient("Patient3"), ["Metformin", "Ibuprofen", "Warfarin"])
        self.assertEqual(kb.static_facts(), before)

    def test_single_drugs_and_pairs_agree_with_reference(self):
        """For all 8 patients, every single drug and every pair gets the same rejections and flags."""
        for patient in PATIENTS:
            for regimen in single_drugs_and_pairs(patient):
                with self.subTest(patient=patient["name"], regimen=regimen):
                    all_facts = kb.chain_regimen(patient, list(regimen))
                    rejected, flag_labels = verdict_in_reference_format(all_facts)
                    expected = reference_evaluator.judge_regimen(patient, regimen)
                    self.assertEqual(rejected, set(expected["rejected"]))
                    self.assertEqual(flag_labels, set(expected["flag_labels"]))
                    self.assertEqual(("InvalidRegimen", patient["name"]) in all_facts,
                                     len(expected["rejected"]) > 0)


if __name__ == "__main__":
    unittest.main()


class TestStep3SearchAndRanking(unittest.TestCase):
    """Step 3: the depth-first search, the ranking, and plan(patient)."""

    def test_answer_key(self):
        """Test 1 in SPEC section 9: plan(patient) matches EXPECTED for all 8 patients."""
        for patient in PATIENTS:
            name = patient["name"]
            result = planner.plan(patient)
            for field in ["regimen_count", "invalid_count", "ranked", "winners",
                          "blocked_conditions", "states_generated", "full_tree_size"]:
                with self.subTest(patient=name, field=field):
                    self.assertEqual(result[field], EXPECTED[name][field])

    def test_patient3_states(self):
        """Patient3: the search creates 9 of the 15 states in the full tree, because dead ends are cut off."""
        result = planner.plan(find_patient("Patient3"))
        self.assertEqual(result["states_generated"], 9)
        self.assertEqual(result["full_tree_size"], 15)

    def test_patient3_dead_ends(self):
        """Patient3: Metformin is a dead end at the first level, for reduced kidney function."""
        result = planner.plan(find_patient("Patient3"))
        dead_end_regimens = []
        for regimen, rejected_facts in result["dead_ends"]:
            dead_end_regimens.append(regimen)
        self.assertIn(("Metformin",), dead_end_regimens)
        self.assertIn(("Glipizide", "Ibuprofen", "Warfarin"), dead_end_regimens)
        for regimen, rejected_facts in result["dead_ends"]:
            if regimen == ("Metformin",):
                self.assertEqual(rejected_facts,
                                 {("Rejected", "Patient3", "Metformin", "ModerateKidneyImpairment")})

    def test_age_problem_stops_the_plan(self):
        """A 15-year-old gets the message and no search is run."""
        result = planner.plan(dict(find_patient("Patient3"), age=15))
        self.assertEqual(list(result.keys()), ["message"])
        self.assertIn("designed for adults", result["message"])

    def test_plan_made_has_no_message(self):
        """A normal patient gets no message and no plan for other conditions."""
        result = planner.plan(find_patient("Patient3"))
        self.assertIsNone(result["message"])
        self.assertIsNone(result["other_conditions"])

    def test_idea_a_plans_the_other_conditions(self):
        """
        Idea A: Patient5b has no complete regimen because ChronicPain is blocked. The other two conditions
        are planned anyway. Patient5 is the same patient without ChronicPain, so the answers must match.
        """
        result = planner.plan(find_patient("Patient5b"))
        self.assertEqual(result["blocked_conditions"], ["ChronicPain"])
        self.assertEqual(result["other_conditions"]["ranked"], EXPECTED["Patient5"]["ranked"])

    def test_no_plan_without_a_blocked_condition(self):
        """
        Every condition has an allowed drug (Warfarin, Ibuprofen), but those two cannot be combined.
        Nothing is blocked, so there is nothing to leave out, and no plan for other conditions is made.
        """
        patient = {"name": "PairOnly", "needs": ["AtrialFibrillation", "ChronicPain"], "age": 50,
                   "pregnant": False, "allergies": ["Apixaban", "Acetaminophen"], "has": []}
        result = planner.plan(patient)
        self.assertEqual(result["ranked"], [])
        self.assertEqual(result["blocked_conditions"], [])
        self.assertIsNone(result["other_conditions"])


def forward_verdict_for_drug(patient, regimen, drug):
    """What the FORWARD chainer concludes about one drug in a regimen, in the same shape as why() reports it."""
    all_facts = kb.chain_regimen(patient, list(regimen))
    rejected = set()
    flagged = set()
    others_rejected = set()
    others_flagged = set()
    for fact in kb.facts_named(all_facts, "Rejected"):
        if fact[2] == drug:
            rejected.add(fact[3])
        elif fact[3] == ("InteractionWith", drug):
            others_rejected.add(fact[2])
    for fact in kb.facts_named(all_facts, "Flagged"):
        if fact[2] == drug:
            flagged.add(fact[3])
        elif fact[3] == ("InteractionWith", drug):
            others_flagged.add(fact[2])
    dose_note = ("DoseNote", patient["name"], drug, "ReduceDose") in all_facts
    return rejected, flagged, others_rejected, others_flagged, dose_note


class TestStep4WhyAndPrinting(unittest.TestCase):
    """Step 4: why() by backward chaining, and the printout for the reader."""

    def test_why_patient3_metformin(self):
        """Test 9 in SPEC section 9: why(patient3, "Metformin") reports ModerateKidneyImpairment."""
        result = planner.why(find_patient("Patient3"), "Metformin")
        self.assertEqual(result["rejected_reasons"], ["ModerateKidneyImpairment"])
        self.assertIn("Drug-condition  rejected: ModerateKidneyImpairment", result["text"])

    def test_why_tries_facts_in_kb_order(self):
        """The trace is the same every time: the three RejectIfHas facts are tried in kb_facts.py order."""
        text = planner.why(find_patient("Patient3"), "Metformin")["text"]
        severe = text.index("attribute = SevereKidneyImpairment")
        moderate = text.index("attribute = ModerateKidneyImpairment")
        liver = text.index("attribute = ActiveLiverDisease")
        self.assertLess(severe, moderate)
        self.assertLess(moderate, liver)

    def test_why_age_flag_and_dose_note(self):
        """Patient1 (age 82, 58 kg): Metformin gets the age flag, and Apixaban gets the dose note."""
        patient = find_patient("Patient1")
        self.assertEqual(planner.why(patient, "Metformin")["flagged_reasons"], ["AgeAtLeast80"])
        self.assertTrue(planner.why(patient, "Apixaban")["dose_note"])

    def test_why_interaction_from_both_sides(self):
        """Warfarin with Ibuprofen: Warfarin is rejected; asking about Ibuprofen shows that too."""
        patient = find_patient("Patient3")
        warfarin = planner.why(patient, "Warfarin", ["Ibuprofen", "Warfarin"])
        self.assertEqual(warfarin["rejected_reasons"], [("InteractionWith", "Ibuprofen")])
        ibuprofen = planner.why(patient, "Ibuprofen", ["Ibuprofen", "Warfarin"])
        self.assertEqual(ibuprofen["others_rejected"], ["Warfarin"])

    def test_why_age_problem(self):
        """why() also refuses a patient under 18."""
        result = planner.why(dict(find_patient("Patient3"), age=15), "Metformin")
        self.assertIn("designed for adults", result["text"])

    def test_backward_agrees_with_forward(self):
        """
        For all 8 patients, every single drug and every pair: for each drug, the backward chainer (why)
        finds exactly what the forward chainer concludes. Two different methods, same answers.
        """
        for patient in PATIENTS:
            for regimen in single_drugs_and_pairs(patient):
                for drug in regimen:
                    with self.subTest(patient=patient["name"], regimen=regimen, drug=drug):
                        result = planner.why(patient, drug, list(regimen))
                        rejected, flagged, others_rejected, others_flagged, dose_note = \
                            forward_verdict_for_drug(patient, regimen, drug)
                        self.assertEqual(set(result["rejected_reasons"]), rejected)
                        self.assertEqual(set(result["flagged_reasons"]), flagged)
                        self.assertEqual(set(result["others_rejected"]), others_rejected)
                        self.assertEqual(set(result["others_flagged"]), others_flagged)
                        self.assertEqual(result["dose_note"], dose_note)

    def test_printout_liver_wording(self):
        """
        Assumption 1: liver disease comes from the patient's liver impairment, so the reader sees the
        impairment the patient actually has, and both kinds of liver restriction share one heading.
        """
        patient4 = report_text(find_patient("Patient4"))
        self.assertIn("Metformin: moderate liver impairment.", patient4)
        self.assertNotIn("liver disease", patient4)
        patient5b = report_text(find_patient("Patient5b"))
        self.assertIn("Acetaminophen: severe liver impairment.", patient5b)

    def test_why_short_and_full(self):
        """The short why leaves out the steps of goals that fail; the full why keeps them. Same answers."""
        patient = find_patient("Patient3")
        short = planner.why(patient, "Metformin")
        full = planner.why(patient, "Metformin", full=True)
        self.assertNotIn("Try rule C1", short["text"])
        self.assertIn("Try rule C1", full["text"])
        self.assertIn("Try rule C2", short["text"])
        self.assertEqual(short["rejected_reasons"], full["rejected_reasons"])
        self.assertLess(len(short["text"]), len(full["text"]))

    def test_printout_no_complete_plan(self):
        """Patient5b (Idea A): says Pain has no suitable drug, then plans the other conditions."""
        text = report_text(find_patient("Patient5b"))
        self.assertIn("NO COMPLETE PLAN: Pain has no suitable drug in the planner's list. A doctor needs to decide.",
                      text)
        self.assertIn("Options for the other conditions:", text)
        self.assertIn("The drug chosen later for Pain could not be checked against these options.", text)

    def test_printout_pair_that_cannot_be_combined(self):
        """No blocked condition, but the only allowed drugs cannot be taken together."""
        patient = {"name": "PairOnly", "needs": ["AtrialFibrillation", "ChronicPain"], "age": 50,
                   "pregnant": False, "allergies": ["Apixaban", "Acetaminophen"], "has": []}
        text = report_text(patient)
        self.assertIn("NO COMPLETE PLAN: each condition has an allowed drug, but they cannot be combined.", text)
        self.assertIn("Warfarin + Ibuprofen: must not be taken together", text)

    def test_printout_age_problem(self):
        """Under 18: only the agreed message, without the patient's name."""
        text = report_text(dict(find_patient("Patient3"), age=15))
        self.assertIn("This patient (age 15) is outside what it covers", text)
        self.assertNotIn("Patient3", text)

    def test_printout_uses_plain_words(self):
        """Decision 6: the reader never sees the KB's internal names (the points are shown since decision 20)."""
        internal_names = (list(kb_facts.TYPED_ATTRIBUTES) + list(kb_facts.BUILT_ATTRIBUTES)
                          + ["InteractionWith", "Rejected", "Flagged"])
        for patient in PATIENTS:
            text = report_text(patient)
            for name in internal_names:
                with self.subTest(patient=patient["name"], name=name):
                    self.assertNotIn(name, text)


# ---------------------------------------------------------------------------
# Step 5 helpers
# ---------------------------------------------------------------------------

def random_patient(generator, number):
    """
    Make one random adult patient: random conditions in a random order, random numbers (sometimes
    missing), pregnancy, typed attributes and allergies. `generator` is a random.Random with a fixed seed,
    so the same patients are made every time the tests run.
    """
    conditions = list(kb_facts.CONDITIONS.keys())
    generator.shuffle(conditions)
    needs = conditions[:generator.randint(1, len(conditions))]
    allergies = []
    for drugs in kb_facts.CONDITIONS.values():
        for drug in drugs:
            if generator.random() < 0.1:
                allergies.append(drug)
    has = []
    for attribute in kb_facts.TYPED_ATTRIBUTES:
        if generator.random() < 0.15:
            has.append(attribute)
    patient = {
        "name": f"Random{number}",
        "needs": needs,
        "age": generator.randint(kb.ADULT_AGE_YEARS, 95),
        "pregnant": generator.random() < 0.2,
        "allergies": allergies,
        "has": has,
    }
    # Each number is missing about one time in eight, to exercise the closed-world assumption.
    if generator.random() > 0.125:
        patient["weight"] = generator.randint(40, 120)
    if generator.random() > 0.125:
        patient["egfr"] = generator.randint(10, 120)
    if generator.random() > 0.125:
        patient["creatinine"] = round(generator.uniform(0.5, 3.5), 2)
    return patient


def random_patients(count):
    """The fixed set of random patients used by the tests (seed 2026)."""
    generator = random.Random(2026)
    patients = []
    for number in range(count):
        patients.append(random_patient(generator, number))
    return patients


def all_regimens(patient):
    """Every complete regimen for the patient: one candidate drug per needed condition."""
    return list(product(*reference_evaluator.candidate_lists(patient)))


def condition_treated_by(drug):
    """The condition this drug treats, from CONDITIONS."""
    for condition, drugs in kb_facts.CONDITIONS.items():
        if drug in drugs:
            return condition
    raise KeyError(drug)


def tiny_patient(drug, changes):
    """A small adult patient who needs only the condition this drug treats, with some changes."""
    patient = {"name": "Tiny", "needs": [condition_treated_by(drug)], "age": 50,
               "pregnant": False, "allergies": [], "has": []}
    patient.update(changes)
    return patient


# What to put in a tiny patient's profile so that they have a built attribute.
PROFILE_FOR_BUILT_ATTRIBUTE = {
    "SevereKidneyImpairment": {"egfr": 20},
    "ModerateKidneyImpairment": {"egfr": 40},
    "ActiveLiverDisease": {"has": ["ModerateLiverImpairment"]},
}


def profile_for(attribute):
    """Profile changes that give a patient this attribute (typed attributes are simply listed in "has")."""
    if attribute in PROFILE_FOR_BUILT_ATTRIBUTE:
        return PROFILE_FOR_BUILT_ATTRIBUTE[attribute]
    return {"has": [attribute]}


class TestStep5RemainingTests(unittest.TestCase):
    """Step 5: the remaining tests from SPEC section 9 (tests 2 to 8)."""

    # ---- Test 2: cross-check with the reference evaluator ----

    def check_regimen_against_reference(self, patient, regimen):
        """The forward chainer and reference_evaluator.judge_regimen agree on rejections, flags and points."""
        all_facts = kb.chain_regimen(patient, list(regimen))
        rejected, flag_labels = verdict_in_reference_format(all_facts)
        expected = reference_evaluator.judge_regimen(patient, regimen)
        self.assertEqual(rejected, set(expected["rejected"]))
        self.assertEqual(flag_labels, set(expected["flag_labels"]))
        if len(rejected) == 0:
            points, flag_count, dose_note = search.score_regimen(patient, regimen)
            self.assertEqual(points, expected["points"])
            self.assertEqual(flag_count, expected["flag_count"])
            self.assertEqual(dose_note, expected["dose_note"])

    def test_every_regimen_of_the_8_patients_agrees_with_reference(self):
        """Test 2, part 1: every complete regimen of every test patient."""
        for patient in PATIENTS:
            for regimen in all_regimens(patient):
                with self.subTest(patient=patient["name"], regimen=regimen):
                    self.check_regimen_against_reference(patient, regimen)

    def test_500_random_patients_agree_with_reference(self):
        """
        Test 2, part 2: 500 random patients (fixed seed). For each one, plan() gives the same results
        as reference_evaluator.plan_reference, which tries every regimen with plain loops.
        """
        for patient in random_patients(500):
            result = planner.plan(patient)
            expected = reference_evaluator.plan_reference(patient)
            for field in ["regimen_count", "invalid_count", "ranked", "winners",
                          "blocked_conditions", "states_generated", "full_tree_size"]:
                with self.subTest(patient=patient["name"], field=field):
                    self.assertEqual(result[field], expected[field])

    # ---- Test 3: the search compared with trying every combination ----

    def test_search_finds_exactly_the_valid_regimens(self):
        """
        Test 3: brute force (chain every complete regimen) finds the same valid regimens as the
        depth-first search, for the 8 test patients and 100 random ones. Pruning never loses a regimen.
        """
        for patient in PATIENTS + random_patients(100):
            brute_force_valid = set()
            for regimen in all_regimens(patient):
                if ("InvalidRegimen", patient["name"]) not in kb.chain_regimen(patient, list(regimen)):
                    brute_force_valid.add(regimen)
            with self.subTest(patient=patient["name"]):
                self.assertEqual(set(search.run_search(patient)["complete_regimens"]), brute_force_valid)

    # ---- Test 4: every rejection ----

    def test_every_reject_if_has_fact(self):
        """Test 4: for each of the 17 RejectIfHas facts, a tiny patient with that attribute gets the drug rejected."""
        self.assertEqual(len(kb_facts.REJECT_IF_HAS), 17)
        for drug, attribute in kb_facts.REJECT_IF_HAS:
            with self.subTest(drug=drug, attribute=attribute):
                patient = tiny_patient(drug, profile_for(attribute))
                self.assertIn(("Rejected", "Tiny", drug, attribute), kb.chain_regimen(patient, [drug]))

    def test_every_reject_if_pregnant_fact(self):
        """Test 4: for each of the 6 RejectIfPregnant facts, a pregnant tiny patient gets the drug rejected."""
        self.assertEqual(len(kb_facts.REJECT_IF_PREGNANT), 6)
        for drug in kb_facts.REJECT_IF_PREGNANT:
            with self.subTest(drug=drug):
                patient = tiny_patient(drug, {"pregnant": True})
                self.assertIn(("Rejected", "Tiny", drug, "Pregnancy"), kb.chain_regimen(patient, [drug]))

    def test_the_major_interaction(self):
        """Test 4: Warfarin with Ibuprofen (the only Major pair) rejects Warfarin."""
        patient = {"name": "Tiny", "needs": ["AtrialFibrillation", "ChronicPain"], "age": 50,
                   "pregnant": False, "allergies": [], "has": []}
        all_facts = kb.chain_regimen(patient, ["Warfarin", "Ibuprofen"])
        self.assertIn(("Rejected", "Tiny", "Warfarin", ("InteractionWith", "Ibuprofen")), all_facts)

    def test_allergy_to_every_drug(self):
        """Test 4: the allergy rule works for each of the 10 drugs."""
        for drugs in kb_facts.CONDITIONS.values():
            for drug in drugs:
                with self.subTest(drug=drug):
                    patient = tiny_patient(drug, {"allergies": [drug]})
                    self.assertIn(("Rejected", "Tiny", drug, "Allergy"), kb.chain_regimen(patient, [drug]))

    # ---- Test 5: every flag appears ----

    def test_all_28_flag_triggers_appear(self):
        """
        Test 5: across the valid regimens of the 8 test patients, all 28 flag triggers appear:
        17 FlagIfHas, 3 FlagIfPregnant, 7 Moderate interactions and 1 Apixaban dose note.
        """
        triggers = set()
        for drug, attribute in kb_facts.FLAG_IF_HAS:
            triggers.add(f"{drug}:{attribute}")
        for drug in kb_facts.FLAG_IF_PREGNANT:
            triggers.add(f"{drug}:Pregnancy")
        for first_drug, second_drug, severity in kb_facts.INTERACTIONS:
            if severity == "Moderate":
                triggers.add(f"{first_drug}+{second_drug}:Moderate")
        triggers.add("Apixaban:DoseNote")
        self.assertEqual(len(triggers), 28)

        seen = set()
        for patient in PATIENTS:
            for row in planner.plan(patient)["ranked"]:
                regimen = row[0]
                rejected, flag_labels = verdict_in_reference_format(kb.chain_regimen(patient, list(regimen)))
                seen = seen | flag_labels
        self.assertEqual(triggers - seen, set())

    # ---- Test 6: cut-off boundaries ----

    def check_boundary(self, field, below, at, attribute, present_at_cut_off):
        """
        Compare a value just below a cut-off with the value exactly at it.
        present_at_cut_off says whether the attribute is there AT the cut-off: True for a ">=" rule
        (it starts at the cut-off), False for a "<" rule (it stops just before the cut-off).
        """
        below_patient = dict(find_patient("Patient3"))
        below_patient[field] = below
        at_patient = dict(find_patient("Patient3"))
        at_patient[field] = at
        self.assertEqual(attribute in derived_attributes(below_patient), not present_at_cut_off)
        self.assertEqual(attribute in derived_attributes(at_patient), present_at_cut_off)

    def test_age_boundaries(self):
        """Test 6: age 64/65 for Elderly, and 79/80 for AgeAtLeast80."""
        self.check_boundary("age", 64, 65, "Elderly", True)
        self.check_boundary("age", 79, 80, "AgeAtLeast80", True)

    def test_egfr_boundaries(self):
        """Test 6: eGFR 29/30 (severe stops, moderate starts) and 44/45 (moderate stops)."""
        self.check_boundary("egfr", 29, 30, "SevereKidneyImpairment", False)
        self.check_boundary("egfr", 29, 30, "ModerateKidneyImpairment", True)
        self.check_boundary("egfr", 44, 45, "ModerateKidneyImpairment", False)

    def test_creatinine_boundary(self):
        """Test 6: creatinine 1.49/1.5 for HighCreatinine."""
        self.check_boundary("creatinine", 1.49, 1.5, "HighCreatinine", True)

    def test_weight_boundary(self):
        """Test 6: LowWeight at 60 kg (included) but not at 61 kg (a "<=" rule, so it is checked the other way round)."""
        at_60 = dict(find_patient("Patient3"))
        at_60["weight"] = 60
        at_61 = dict(find_patient("Patient3"))
        at_61["weight"] = 61
        self.assertIn("LowWeight", derived_attributes(at_60))
        self.assertNotIn("LowWeight", derived_attributes(at_61))

    # ---- Test 7: missing information (closed-world assumption) ----

    def test_missing_egfr_gives_no_kidney_attribute(self):
        """Test 7: with no eGFR recorded, the patient never gets a kidney attribute."""
        patient = dict(find_patient("Patient3b"))
        del patient["egfr"]
        attributes = derived_attributes(patient)
        self.assertNotIn("SevereKidneyImpairment", attributes)
        self.assertNotIn("ModerateKidneyImpairment", attributes)

    def test_missing_weight_gives_no_low_weight(self):
        """Test 7: with no weight recorded, the patient never gets LowWeight."""
        patient = dict(find_patient("Patient1"))
        del patient["weight"]
        self.assertNotIn("LowWeight", derived_attributes(patient))

    def test_missing_creatinine_gives_no_high_creatinine(self):
        """Test 7: with no creatinine recorded, the patient never gets HighCreatinine."""
        patient = dict(find_patient("Patient3"))
        del patient["creatinine"]
        self.assertNotIn("HighCreatinine", derived_attributes(patient))

    def test_missing_numbers_still_plan_and_print(self):
        """With weight, eGFR and creatinine all missing, the planner still plans and says they were not recorded."""
        patient = dict(find_patient("Patient3"))
        for field in ["weight", "egfr", "creatinine"]:
            del patient[field]
        self.assertGreater(len(planner.plan(patient)["ranked"]), 0)
        self.assertIn("weight not recorded, eGFR not recorded, creatinine not recorded", report_text(patient))

    # ---- Test 8: fact-base consistency ----

    def test_no_attribute_is_both_reject_and_flag(self):
        """Test 8: no drug has the same attribute under both RejectIfHas and FlagIfHas."""
        self.assertEqual(set(kb_facts.REJECT_IF_HAS) & set(kb_facts.FLAG_IF_HAS), set())

    def test_no_drug_is_both_reject_and_flag_for_pregnancy(self):
        """Test 8 (the same idea for pregnancy): no drug is both rejected and flagged for pregnancy."""
        self.assertEqual(set(kb_facts.REJECT_IF_PREGNANT) & set(kb_facts.FLAG_IF_PREGNANT), set())

    def test_no_interaction_pair_stored_twice(self):
        """Test 8: no interaction pair is stored twice, in either order."""
        pairs_seen = []
        for first_drug, second_drug, severity in kb_facts.INTERACTIONS:
            pair = {first_drug, second_drug}
            self.assertNotIn(pair, pairs_seen)
            pairs_seen.append(pair)

    def test_interacting_drugs_treat_different_conditions(self):
        """Test 8: both drugs in an interaction pair treat different conditions."""
        for first_drug, second_drug, severity in kb_facts.INTERACTIONS:
            with self.subTest(pair=(first_drug, second_drug)):
                self.assertNotEqual(condition_treated_by(first_drug), condition_treated_by(second_drug))

    def test_every_attribute_is_known(self):
        """Test 8: every attribute used by a fact is in TYPED_ATTRIBUTES or BUILT_ATTRIBUTES."""
        known_attributes = set(kb_facts.TYPED_ATTRIBUTES) | set(kb_facts.BUILT_ATTRIBUTES)
        for drug, attribute in kb_facts.REJECT_IF_HAS + kb_facts.FLAG_IF_HAS:
            with self.subTest(drug=drug, attribute=attribute):
                self.assertIn(attribute, known_attributes)
        for attribute in kb_facts.APIXABAN_DOSE_NOTE_ATTRIBUTES:
            self.assertIn(attribute, known_attributes)

    def test_every_drug_in_a_fact_is_one_of_the_10(self):
        """Test 8 (extra): every drug named in a fact is one of the 10 drugs in CONDITIONS."""
        all_drugs = set()
        for drugs in kb_facts.CONDITIONS.values():
            all_drugs = all_drugs | set(drugs)
        used_drugs = set(kb_facts.REJECT_IF_PREGNANT) | set(kb_facts.FLAG_IF_PREGNANT)
        for drug, attribute in kb_facts.REJECT_IF_HAS + kb_facts.FLAG_IF_HAS:
            used_drugs.add(drug)
        for first_drug, second_drug, severity in kb_facts.INTERACTIONS:
            used_drugs.add(first_drug)
            used_drugs.add(second_drug)
        self.assertEqual(used_drugs - all_drugs, set())

    # ---- run_demo.py ----

    def test_run_demo_summary(self):
        """run_demo.py shows the search numbers and every option with its points."""
        import run_demo
        text = "\n".join(run_demo.patient_summary(find_patient("Patient3")))
        self.assertIn("Search: 9 of 15 states generated (6 saved by pruning)", text)
        self.assertIn("Regimens: 8 complete, 5 not suitable, 3 safe", text)
        self.assertIn("1 *   Glipizide  Acetaminophen  Apixaban      1       1         no", text)
        blocked = "\n".join(run_demo.patient_summary(find_patient("Patient5b")))
        self.assertIn("NO COMPLETE PLAN: Pain has no suitable drug in the planner's list. A doctor needs to decide.",
                      blocked)


# ---------------------------------------------------------------------------
# Step 6: current medications
# ---------------------------------------------------------------------------

def example_patient(letter, needs, current_medications, age=50, pregnant=False):
    """One of the example patients A to F from SPEC section 9, test 11 (no lab numbers recorded)."""
    return {"name": "Patient" + letter, "needs": needs, "age": age, "pregnant": pregnant,
            "allergies": [], "has": [], "current_medications": current_medications}


PATIENT_A = example_patient("A", ["ChronicPain"], ["Warfarin"])
PATIENT_B = example_patient("B", ["Hypertension"], ["Simvastatin"])
PATIENT_C = example_patient("C", ["Hypertension", "ChronicPain"], ["Warfarin"], age=30, pregnant=True)
PATIENT_D = example_patient("D", ["Type2Diabetes"], ["Warfarin", "Ibuprofen"])
PATIENT_E = example_patient("E", ["Type2Diabetes"], ["Metformin"])
PATIENT_F = example_patient("F", ["ChronicPain"], ["Aspirin"])


def dead_end_reasons(result):
    """Every Rejected fact met during the search, as (drug, reason)."""
    reasons = set()
    for regimen, rejected_facts in result["dead_ends"]:
        for fact in rejected_facts:
            reasons.add((fact[2], fact[3]))
    return reasons


def warnings_for(patient):
    """The CurrentWarning facts the forward chainer concludes for the patient, as (drug, reason)."""
    warnings = set()
    for fact in kb.facts_named(kb.chain_regimen(patient, []), "CurrentWarning"):
        warnings.add((fact[2], fact[3]))
    return warnings


class TestStep6CurrentMedications(unittest.TestCase):
    """Step 6: current medications (rules F and G, the input check, the printout). SPEC section 9, test 11."""

    def test_patient_a_warfarin_and_pain(self):
        """A: Ibuprofen is rejected (Major with Warfarin); Acetaminophen is flagged (Moderate), 3 points."""
        result = planner.plan(PATIENT_A)
        self.assertEqual(result["ranked"], [(("Acetaminophen",), 3, 1, False)])
        self.assertIn(("Ibuprofen", ("InteractionWithCurrent", "Warfarin")), dead_end_reasons(result))
        self.assertEqual(warnings_for(PATIENT_A), set())

    def test_patient_b_simvastatin_and_blood_pressure(self):
        """B: Lisinopril has no concerns; Amlodipine is flagged (Moderate with Simvastatin)."""
        result = planner.plan(PATIENT_B)
        self.assertEqual(result["ranked"], [(("Lisinopril",), 0, 0, False), (("Amlodipine",), 3, 1, False)])
        self.assertEqual(result["winners"], [("Lisinopril",)])

    def test_patient_c_pregnant_and_warfarin(self):
        """
        C: a warning for Warfarin (pregnancy); Lisinopril and Ibuprofen rejected; the only option is
        Amlodipine + Acetaminophen with 2 pregnancy flags and 1 Moderate flag (1 + 1 + 3 = 5 points).
        """
        result = planner.plan(PATIENT_C)
        self.assertEqual(warnings_for(PATIENT_C), {("Warfarin", "Pregnancy")})
        self.assertEqual(result["ranked"], [(("Amlodipine", "Acetaminophen"), 5, 3, False)])
        reasons = dead_end_reasons(result)
        self.assertIn(("Lisinopril", "Pregnancy"), reasons)

    def test_patient_c_warning_does_not_reject_options(self):
        """A warning about a medicine already taken never makes the regimen invalid."""
        all_facts = kb.chain_regimen(PATIENT_C, ["Amlodipine", "Acetaminophen"])
        self.assertIn(("CurrentWarning", "PatientC", "Warfarin", "Pregnancy"), all_facts)
        self.assertNotIn(("InvalidRegimen", "PatientC"), all_facts)

    def test_patient_d_two_current_medications(self):
        """D: a warning for Warfarin with Ibuprofen (Major); Metformin and Glipizide are both flagged, so tied."""
        result = planner.plan(PATIENT_D)
        self.assertEqual(warnings_for(PATIENT_D), {("Warfarin", ("InteractionWith", "Ibuprofen"))})
        self.assertEqual(result["ranked"], [(("Glipizide",), 3, 1, False), (("Metformin",), 3, 1, False)])
        self.assertEqual(result["winners"], [("Glipizide",), ("Metformin",)])

    def test_patient_e_already_treated(self):
        """E: already takes Metformin for diabetes, so diabetes is not planned and nothing else is left (decision 2)."""
        result = planner.plan(PATIENT_E)
        self.assertTrue(result["nothing_to_plan"])
        self.assertEqual(result["already_treated"], {"Type2Diabetes": ["Metformin"]})
        text = report_text(PATIENT_E)
        self.assertIn("Note: Diabetes is not planned, because the patient already takes Metformin for it.", text)
        self.assertIn("To plan a replacement instead, enter the patient again without Metformin", text)
        self.assertIn("Nothing else to plan: every condition asked for is already treated.", text)

    def test_patient_e_with_pain_plans_only_pain(self):
        """E with ChronicPain as well: only pain is planned, and it is still checked against Metformin."""
        patient = dict(PATIENT_E, needs=["Type2Diabetes", "ChronicPain"])
        result = planner.plan(patient)
        self.assertEqual(result["planned_needs"], ["ChronicPain"])
        self.assertEqual(result["ranked"], [(("Acetaminophen",), 0, 0, False), (("Ibuprofen",), 0, 0, False)])

    def test_already_taken_drug_is_never_suggested_again(self):
        """
        The case found while building step 7: the patient takes Warfarin and asks for heart rhythm too.
        Heart rhythm is not planned, so neither Warfarin again nor Apixaban on top of it is suggested.
        """
        patient = dict(find_patient("Patient3"), current_medications=["Warfarin"])
        result = planner.plan(patient)
        self.assertEqual(result["planned_needs"], ["Type2Diabetes", "ChronicPain"])
        for regimen, points, flag_count, dose_note in result["ranked"]:
            self.assertNotIn("Warfarin", regimen)
            self.assertNotIn("Apixaban", regimen)
        self.assertIn("Note: Heart rhythm is not planned, because the patient already takes Warfarin for it.",
                      report_text(patient))

    def test_warning_still_shown_when_nothing_to_plan(self):
        """Pregnant, takes Warfarin, asks only for heart rhythm: nothing to plan, but the WARNING is still shown."""
        patient = example_patient("W", ["AtrialFibrillation"], ["Warfarin"], age=30, pregnant=True)
        text = report_text(patient)
        self.assertIn("WARNING  Warfarin (already taken) is not suitable for this patient: pregnancy.", text)
        self.assertIn("Nothing else to plan", text)

    def test_patient_f_unknown_drug(self):
        """F: Aspirin is not one of the 10 drugs, so no plan is made."""
        result = planner.plan(PATIENT_F)
        self.assertEqual(list(result.keys()), ["message"])
        self.assertEqual(result["message"],
                         "The Prescription Planner only knows these 10 drugs: Lisinopril, Amlodipine, "
                         "Atorvastatin, Simvastatin, Warfarin, Apixaban, Metformin, Glipizide, Ibuprofen, "
                         "Acetaminophen. \"Aspirin\" is not one of them, so no plan was made.")

    def test_more_warning_rules(self):
        """Rules G1 and G2: allergy to a current medicine, and a condition that rules it out."""
        allergic = example_patient("G", ["ChronicPain"], ["Warfarin"])
        allergic["allergies"] = ["Warfarin"]
        self.assertIn(("Warfarin", "Allergy"), warnings_for(allergic))
        kidney = example_patient("H", ["ChronicPain"], ["Metformin"])
        kidney["egfr"] = 40
        self.assertIn(("Metformin", "ModerateKidneyImpairment"), warnings_for(kidney))

    def test_no_current_medications_changes_nothing(self):
        """An empty list gives the same plan as no field at all, for all 8 test patients."""
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                with_empty_list = dict(patient, current_medications=[])
                self.assertEqual(planner.plan(with_empty_list)["ranked"], EXPECTED[patient["name"]]["ranked"])

    def test_printout_warning_and_notes(self):
        """C's printout: the medicines already taken, the WARNING, the note, and the already-taken pair."""
        text = " ".join(report_text(PATIENT_C).split())
        self.assertIn("Already takes: Warfarin", text)
        self.assertIn("WARNING Warfarin (already taken) is not suitable for this patient: pregnancy.", text)
        self.assertIn("A doctor should review it.", text)
        self.assertNotIn("The planner cannot change it", text)
        self.assertIn("serious problems only. Other cautions about them are not shown.", text)
        self.assertIn("Ibuprofen + already-taken Warfarin: must not be taken together", text)
        self.assertIn("Acetaminophen: use with care, because it can affect already-taken Warfarin and the patient "
                      "is pregnant.", text)

    def test_printout_without_current_medications_has_no_note(self):
        """A patient who takes nothing gets no "Already takes" line and no note."""
        text = report_text(find_patient("Patient3"))
        self.assertNotIn("Already takes", text)
        self.assertNotIn("WARNING", text)

    def test_why_with_a_current_medication(self):
        """why(): Ibuprofen is rejected for A (rule F3); Warfarin for C gets the pregnancy warning (rule G3)."""
        self.assertEqual(planner.why(PATIENT_A, "Ibuprofen")["rejected_reasons"],
                         [("InteractionWithCurrent", "Warfarin")])
        warfarin = planner.why(PATIENT_C, "Warfarin")
        self.assertEqual(warfarin["warning_reasons"], ["Pregnancy"])
        self.assertEqual(warfarin["rejected_reasons"], [])   # it is already taken, not chosen

    def test_backward_agrees_with_forward_for_current_medications(self):
        """For patients A to E, every candidate drug: why() finds what the forward chainer concludes."""
        for patient in [PATIENT_A, PATIENT_B, PATIENT_C, PATIENT_D, PATIENT_E]:
            for drugs in reference_evaluator.candidate_lists(patient):
                for drug in drugs:
                    if drug in patient["current_medications"]:
                        continue
                    with self.subTest(patient=patient["name"], drug=drug):
                        result = planner.why(patient, drug, [drug])
                        rejected, flagged, others_rejected, others_flagged, dose_note = \
                            forward_verdict_for_drug(patient, (drug,), drug)
                        self.assertEqual(set(result["rejected_reasons"]), rejected)
                        self.assertEqual(set(result["flagged_reasons"]), flagged)


# ---------------------------------------------------------------------------
# Step 7: question-and-answer entry
# ---------------------------------------------------------------------------

def typed_answers(answers):
    """
    Pretend to be the keyboard: each call returns the next answer from the list.
    The question shown is ignored, because the tests only check the answers and the messages.
    """
    remaining = list(answers)

    def read_line(question):
        return remaining.pop(0)
    return read_line


def run_entry(answers):
    """Run enter_patient with typed answers. Returns the patient and every line the program showed."""
    shown = []
    patient = enter_patient.enter_patient(typed_answers(answers), shown.append)
    return patient, shown


# Patient3 typed in: 4 = Diabetes, 5 = Pain, 3 = Heart rhythm (the order of CONDITIONS).
PATIENT3_ANSWERS = ["Patient3", "58", "80", "40", "1.9", "no", "4 5 3", "", "", ""]


class TestStep7PatientEntry(unittest.TestCase):
    """Step 7: the question-and-answer entry (SPEC section 12, decision 7)."""

    def test_entering_patient3_gives_the_same_plan(self):
        """Typing in Patient3's profile gives the same plan as the answer key."""
        patient, shown = run_entry(PATIENT3_ANSWERS)
        self.assertEqual(patient["needs"], ["Type2Diabetes", "ChronicPain", "AtrialFibrillation"])
        self.assertEqual(patient["egfr"], 40)
        self.assertEqual(patient["creatinine"], 1.9)
        self.assertEqual(planner.plan(patient)["ranked"], EXPECTED["Patient3"]["ranked"])

    def test_wrong_answers_get_an_example_and_are_asked_again(self):
        """Each wrong answer gets a friendly message with an example, then the question again."""
        answers = ["", "Patient9", "fifty", "58", "eighty", "80", "-5", "40", "1.9",
                   "maybe", "n", "4 9", "4 4", "4, 5,3", "12", "", "", ""]
        patient, shown = run_entry(answers)
        self.assertEqual(patient["name"], "Patient9")
        self.assertEqual(patient["age"], 58)
        self.assertEqual(patient["weight"], 80)
        self.assertEqual(patient["egfr"], 40)
        self.assertFalse(patient["pregnant"])
        self.assertEqual(patient["needs"], ["Type2Diabetes", "ChronicPain", "AtrialFibrillation"])
        self.assertEqual(patient["has"], [])
        self.assertIn("  Please type a name or label, for example Patient9.", shown)
        self.assertIn("  Please type the age as a whole number from 18 to 130, for example 58.", shown)
        self.assertIn("  Please type the weight as a number from 20 to 500, for example 72.", shown)
        self.assertIn("  Please type eGFR as a number from 0 to 200, for example 60.", shown)
        self.assertIn("  Please type yes or no.", shown)
        self.assertIn("  Please type numbers from the list, each once, for example 4 5 3.", shown)

    def test_required_questions_are_marked(self):
        """Only the required questions say (required); the top line explains how to leave the others empty."""
        questions = []
        answers = list(PATIENT3_ANSWERS)

        def read_line(question):
            questions.append(question)
            return answers.pop(0)
        shown = []
        enter_patient.enter_patient(read_line, shown.append)
        self.assertIn("Questions marked (required) must be answered. You can leave the others empty: press Enter.",
                      shown)
        self.assertEqual(questions, [
            "Patient name or label (required): ",
            "Age in years (required): ",
            "Weight in kg: ",
            "eGFR: ",
            "Creatinine in mg/dL: ",
            "Is the patient pregnant? (required, yes or no): ",
            "Type the numbers, in the order to plan them (required): ",
            "Type the numbers: ",
            "Type the numbers: ",
            "Type the numbers: ",
        ])

    def test_skipped_numbers_are_left_out(self):
        """Closed world: a skipped number is not in the profile at all (not guessed, not zero)."""
        patient, shown = run_entry(["Patient9", "58", "", "", "", "no", "5", "", "", ""])
        self.assertNotIn("weight", patient)
        self.assertNotIn("egfr", patient)
        self.assertNotIn("creatinine", patient)
        self.assertIn("weight not recorded", report_text(patient))

    def test_choices_for_attributes_allergies_and_current_medications(self):
        """Numbered lists: existing conditions, allergies and medicines already taken."""
        # Existing conditions 3 and 10 = ChronicKidneyDisease, ModerateLiverImpairment (order of TYPED_ATTRIBUTES).
        # Allergy 9 = Ibuprofen. Already takes 5 = Warfarin (order of CONDITIONS).
        patient, shown = run_entry(["Patient9", "70", "", "", "", "yes", "4", "3,10", "9", "5"])
        self.assertTrue(patient["pregnant"])
        self.assertEqual(patient["has"], ["ChronicKidneyDisease", "ModerateLiverImpairment"])
        self.assertEqual(patient["allergies"], ["Ibuprofen"])
        self.assertEqual(patient["current_medications"], ["Warfarin"])

    def test_under_18_typing_mistake(self):
        """Under 18: the adults-only message, then the corrected age is accepted."""
        patient, shown = run_entry(["Patient9", "15", "58", "", "", "", "no", "5", "", "", ""])
        self.assertEqual(patient["age"], 58)
        self.assertIn("  The Prescription Planner is designed for adults. "
                      "This patient (age 15) is outside what it covers, so no plan was made.", shown)

    def test_under_18_stop(self):
        """Under 18, then Enter: the entry stops and no plan is made."""
        patient, shown = run_entry(["Patient9", "15", ""])
        self.assertIsNone(patient)
        self.assertIn("No plan was made.", shown)


class TestDoseCheckWithMissingNumbers(unittest.TestCase):
    """SPEC section 12, decision 14: the Apixaban dose check when weight or creatinine is not recorded."""

    def test_reminder_when_missing_weight_could_matter(self):
        """Patient3 without a weight: creatinine 1.9 is already one of the three, so the weight could make two."""
        patient = dict(find_patient("Patient3"))
        del patient["weight"]
        text = " ".join(report_text(patient).split())
        self.assertIn("Apixaban: Weight was not recorded. Please check it: a lower dose may be needed if the patient "
                      "weighs 60 kg or less, because creatinine is already 1.5 or higher (1.9).", text)

    def test_reminder_when_both_numbers_are_missing(self):
        """Age 82, weight and creatinine missing: either one would make two of three, so they are joined with "or"."""
        patient = dict(find_patient("Patient1"))
        del patient["weight"]
        del patient["creatinine"]
        text = " ".join(report_text(patient).split())
        self.assertIn("Weight and creatinine were not recorded. Please check them: a lower dose may be needed "
                      "if the patient weighs 60 kg or less or has creatinine 1.5 or higher, because the patient "
                      "is already 80 or older (age 82).", text)


class TestSeparatorLines(unittest.TestCase):
    """The "=" and "-" lines are always exactly as long as the longest line of text in the printout."""

    def check_separators(self, text):
        """Every separator line has the same length as the longest line in the text."""
        lines = text.split("\n")
        longest = 0
        for line in lines:
            longest = max(longest, len(line))
        separators = []
        for line in lines:
            if line != "" and (set(line) == {"="} or set(line) == {"-"}) and len(line) > 10:
                separators.append(line)
        self.assertGreater(len(separators), 0)
        for line in separators:
            self.assertEqual(len(line), longest)

    def test_plans_of_the_8_patients(self):
        """All 8 test patients, including Patient1's wide table."""
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.check_separators(report_text(patient))

    def test_plans_with_current_medications_and_messages(self):
        """Long note lines (current medications) and long messages (unknown drug) are covered too."""
        for patient in [PATIENT_C, PATIENT_D, PATIENT_E, PATIENT_F]:
            with self.subTest(patient=patient["name"]):
                self.check_separators(report_text(patient))

    def test_run_demo_summaries(self):
        """run_demo.py's summary for each test patient."""
        import run_demo
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.check_separators("\n".join(run_demo.patient_summary(patient)))

    def test_no_reminder_when_missing_weight_cannot_matter(self):
        """Age 58 and creatinine 1.0: even a low weight would make only one of the three, so no reminder."""
        patient = dict(find_patient("Patient3"), creatinine=1.0)
        del patient["weight"]
        self.assertNotIn("Weight was not recorded", report_text(patient))

    def test_no_reminder_when_everything_is_recorded(self):
        """Patient3 with every number recorded: only one of the three is true, so nothing to check."""
        self.assertNotIn("was not recorded", report_text(find_patient("Patient3")))

    def test_reminder_does_not_change_the_plan(self):
        """The reminder is printout only: the ranking stays the same as with the weight recorded."""
        patient = dict(find_patient("Patient3"))
        del patient["weight"]
        self.assertEqual(planner.plan(patient)["ranked"], EXPECTED["Patient3"]["ranked"])


class TestEgfrInputCheck(unittest.TestCase):
    """SPEC section 12, decision 17: eGFR must be from 0 to 200; above 150 the user is warned."""

    def test_entry_refuses_out_of_range_and_text(self):
        """In enter_patient.py: 400, -5 and text are refused, then 40 is accepted."""
        patient, shown = run_entry(["Patient9", "58", "", "400", "-5", "forty", "40", "", "no", "5", "", "", ""])
        self.assertEqual(patient["egfr"], 40)
        self.assertEqual(shown.count("  Please type eGFR as a number from 0 to 200, for example 60."), 3)

    def test_entry_accepts_above_150_without_a_question(self):
        """180 is inside 0 to 200, so it is accepted directly; the report notes it (decision 27)."""
        patient, shown = run_entry(["Patient9", "58", "", "180", "", "no", "5", "", "", ""])
        self.assertEqual(patient["egfr"], 180)
        self.assertNotIn("Is it correct?", " ".join(shown))
        self.assertIn("Note: an eGFR of 180 is unusually high (above 150). Please check it is not a typing mistake.",
                      planner.patient_report(patient))

    def test_plan_refuses_out_of_range_egfr(self):
        """A patient written as a dictionary with eGFR 400 gets the message and no plan."""
        result = planner.plan(dict(find_patient("Patient3"), egfr=400))
        self.assertEqual(result["message"],
                         "The eGFR must be a number from 0 to 200. This patient's eGFR was entered as 400, "
                         "so no plan was made.")

    def test_printout_note_above_150(self):
        """A dictionary patient with eGFR 180 is planned, with a note to check it. 200 and 0 are allowed."""
        self.assertIn("Note: an eGFR of 180 is unusually high (above 150). Please check it is not a typing mistake.",
                      report_text(dict(find_patient("Patient3"), egfr=180)))
        self.assertIsNone(planner.plan(dict(find_patient("Patient3"), egfr=200))["message"])
        self.assertIsNone(planner.plan(dict(find_patient("Patient3"), egfr=0))["message"])


class TestPlainExplanation(unittest.TestCase):
    """SPEC section 12, decision 18: explain() gives the answer and the reason in plain words, short."""

    def explain_flat(self, patient, drug, regimen=None):
        """explain(), with line breaks and extra spaces removed, so the tests do not depend on line wrapping."""
        return " ".join(planner.explain(patient, drug, regimen).split())

    def test_not_suitable_reason_on_one_line(self):
        """Metformin for Patient3: the answer and the reason together, nothing more."""
        self.assertEqual(planner.explain(find_patient("Patient3"), "Metformin"),
                         "Metformin is NOT SUITABLE for Patient3: reduced kidney function (eGFR 40, between 30 and 44).")

    def test_no_code_words(self):
        """The plain explanation has none of the trace words, rule names or KB names."""
        for patient in PATIENTS:
            for drugs in reference_evaluator.candidate_lists(patient):
                for drug in drugs:
                    text = planner.explain(patient, drug)
                    for word in ["Sub-goal", "Goal:", "Try rule", "Rejected(", "InteractionWith",
                                 "ModerateKidneyImpairment", "ActiveLiverDisease", "AgeAtLeast80"]:
                        with self.subTest(patient=patient["name"], drug=drug, word=word):
                            self.assertNotIn(word, text)

    def test_caution(self):
        """Glipizide for Patient3 can be used, with a kidney caution."""
        self.assertEqual(self.explain_flat(find_patient("Patient3"), "Glipizide", ["Glipizide", "Acetaminophen", "Apixaban"]),
                         "Glipizide CAN BE USED for Patient3, with 1 caution: the patient has reduced kidney function "
                         "(eGFR 40, between 30 and 44). Use with care.")

    def test_interaction_from_both_sides(self):
        """Warfarin with Ibuprofen: asking about either drug says they must not be taken together."""
        regimen = ["Glipizide", "Ibuprofen", "Warfarin"]
        patient = find_patient("Patient3")
        self.assertEqual(self.explain_flat(patient, "Warfarin", regimen),
                         "Warfarin is NOT SUITABLE together with Ibuprofen: serious drug interaction, "
                         "they must not be taken together.")
        self.assertIn("Ibuprofen is NOT SUITABLE together with Warfarin", self.explain_flat(patient, "Ibuprofen", regimen))

    def test_typed_condition_and_pregnancy(self):
        """A typed-in condition (Patient4) and pregnancy (Patient6) are said in plain words."""
        self.assertEqual(planner.explain(find_patient("Patient4"), "Metformin"),
                         "Metformin is NOT SUITABLE for Patient4: moderate liver impairment.")
        self.assertEqual(planner.explain(find_patient("Patient6"), "Lisinopril"),
                         "Lisinopril is NOT SUITABLE for Patient6: pregnancy.")
        self.assertEqual(planner.explain(find_patient("Patient6"), "Metformin"),
                         "Metformin CAN BE USED for Patient6. No problems were found.")

    def test_dose_note(self):
        """Apixaban for Patient1: can be used, with the dose reason in plain words."""
        self.assertEqual(self.explain_flat(find_patient("Patient1"), "Apixaban"),
                         "Apixaban CAN BE USED for Patient1. No problems were found. Check the dose: a lower dose "
                         "may be needed, because the patient is 80 or older (age 82) and weighs 60 kg or less (58 kg).")

    def test_medicine_already_taken(self):
        """A drug the patient already takes: the warning (patient C) or no serious problem (patient A)."""
        self.assertIn("WARNING: it is not suitable for this patient: pregnancy. A doctor should review it.",
                      self.explain_flat(PATIENT_C, "Warfarin"))
        self.assertIn("No serious problem was found with it.", self.explain_flat(PATIENT_A, "Warfarin"))
        self.assertIn("Ibuprofen is NOT SUITABLE together with already-taken Warfarin",
                      self.explain_flat(PATIENT_A, "Ibuprofen"))


class TestWhyThisOptionAndSearchSteps(unittest.TestCase):
    """SPEC section 12, decision 19: why the recommended option, how the search went, each problem once."""

    def section_flat(self, lines):
        """Lines joined, with line breaks and extra spaces removed, so the tests do not depend on wrapping."""
        return " ".join(" ".join(lines).split())

    def test_why_this_option_patient3(self):
        """Each condition: why its drug was picked over the other one."""
        patient = find_patient("Patient3")
        text = self.section_flat(planner.why_this_option_lines(patient, planner.plan(patient)))
        self.assertIn("Diabetes: Glipizide, because Metformin is not suitable: reduced kidney function", text)
        self.assertIn("Pain: Acetaminophen, because Ibuprofen has more concerns:", text)
        self.assertIn("Heart rhythm: Apixaban, because Warfarin has more concerns: it can affect Acetaminophen and "
                      "Glipizide.", text)

    def test_why_this_option_tie(self):
        """Patient1: Atorvastatin and Simvastatin are tied, and it says so."""
        patient = find_patient("Patient1")
        text = self.section_flat(planner.why_this_option_lines(patient, planner.plan(patient)))
        self.assertIn("Cholesterol: Atorvastatin, because Simvastatin is just as good (a tie; both are listed in the "
                      "table).", text)

    def test_search_steps_patient3(self):
        """The 8 steps of Patient3's search, in order, with what the forward chainer said at each."""
        patient = find_patient("Patient3")
        result = planner.plan(patient)
        self.assertEqual(len(result["steps"]), result["states_generated"] - 1)   # every state except the start
        text = self.section_flat(planner.search_steps_lines(patient, result))
        self.assertIn("1. Diabetes: try Metformin -> not suitable: reduced kidney function", text)
        self.assertIn("4. Heart rhythm: try Warfarin -> not suitable: serious drug interaction with Ibuprofen", text)
        self.assertIn("8. Heart rhythm: try Apixaban -> complete option found", text)
        self.assertIn("Result: 3 safe options found. The search made 9 of the 15 possible states", text)

    def test_search_steps_match_the_search(self):
        """For all 8 patients: one step per state (except the start), and the complete steps are the safe regimens."""
        for patient in PATIENTS:
            result = planner.plan(patient)
            complete = []
            for attempt, outcome, rejected_facts in result["steps"]:
                if outcome == "complete":
                    complete.append(attempt)
            with self.subTest(patient=patient["name"]):
                self.assertEqual(len(result["steps"]), result["states_generated"] - 1)
                ranked_regimens = []
                for row in result["ranked"]:
                    ranked_regimens.append(row[0])
                self.assertEqual(sorted(complete), sorted(ranked_regimens))

    def test_each_problem_once_with_combinations(self):
        """Patient3: Metformin ruled out 4 combinations, Warfarin + Ibuprofen ruled out 1."""
        patient = find_patient("Patient3")
        text = self.section_flat(planner.problem_summary_lines(patient, planner.plan(patient)))
        self.assertIn("Metformin: reduced kidney function (eGFR 40, between 30 and 44). This ruled out 4 combinations.",
                      text)
        self.assertIn("Warfarin + Ibuprofen: must not be taken together (serious drug interaction). "
                      "This ruled out 1 combination.", text)


class TestPlainExplanationVerdict(unittest.TestCase):
    """explain() says NOT SUITABLE exactly when the forward chainer rejects the drug."""

    def test_verdict_agrees_with_forward_chainer(self):
        """For every single drug and pair of the 8 patients: NOT SUITABLE exactly when the forward chainer rejects it."""
        for patient in PATIENTS:
            for regimen in single_drugs_and_pairs(patient):
                for drug in regimen:
                    rejected, flagged, others_rejected, others_flagged, dose_note = \
                        forward_verdict_for_drug(patient, regimen, drug)
                    text = planner.explain(patient, drug, list(regimen))
                    with self.subTest(patient=patient["name"], regimen=regimen, drug=drug):
                        is_not_suitable = len(rejected) > 0 or len(others_rejected) > 0
                        self.assertEqual("NOT SUITABLE" in text, is_not_suitable)


class TestRunDemoModes(unittest.TestCase):
    """SPEC section 12, decision 19: run_demo.py shows an overview, one patient in detail, or the steps."""

    def run_demo_main(self, arguments):
        """Run run_demo.main and return everything it printed."""
        import contextlib
        import io
        import run_demo
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            run_demo.main(arguments)
        return printed.getvalue()

    def flat(self, text):
        """The text with line breaks and extra spaces removed, so the tests do not depend on line wrapping."""
        return " ".join(text.split())

    def test_overview(self):
        """No arguments: a blank line first, one row per test patient, then how to see more."""
        text = self.run_demo_main([])
        self.assertTrue(text.startswith("\n"))
        self.assertIn("Patient3   3           9 of 15      3 of 8         Glipizide + Acetaminophen + Apixaban", text)
        self.assertIn("4 tied options (see the details)", text)
        self.assertIn("None (Pain blocked)", text)
        self.assertIn("To see one patient in detail:      python run_demo.py Patient3", text)
        self.assertIn("To see the steps for one patient:  python run_demo.py steps Patient3", text)
        self.assertLess(len(text.split("\n")), 22)

    def test_steps_without_a_name_shows_the_overview(self):
        """"steps" alone shows the overview, which says how to use it."""
        self.assertEqual(self.run_demo_main(["steps"]), self.run_demo_main([]))

    def test_one_patient(self):
        """A patient's name (any capitals): the details and the two sections, but not the search steps."""
        text = self.run_demo_main(["patient3"])
        self.assertTrue(text.startswith("\n"))
        self.assertIn("Search: 9 of 15 states generated (6 saved by pruning)", text)
        self.assertIn("Why this is the best option (Glipizide + Acetaminophen + Apixaban):", text)
        self.assertIn("Cautions for the best option (Glipizide + Acetaminophen + Apixaban):", text)
        self.assertIn("Why some drugs are not suitable:", text)
        self.assertNotIn("PART 1", text)
        self.assertNotIn("try Metformin", text)

    def test_each_problem_once(self):
        """Patient1: Warfarin + Ibuprofen is in 8 dead ends, but it is explained once."""
        text = self.flat(self.run_demo_main(["Patient1"]))
        self.assertEqual(text.count("Warfarin + Ibuprofen: must not be taken together"), 1)
        self.assertIn("This ruled out 8 combinations.", text)

    def test_steps_patient3(self):
        """steps Patient3: part 1 is the search, part 2 explains Metformin and Warfarin, each once."""
        text = self.flat(self.run_demo_main(["steps", "Patient3"]))
        self.assertIn("PART 1: HOW THE PLANNER SEARCHED", text)
        self.assertIn("1. Diabetes: try Metformin -> not suitable: reduced kidney function", text)
        self.assertIn("PART 2: HOW THE PLANNER EXPLAINS EACH DRUG THAT IS NOT SUITABLE (backward chaining)", text)
        self.assertEqual(text.count("Question: why is Metformin not suitable for Patient3?"), 1)
        self.assertEqual(text.count("Question: why is Warfarin not suitable for Patient3?"), 1)
        self.assertIn("Reduced kidney function? (eGFR 30 to 44) -> YES, eGFR is 40", text)
        self.assertIn("Serious interaction with the other chosen drugs? -> YES, with Ibuprofen", text)
        self.assertNotIn("Sub-goal", text)

    def test_steps_every_patient(self):
        """steps works for every test patient, and each not-suitable drug is explained exactly once."""
        import run_demo
        for patient in PATIENTS:
            text = self.flat("\n".join(run_demo.steps_lines(patient)))
            result = planner.plan(patient)
            drugs = []
            for drug, regimen in planner.drugs_to_explain(result):
                drugs.append(drug)
            with self.subTest(patient=patient["name"]):
                self.assertGreater(len(drugs), 0)
                for drug in drugs:
                    self.assertEqual(text.count(f"Question: why is {drug} not suitable"), 1)
                self.assertEqual(text.count("Answer: "), len(drugs))

    def test_unknown_name(self):
        """An unknown name gets the list of names."""
        self.assertIn("There is no test patient called Patient9.", self.run_demo_main(["Patient9"]))
        self.assertIn("There is no test patient called Patient9.", self.run_demo_main(["steps", "Patient9"]))


class TestBackwardStepsAgreeWithWhy(unittest.TestCase):
    """The plain backward-chaining steps find the same reasons as why(): every YES matches a real reason."""

    def test_yes_answers_match_the_reasons(self):
        """For every not-suitable drug of the 8 patients: the plain steps' answer is the same as explain()."""
        for patient in PATIENTS:
            result = planner.plan(patient)
            for drug, regimen in planner.drugs_to_explain(result):
                lines = planner.backward_steps_lines(patient, drug, regimen)
                # The answer starts at the line beginning with "Answer: " and may continue on the next lines.
                answer_start = 0
                for position, line in enumerate(lines):
                    if line.startswith("Answer: "):
                        answer_start = position
                answer = " ".join(" ".join(lines[answer_start:]).split())
                with self.subTest(patient=patient["name"], drug=drug):
                    self.assertEqual(answer, "Answer: " + " ".join(planner.explain(patient, drug, regimen).split()))
                    self.assertIn("YES", " ".join(lines))


class TestPatientReport(unittest.TestCase):
    """SPEC section 12, decision 20: one report for run_demo.py and enter_patient.py."""

    def flat(self, lines):
        """Lines joined, with line breaks and extra spaces removed, so the tests do not depend on wrapping."""
        return " ".join(" ".join(lines).split())

    def test_cautions_for_the_best_option_only(self):
        """Patient1: only the best option's drugs, said like a person would, with the dose note in Apixaban's row."""
        text = self.flat(planner.patient_report(find_patient("Patient1")))
        self.assertIn("Cautions for the best option (Lisinopril + Atorvastatin + Apixaban + Glipizide + Acetaminophen): "
                      "Atorvastatin: use with care, because the patient is 65 or older (age 82). "
                      "Apixaban: a lower dose may be needed, because the patient is 80 or older (age 82) and weighs "
                      "60 kg or less (58 kg). "
                      "Glipizide: use with care, because the patient is 65 or older (age 82).", text)
        self.assertNotIn("Simvastatin: use with care", text)   # Simvastatin is not in the best option

    def test_patient_is_said_once(self):
        """Two reasons for one drug: "the patient" is said once."""
        patient = dict(find_patient("Patient3"), age=82)
        text = self.flat(planner.patient_report(patient))
        self.assertIn("Glipizide: use with care, because the patient is 65 or older (age 82) and has reduced kidney "
                      "function (eGFR 40, between 30 and 44).", text)

    def test_no_cautions(self):
        """A patient whose best option has no cautions gets "none"."""
        patient = {"name": "Healthy", "needs": ["ChronicPain"], "age": 40, "pregnant": False,
                   "allergies": [], "has": []}
        self.assertIn("Cautions for the best option (Acetaminophen): none.", planner.patient_report(patient))

    def test_same_report_in_demo_and_entry(self):
        """run_demo.py's detail view is exactly planner.patient_report."""
        import run_demo
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.assertEqual(run_demo.patient_summary(patient), planner.patient_report(patient))

    def test_one_line_about_the_order(self):
        """Only "Options are listed from fewest to most concerns." (the unclear second line is gone everywhere)."""
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.assertNotIn("A concern about two drugs", report_text(patient))

    def test_entry_flow(self):
        """enter_patient.main: the questions, the report, then "Show the steps?" (and no "Explain a drug?")."""
        answers = list(PATIENT3_ANSWERS) + ["yes"]

        def read_line(question):
            return answers.pop(0)
        shown = []
        enter_patient.main(read_line, shown.append)
        text = " ".join(" ".join(shown).split())
        self.assertIn("Cautions for the best option (Glipizide + Acetaminophen + Apixaban):", text)
        self.assertIn("PART 1: HOW THE PLANNER SEARCHED", text)
        self.assertIn("PART 2: HOW THE PLANNER EXPLAINS EACH DRUG THAT IS NOT SUITABLE", text)
        self.assertNotIn("Explain a drug?", text)
        self.assertEqual(answers, [])


class TestReportTableLimit(unittest.TestCase):
    """SPEC section 12, decision 22: the report's table shows at most 10 options, and says how many more there are."""

    def test_patient1_shows_10_of_24(self):
        """Patient1 has 24 safe options: the best 10 are shown, then a line says 14 are not shown."""
        text = "\n".join(planner.patient_report(find_patient("Patient1")))
        self.assertIn("Showing the best 10 of 24 safe options. The other 14 have more concerns and are not shown.", text)
        self.assertIn("\n10    Amlodipine", text)
        self.assertNotIn("\n11    ", text)

    def test_short_tables_are_complete(self):
        """Patient3 has 3 safe options: all are shown, with no extra line."""
        text = "\n".join(planner.patient_report(find_patient("Patient3")))
        self.assertNotIn("Showing the best", text)
        self.assertIn("\n3     Glipizide  Acetaminophen  Warfarin", text)

    def test_ties_are_never_cut(self):
        """If more options are tied for best than the limit, all of them are shown."""
        result = {"ranked": [], "winners": []}
        for number in range(12):
            regimen = (f"Drug{number}",)
            result["ranked"].append((regimen, 1, 1, False))
            result["winners"].append(regimen)
        lines = planner.ranked_table(["ChronicPain"], result)
        self.assertEqual(len(lines), 13)   # the header and all 12 tied options


class TestUnrealNumbers(unittest.TestCase):
    """SPEC section 12, decision 23: nan, inf and huge numbers are not real measurements."""

    def test_read_number(self):
        """nan, inf and 1e400 count as "not a number"; ordinary numbers still work."""
        for text in ["nan", "NaN", "inf", "-inf", "infinity", "1e400"]:
            with self.subTest(text=text):
                self.assertIsNone(enter_patient.read_number(text))
        self.assertEqual(enter_patient.read_number("58"), 58)
        self.assertEqual(enter_patient.read_number("1.9"), 1.9)

    def test_typed_unreal_numbers_are_asked_again(self):
        """For age, weight, eGFR and creatinine: nan, inf and 1e400 get the existing message and the question again."""
        bad = ["nan", "inf", "1e400"]
        answers = (["Patient9"] + bad + ["58"] + bad + ["80"] + bad + ["40"] + bad + ["1.9"]
                   + ["no", "5", "", "", ""])
        patient, shown = run_entry(answers)
        self.assertEqual((patient["age"], patient["weight"], patient["egfr"], patient["creatinine"]), (58, 80, 40, 1.9))
        self.assertEqual(shown.count("  Please type the age as a whole number from 18 to 130, for example 58."), 3)
        self.assertEqual(shown.count("  Please type the weight as a number from 20 to 500, for example 72."), 3)
        self.assertEqual(shown.count("  Please type eGFR as a number from 0 to 200, for example 60."), 3)
        self.assertEqual(shown.count("  Please type creatinine as a number above 0 and up to 20, for example 1.1."), 3)

    def test_plan_refuses_unreal_numbers(self):
        """plan() with a NaN or infinite age, weight, eGFR or creatinine gives a message and no plan."""
        expected = {
            "age": "The age must be a whole number from 18 to 130. Please correct the age and try again.",
            "weight": "The weight must be a number from 20 to 500. Please correct the weight and try again.",
            "egfr": "The eGFR must be a number from 0 to 200. This patient's eGFR was entered as {}, "
                    "so no plan was made.",
            "creatinine": "The creatinine must be a number above 0 and up to 20. Please correct the creatinine and "
                          "try again.",
        }
        for field, message in expected.items():
            for value in [float("nan"), float("inf"), float("-inf")]:
                with self.subTest(field=field, value=value):
                    result = planner.plan(dict(find_patient("Patient3"), **{field: value}))
                    self.assertEqual(list(result.keys()), ["message"])
                    self.assertEqual(result["message"], message.format(value))


class TestNumberRanges(unittest.TestCase):
    """
    SPEC section 12, decision 27: one range per number. Outside it, the message gives the range and the question
    is asked again; inside it, the value is accepted directly (no "Is it correct?"), and an unusual value gets a
    note in the report.
    """

    # Typed answers after the age: weight, eGFR, creatinine, pregnant, conditions, existing, allergies, already takes.
    REST_AFTER_AGE = ["", "", "", "no", "5", "", "", ""]

    def test_age_range_when_typed(self):
        """131, text and -1 are asked again with the range; 130 and 115 are accepted directly."""
        for typed in ["131", "fifty", "-1", "58.5"]:
            with self.subTest(typed=typed):
                patient, shown = run_entry(["Patient9", typed, "58"] + self.REST_AFTER_AGE)
                self.assertEqual(patient["age"], 58)
                self.assertIn("  Please type the age as a whole number from 18 to 130, for example 58.", shown)
        for age in [130, 115]:
            with self.subTest(age=age):
                patient, shown = run_entry(["Patient9", str(age)] + self.REST_AFTER_AGE)
                self.assertEqual(patient["age"], age)
                self.assertNotIn("Is it correct?", " ".join(shown))

    def test_under_18_flow_is_unchanged(self):
        """Under 18 keeps the existing adults-only flow, and its existing messages."""
        patient, shown = run_entry(["Patient9", "15", "16", "58"] + self.REST_AFTER_AGE)
        self.assertEqual(patient["age"], 58)
        self.assertIn("  That age cannot be planned for either.", shown)

    def test_weight_range_when_typed(self):
        """19, 501, 2 and text are asked again; 20, 500, 25 and 350 are accepted directly."""
        def weight_answers(typed):
            return ["Patient9", "58"] + typed + ["", "", "no", "5", "", "", ""]
        for bad in ["19", "501", "2", "heavy"]:
            with self.subTest(bad=bad):
                patient, shown = run_entry(weight_answers([bad, "49"]))
                self.assertEqual(patient["weight"], 49)
                self.assertIn("  Please type the weight as a number from 20 to 500, for example 72.", shown)
        for good in [20, 500, 25, 350]:
            with self.subTest(good=good):
                patient, shown = run_entry(weight_answers([str(good)]))
                self.assertEqual(patient["weight"], good)
                self.assertNotIn("Is it correct?", " ".join(shown))

    def test_creatinine_range_when_typed(self):
        """0, 20.1 and text are asked again; 0.1, 20, 0.15 and 12 are accepted directly."""
        def creatinine_answers(typed):
            return ["Patient9", "58", "", ""] + typed + ["no", "5", "", "", ""]
        for bad in ["0", "20.1", "high"]:
            with self.subTest(bad=bad):
                patient, shown = run_entry(creatinine_answers([bad, "1.5"]))
                self.assertEqual(patient["creatinine"], 1.5)
                self.assertIn("  Please type creatinine as a number above 0 and up to 20, for example 1.1.", shown)
        for good in [0.1, 20, 0.15, 12]:
            with self.subTest(good=good):
                patient, shown = run_entry(creatinine_answers([str(good)]))
                self.assertEqual(patient["creatinine"], good)

    def test_plan_refusals(self):
        """plan(): the same ranges for a patient written as a dictionary."""
        age_message = "The age must be a whole number from 18 to 130. Please correct the age and try again."
        for age in [131, 580, 58.5]:
            with self.subTest(age=age):
                self.assertEqual(planner.plan(dict(find_patient("Patient3"), age=age)), {"message": age_message})
        weight_message = "The weight must be a number from 20 to 500. Please correct the weight and try again."
        for weight in [19, 501, 0, -5]:
            with self.subTest(weight=weight):
                self.assertEqual(planner.plan(dict(find_patient("Patient3"), weight=weight)),
                                 {"message": weight_message})
        creatinine_message = ("The creatinine must be a number above 0 and up to 20. Please correct the creatinine "
                              "and try again.")
        for creatinine in [0, -5, 20.1]:
            with self.subTest(creatinine=creatinine):
                self.assertEqual(planner.plan(dict(find_patient("Patient3"), creatinine=creatinine)),
                                 {"message": creatinine_message})
        for change in [{"age": 130}, {"weight": 20}, {"weight": 500}, {"creatinine": 20}]:
            with self.subTest(change=change):
                self.assertIsNone(planner.plan(dict(find_patient("Patient3"), **change))["message"])

    def test_report_notes(self):
        """An unusual value inside the range gets a note in the report; a normal one does not."""
        cases = [
            ({"age": 115}, "Note: an age of 115 is unusually high (above 110). Please check it is not a typing mistake."),
            ({"weight": 22}, "Note: a weight of 22 kg is unusually low (below 35). Please check it is not a typing mistake."),
            ({"weight": 350}, "Note: a weight of 350 kg is unusually high (above 300). Please check it is not a typing mistake."),
            ({"creatinine": 0.15}, "Note: a creatinine of 0.15 is unusually low (below 0.3). Please check it is not a typing mistake."),
            ({"creatinine": 12}, "Note: a creatinine of 12 is unusually high (above 10). Please check it is not a typing mistake."),
        ]
        for change, note in cases:
            with self.subTest(change=change):
                self.assertIn(note, planner.patient_report(dict(find_patient("Patient3"), **change)))
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.assertNotIn("unusually", "\n".join(planner.patient_report(patient)))


class TestMissingEgfrNote(unittest.TestCase):
    """SPEC section 12, decision 25: a reminder when eGFR was not recorded and a kidney-restricted drug is shown."""

    def no_egfr_patient(self, needs):
        """A patient with no eGFR recorded, who needs these conditions."""
        return {"name": "NoEGFR", "needs": needs, "age": 58, "weight": 80, "creatinine": 1.0,
                "pregnant": False, "allergies": [], "has": []}

    def test_drugs_come_from_the_facts(self):
        """The kidney-restricted drugs are read from kb_facts.py, not written into the code."""
        self.assertEqual(planner.egfr_attributes(), ["SevereKidneyImpairment", "ModerateKidneyImpairment"])
        self.assertEqual(planner.kidney_restricted_drugs(), ["Metformin", "Ibuprofen", "Glipizide"])

    def test_note_names_the_shown_drugs(self):
        """Diabetes and Pain with no eGFR: all three drugs are in the shown options."""
        self.assertIn("Note: eGFR was not recorded. Please check it: Metformin, Ibuprofen and Glipizide have kidney "
                      "restrictions.", planner.patient_report(self.no_egfr_patient(["Type2Diabetes", "ChronicPain"])))

    def test_note_names_only_the_shown_drugs(self):
        """Pain only: Ibuprofen is the only one of the three in the options, and the verb is singular."""
        self.assertIn("Note: eGFR was not recorded. Please check it: Ibuprofen has kidney restrictions.",
                      planner.patient_report(self.no_egfr_patient(["ChronicPain"])))

    def test_no_note_without_a_kidney_restricted_drug(self):
        """Blood pressure and Heart rhythm only: none of the three drugs is shown, so there is no note."""
        text = "\n".join(planner.patient_report(self.no_egfr_patient(["Hypertension", "AtrialFibrillation"])))
        self.assertNotIn("eGFR was not recorded. Please check it", text)

    def test_no_note_when_egfr_is_recorded(self):
        """None of the 8 test patients gets the note (they all have an eGFR)."""
        for patient in PATIENTS:
            with self.subTest(patient=patient["name"]):
                self.assertNotIn("eGFR was not recorded. Please check it", "\n".join(planner.patient_report(patient)))

    def test_note_does_not_change_the_ranking(self):
        """The note is printout only: the plan is the same as before."""
        patient = self.no_egfr_patient(["Type2Diabetes", "ChronicPain"])
        self.assertEqual(len(planner.plan(patient)["ranked"]), 4)


class TestMissingEgfrWithNothingToPlan(unittest.TestCase):
    """A bug found while removing the old printout: no eGFR and nothing to plan made the report crash."""

    def test_report_works(self):
        """Patient E has no eGFR and only needs diabetes, which Metformin already treats: no table, no crash."""
        text = report_text(PATIENT_E)
        self.assertIn("Nothing else to plan: every condition asked for is already treated.", text)
        self.assertNotIn("eGFR was not recorded. Please check it", text)


class TestCleanStop(unittest.TestCase):
    """SPEC section 12, decision 28: Ctrl+C or Ctrl+D at any question stops cleanly with "No plan was made."."""

    def stop_after(self, answers, stop):
        """Answer some questions, then raise 'stop' (as Python does for Ctrl+C or Ctrl+D). Returns what was shown."""
        remaining = list(answers)

        def read_line(question):
            if len(remaining) == 0:
                raise stop
            return remaining.pop(0)
        shown = []
        enter_patient.main(read_line, shown.append)
        return shown

    def test_ctrl_c_and_ctrl_d(self):
        """Stopping during the questions, or at "Show the steps?", ends with an empty line and the message."""
        for stop in [KeyboardInterrupt(), EOFError()]:
            for answers in [["Patient9"], list(PATIENT3_ANSWERS)]:
                with self.subTest(stop=type(stop).__name__, answers=len(answers)):
                    shown = self.stop_after(answers, stop)
                    self.assertEqual(shown[-2:], ["", "No plan was made."])

    def test_how_to_stop_is_shown(self):
        """The top of the entry says how to stop."""
        shown = self.stop_after([], KeyboardInterrupt())
        self.assertIn("Press Ctrl+C at any time to stop.", shown)
