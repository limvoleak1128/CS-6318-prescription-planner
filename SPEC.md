# The Prescription Planner: design specification

This file describes what the program does and how it is built. Section 12 records every design decision.

## 1. What to build

A Python program (standard library only) that does this for one patient at a time:

1. Takes a patient profile with the conditions the patient needs treated.
2. Picks exactly one drug for each condition from that condition's two candidate drugs.
3. Rejects unsafe choices, flags concerns, and ranks the safe complete regimens.
4. Explains every rejection and flag, and can answer "why was this drug rejected?".

It has three parts:

- A knowledge base (KB) with a **real forward chainer**. Rules are data, matched against facts.
- A **depth-first search with backtracking** that builds a regimen one condition at a time.
- **Explanations**, including a small **backward chainer** for "why?".

This is a course project for an AI class, and the code is a bonus. Every part must be easy to explain, so
readability matters more than cleverness.

## 2. Files provided at the start (kept unchanged)

| File | What it is |
|---|---|
| `kb_facts.py` | The 61 facts and the constants (cut-offs, weights). Each fact has a `# ref` number that points to the Restriction Table PDF. |
| `test_patients.py` | 8 test patients (`PATIENTS`) and the correct results (`EXPECTED`). This is the answer key. |
| `reference_evaluator.py` | A simple, separate implementation of the same judgments, used only to cross-check the program. It is not the forward chainer. |

## 3. Files to create

| File | Purpose |
|---|---|
| `kb.py` | Fact encoding, the 29 rules, the forward and backward chainers, and the input checks |
| `search.py` | The depth-first search and the ranking |
| `planner.py` | `plan(patient)` and `why(patient, drug)`, plus readable printing |
| `test_planner.py` | Tests (use `unittest`; run with `python -m unittest`) |
| `run_demo.py` | Prints the results for the 8 patients, in a form that can be used in presentation slides |

## 4. Patient profile (a Python dict)

```python
patient3 = {
    "name": "Patient3",
    "needs": ["Type2Diabetes", "ChronicPain", "AtrialFibrillation"],   # search order = this order
    "age": 58, "weight": 80, "egfr": 40, "creatinine": 1.9,
    "pregnant": False, "allergies": [], "has": [],
    "current_medications": []
}
```

- `has` holds typed yes/no attributes from `TYPED_ATTRIBUTES` in `kb_facts.py`.
- `current_medications` lists drugs the patient already takes. If the field is missing, the patient takes
  none (like `allergies`). The 8 test patients have no current medications. Every current medication must be
  one of the 10 drugs in `CONDITIONS`; otherwise the program stops with this message (the drug is shown
  exactly as entered):
  `The Prescription Planner only knows these 10 drugs: Lisinopril, Amlodipine, Atorvastatin, Simvastatin, Warfarin, Apixaban, Metformin, Glipizide, Ibuprofen, Acetaminophen. "Aspirin" is not one of them, so no plan was made.`
- A missing number means the attributes built from it are never created (the closed-world assumption:
  anything not recorded is treated as absent). Do not guess missing values.
- **Age is required, and the patient must be an adult (18 or older).** Before planning, the program checks
  the age and, if needed, stops with one of these messages (the age is shown exactly as entered, and the
  patient's name is not shown):
  - No age: `The Prescription Planner needs the patient's age. No age was recorded for this patient, so no plan was made.`
  - Under 18: `The Prescription Planner is designed for adults. This patient (age 15) is outside what it covers, so no plan was made.`
- The other numbers (`weight`, `egfr`, `creatinine`) may be missing.

## 5. The knowledge base

### 5.1 Fact encoding

Facts are tuples of strings and numbers, with the predicate name first:

- Static facts from `kb_facts.py`: `("Treats", drug, condition)`, `("Interacts", first, second, severity)`,
  `("RejectIfHas", drug, attribute)`, `("FlagIfHas", drug, attribute)`, `("RejectIfPregnant", drug)`,
  `("FlagIfPregnant", drug)`.
- Patient facts: `("Needs", patient, condition)`, `("Age", patient, years)`, `("Weight", patient, kilograms)`,
  `("EGFR", patient, score)`, `("Creatinine", patient, level)`, `("Pregnant", patient)`,
  `("Allergic", patient, drug)`, `("Has", patient, attribute)`, `("Taking", patient, drug)`.
- Added by the search: `("Chosen", patient, drug)`.
- Conclusions: `("Candidate", patient, drug)`, `("Conflict", patient, first, second, severity)`,
  `("CurrentConflict", patient, chosen, current, severity)`,
  `("Rejected", patient, drug, reason)`, `("Flagged", patient, drug, reason)`,
  `("DoseNote", patient, "Apixaban", "ReduceDose")`, `("InvalidRegimen", patient)`,
  `("CurrentWarning", patient, drug, reason)`.
- A reason is an attribute name, `"Allergy"`, `"Pregnancy"`, `("InteractionWith", other_drug)`, or
  `("InteractionWithCurrent", current_drug)`.

### 5.2 The 29 rules (mirror this notation in comments)

Variables are lowercase full words. In code, write them with a leading question mark, for example `"?patient"`.
Conditions such as `years >= 65` are plain Python comparisons checked after the variables are replaced.

```
A. Candidates (1)
∀patient, condition, drug, Needs(patient, condition), Treats(drug, condition) ➔ Candidate(patient, drug)

B. Turning numbers into attributes (8)
∀patient, years, Age(patient, years), years ≥ 65 ➔ Has(patient, Elderly)
∀patient, years, Age(patient, years), years ≥ 80 ➔ Has(patient, AgeAtLeast80)
∀patient, score, EGFR(patient, score), score < 30 ➔ Has(patient, SevereKidneyImpairment)
∀patient, score, EGFR(patient, score), score ≥ 30, score < 45 ➔ Has(patient, ModerateKidneyImpairment)
∀patient, kilograms, Weight(patient, kilograms), kilograms ≤ 60 ➔ Has(patient, LowWeight)
∀patient, level, Creatinine(patient, level), level ≥ 1.5 ➔ Has(patient, HighCreatinine)
∀patient, Has(patient, ModerateLiverImpairment) ➔ Has(patient, ActiveLiverDisease)
∀patient, Has(patient, SevereLiverImpairment) ➔ Has(patient, ActiveLiverDisease)

C. Checks on a chosen regimen (8)
∀patient, drug, Chosen(patient, drug), Allergic(patient, drug) ➔ Rejected(patient, drug, Allergy)
∀patient, drug, attribute, Chosen(patient, drug), Has(patient, attribute), RejectIfHas(drug, attribute) ➔ Rejected(patient, drug, attribute)
∀patient, drug, attribute, Chosen(patient, drug), Has(patient, attribute), FlagIfHas(drug, attribute) ➔ Flagged(patient, drug, attribute)
∀patient, drug, Chosen(patient, drug), Pregnant(patient), RejectIfPregnant(drug) ➔ Rejected(patient, drug, Pregnancy)
∀patient, drug, Chosen(patient, drug), Pregnant(patient), FlagIfPregnant(drug) ➔ Flagged(patient, drug, Pregnancy)
∀patient, first, second, severity, Chosen(patient, first), Chosen(patient, second), Interacts(first, second, severity) ➔ Conflict(patient, first, second, severity)
∀patient, first, second, Conflict(patient, first, second, Major) ➔ Rejected(patient, first, InteractionWith(second))
∀patient, first, second, Conflict(patient, first, second, Moderate) ➔ Flagged(patient, first, InteractionWith(second))

D. Apixaban dose note, two of three conditions (3)
∀patient, Chosen(patient, Apixaban), Has(patient, AgeAtLeast80), Has(patient, LowWeight) ➔ DoseNote(patient, Apixaban, ReduceDose)
∀patient, Chosen(patient, Apixaban), Has(patient, AgeAtLeast80), Has(patient, HighCreatinine) ➔ DoseNote(patient, Apixaban, ReduceDose)
∀patient, Chosen(patient, Apixaban), Has(patient, LowWeight), Has(patient, HighCreatinine) ➔ DoseNote(patient, Apixaban, ReduceDose)

E. Verdict (1)
∀patient, drug, reason, Rejected(patient, drug, reason) ➔ InvalidRegimen(patient)

F. Current medications (4)
∀patient, current, chosen, severity, Taking(patient, current), Chosen(patient, chosen), Interacts(current, chosen, severity) ➔ CurrentConflict(patient, chosen, current, severity)
∀patient, current, chosen, severity, Taking(patient, current), Chosen(patient, chosen), Interacts(chosen, current, severity) ➔ CurrentConflict(patient, chosen, current, severity)
∀patient, chosen, current, CurrentConflict(patient, chosen, current, Major) ➔ Rejected(patient, chosen, InteractionWithCurrent(current))
∀patient, chosen, current, CurrentConflict(patient, chosen, current, Moderate) ➔ Flagged(patient, chosen, InteractionWithCurrent(current))

G. Warnings about current medications (4)
∀patient, drug, Taking(patient, drug), Allergic(patient, drug) ➔ CurrentWarning(patient, drug, Allergy)
∀patient, drug, attribute, Taking(patient, drug), RejectIfHas(drug, attribute), Has(patient, attribute) ➔ CurrentWarning(patient, drug, attribute)
∀patient, drug, Taking(patient, drug), Pregnant(patient), RejectIfPregnant(drug) ➔ CurrentWarning(patient, drug, Pregnancy)
∀patient, first, second, Taking(patient, first), Taking(patient, second), Interacts(first, second, Major) ➔ CurrentWarning(patient, first, InteractionWith(second))
```

The cut-off numbers are in `kb_facts.py`. Use those constants, not typed-in numbers.

Notes on groups F and G:
- Each interaction pair is stored once, in one order, so there are two `CurrentConflict` rules, one for each
  order.
- In group F, the drug that is rejected or flagged is always the newly chosen one. The patient already takes
  the current drug, so the planner cannot remove it.
- Group G gives a warning when a medicine the patient already takes would be not suitable for them (the same
  restrictions that reject a chosen drug). A `CurrentWarning` never rejects an option and does not change
  the ranking: rule E only looks at `Rejected` facts.
- Group G warns only about "not suitable" problems. Cautions about current medicines (FlagIfHas,
  FlagIfPregnant, Moderate interactions between two current medicines, the dose note) are not shown; the
  printout says so (section 12, decision 3).
- Groups F and G use the same facts as groups C and D. No new facts are needed in `kb_facts.py`.
- The age check and the current-medication check (section 4) are plain input checks done before chaining,
  not rules.

### 5.3 The forward chainer (must be a genuine one)

- A rule is data: a list of condition patterns, optional comparisons, and one conclusion pattern.
- Matching replaces variables with constants (the course calls this SUBST, and Universal Elimination).
- When all conditions of a rule match facts, the conclusion is added (And-Introduction, then
  Implication-Elimination).
- Repeat passes over all rules until a full pass adds no new fact.
- Do **not** hard-code one `if` per drug or per interaction. The facts tables carry the medical content;
  the rules are general. Keep the matching simple and readable.
- Rules only add facts. No rule uses "not" and nothing is ever deleted.
- To try a regimen, build a fresh fact set (patient facts + static facts + the `Chosen` facts) and chain.
  Do not mutate shared state, so there is no retraction logic to get wrong. (The result of chaining the
  patient facts alone may be cached.)

## 6. Scoring and ranking

- Points come from `Flagged` facts: a flag whose reason is `("InteractionWith", ...)` or
  `("InteractionWithCurrent", ...)` costs `MODERATE_INTERACTION_POINTS` (3); every other flag costs
  `OTHER_FLAG_POINTS` (1). Dose notes cost 0.
- A regimen with any `Rejected` fact is invalid and is dropped.
- Rank valid regimens by: points, then number of flags, then number of dose notes (fewer is better).
  Regimens tied on all three are tied winners and are listed together. Sort ties by regimen for a stable order.
- The weights, cut-offs and severity labels are project choices, not clinical ratings. Say so in comments.

## 7. The search (depth-first with backtracking)

```
SEARCH(index, chosen):
    if index equals the number of conditions the patient needs:
        record the complete regimen (it passed every check on the way down)
        return
    for each candidate drug for needs[index], in the order listed in CONDITIONS:
        count one more state generated
        run the forward chainer on patient facts + Chosen facts for chosen + this drug
        if any Rejected fact appears: dead end, go to the next drug
        else: SEARCH(index + 1, chosen + this drug)
```

- Before searching, run the age check (section 4). If it gives a message, report the message and do not search.
- Count the root as one state. `states_generated` must match `EXPECTED` (for Patient3 it is 9 of 15).
- After the search, compute points, flag counts and dose notes for each complete regimen, then rank.
- If there is no valid complete regimen, report it plainly ("no complete regimen") and list the conditions
  where every candidate drug is rejected on its own (`blocked_conditions`). Do not guess a regimen.
- Return the same fields as `reference_evaluator.plan_reference` so the tests can compare them directly.

## 8. Explanations

- Every `Rejected` and `Flagged` fact carries its reason. `plan` prints, for each valid regimen, its
  points and the reasons for each flag; for each rejected branch, the reason.
- `why(patient, drug)` uses **backward chaining**: start from the goal `Rejected(patient, drug, reason)`,
  find the rule that concludes it, set the premises as sub-goals, and report which ones succeed or fail.
  Print the steps like this (Patient3, Metformin):

```
Goal: Rejected(Patient3, Metformin, reason)
  Sub-goal 1: Chosen(Patient3, Metformin)        true
  Sub-goal 2: RejectIfHas(Metformin, attribute)  the KB has three facts, so try each
    attribute = SevereKidneyImpairment   needs EGFR below 30, but EGFR is 40      FAILS
    attribute = ModerateKidneyImpairment needs 30 <= 40 < 45                       SUCCEEDS
    attribute = ActiveLiverDisease       needs a liver impairment fact; none       FAILS
Answer: reason = ModerateKidneyImpairment
```

## 9. Tests to write (`test_planner.py`)

1. **Answer key:** for each of the 8 patients, `plan(patient)` matches `EXPECTED` on `regimen_count`,
   `invalid_count`, `ranked`, `winners`, `blocked_conditions` and `states_generated`.
2. **Cross-check:** the forward chainer's verdict for every regimen of every patient agrees with
   `reference_evaluator.judge_regimen` (rejections, flags, points). Also test 500 random patients
   (random conditions, ages, labs, pregnancy, typed attributes, allergies) with a fixed random seed.
3. **Search vs brute force:** the search finds exactly the valid regimens that trying all combinations finds.
4. **Every rejection:** one tiny patient per `RejectIfHas`/`RejectIfPregnant` fact, the Major interaction,
   and the allergy rule, each producing the expected `Rejected` result.
5. **Every flag:** across the 8 patients, all 28 flag triggers appear in at least one valid regimen
   (17 `FlagIfHas`, 3 `FlagIfPregnant`, 7 Moderate interactions, 1 Apixaban dose note).
6. **Boundaries:** just below and at each cut-off: age 64/65 and 79/80, eGFR 29/30 and 44/45,
   weight 60/61, creatinine 1.49/1.5.
7. **Missing information:** a patient with no `egfr` never gets a kidney attribute; no `weight` means no
   `LowWeight`. These tests document the closed-world assumption.
8. **Fact-base consistency:** no drug has the same attribute under both reject and flag; no interaction
   pair is stored twice (in either order); both drugs in a pair treat different conditions; every attribute
   used by a fact is in `TYPED_ATTRIBUTES` or `BUILT_ATTRIBUTES`.
9. **`why`:** `why(patient3, "Metformin")` reports `ModerateKidneyImpairment`.
10. **Age check:** no age gives the "needs the patient's age" message; age 15 gives the "designed for adults"
    message; age 18 is accepted. Random patients in test 2 are 18 or older.
11. **Current medications:** small patients whose answers were checked with `reference_evaluator.judge_regimen`
    by treating the current medication as if it were chosen (adults, not pregnant unless stated):
    - A: takes Warfarin, needs ChronicPain: Ibuprofen rejected (Major with Warfarin); Acetaminophen flagged
      (Moderate with Warfarin).
    - B: takes Simvastatin, needs Hypertension: Lisinopril has no concerns; Amlodipine flagged (Moderate).
    - C: pregnant, takes Warfarin, needs Hypertension and ChronicPain: warning for Warfarin (Pregnancy);
      Lisinopril and Ibuprofen rejected; the only option is Amlodipine + Acetaminophen with 2 pregnancy flags
      and 1 Moderate interaction flag (Acetaminophen with Warfarin).
    - D: takes Warfarin and Ibuprofen, needs Type2Diabetes: warning for Warfarin (Major with Ibuprofen);
      Metformin and Glipizide are both flagged (each is Moderate with Warfarin), so they are tied.
    - E: takes Metformin, needs Type2Diabetes: Type2Diabetes is not planned (Metformin already treats it),
      so there is nothing else to plan. With ChronicPain also needed, only ChronicPain is planned.
    - F: takes Aspirin: the "only knows these 10 drugs" message, and no plan.
    `reference_evaluator.py` does not know about current medications, so the cross-check (test 2) uses
    patients with no current medications, and the 8 test patients must give the same results as before.

## 10. Suggested order of work (small steps)

1. Load the facts, build a patient's facts, and derive attributes (rules B), with the age check. The forward
   chainer is written here, because rules B need it. Test against Patient3.
2. Add rules A, C, D, E. Test single drugs and pairs on Patient3.
3. Write the search and ranking. Make the answer-key test pass for all 8 patients.
4. Write `why` (backward chaining) and the readable printing.
5. Add the remaining tests and `run_demo.py`.
6. Add current medications (rules F and G, the input check, the printout) and their tests.
7. Add the question-and-answer patient entry (section 12, item 7).

After each step, the tests were run and the work was saved with a Git commit once they passed.

## 11. Assumptions to keep (write them as comments where they apply)

1. Moderate or severe liver impairment counts as active liver disease.
2. Any heart failure flags Lisinopril (the label says severe; the profile has no severity).
3. Metformin is rejected at eGFR 30 up to but not including 45 (the label says do not start it there).
4. Yes/no history items are typed in; they cannot be calculated.
5. Allergies are per drug only.
6. Closed world: anything not recorded is treated as absent.
7. Adults only (18 or older), and age is required (section 4). This is a course project, not a clinical tool.
8. Age never rejects a drug. It only flags (Elderly, AgeAtLeast80) or adds the Apixaban dose note. This is
   intended.

## 12. Design decisions

Current medications (step 6):

1. Current medications must be among the 10 drugs in the KB (this is the project's scope). Any other drug
   stops the planner with a friendly message that lists the 10 drugs, and no plan is made.
2. A current medication that already treats a needed condition (option (a), chosen in step 7): that condition
   is NOT planned, because the KB has no facts about taking two drugs for the same condition. The other
   conditions are planned as usual, and are still checked against the current medication. The note:
   `Note: Diabetes is not planned, because the patient already takes Metformin for it.`
   `      To plan a replacement instead, enter the patient again without Metformin in the medicines already taken.`
   If every condition asked for is already treated, the printout says
   `Nothing else to plan: every condition asked for is already treated.` (any WARNING is still shown).
3. Option (b), chosen to keep step 6 small: current medications are checked for "not suitable" problems only
   (allergy, a condition that rules the drug out, pregnancy, a serious interaction between two current
   medicines), by the 4 rules in group G. Each one is shown as a WARNING near the top of the printout, for
   example:
   `WARNING  Warfarin (already taken) is not suitable for this patient: pregnancy. A doctor should review it.`
   Warnings do not reject options or change the ranking. Whenever the patient takes something, the printout
   also says:
   `Note: medicines the patient already takes are checked for interactions with the new medicines and for`
   `serious problems only. Other cautions about them are not shown. A doctor should review them separately.`

No complete regimen (Idea A):

4. If some condition has no safe option, say so plainly ("No safe option was found for ..."), give the reason
   for each drug, and say it needs a doctor's decision outside the planner. Then still plan the other
   conditions, with a note that the drug chosen later for the blocked condition could not be checked
   against them. The fields compared with `EXPECTED` do not change. This is a scope limitation: the KB has
   only two drugs per condition, and no drugs are added.

Printing (step 4), for the reader (a doctor or pharmacist, not a programmer):

5. (Replaced by the patient report, decision 20; the code for this layout was removed in decision 26.)
   Layout ("Version A"), in this order:
   - Title `PLAN FOR <NAME>`, then a line of `=`, then one line with the patient's numbers.
   - Any WARNING about medicines the patient already takes.
   - If there is no complete plan: which condition has no suitable drug and why, then "A doctor needs to
     decide", then the options for the other conditions.
   - The options as a table: one row per option (`Recommended`, `Option 2`, ... or `Best` when tied), one
     column per condition, and a `Concerns` column (for example `1 caution, 2 interactions`). When options
     are tied, one line above the table says they are equally good and which conditions they differ in.
   - `Cautions`: each caution explained once, with the options it applies to.
   - `Check the dose`: the Apixaban dose note, with the three conditions in plain words and which ones the
     patient meets.
   - `Not suitable`: rejected drugs and pairs, with the reason.
   - Each section heading is followed by a line of `-`. The plan ends with a line of `=`.
6. Plain words only: no rule names or attribute names (for example "reduced kidney function (eGFR 40)",
   not `ModerateKidneyImpairment`), "Not suitable" instead of "Rejected", and only plain ASCII characters.

Patient entry (step 7):

7. A question-and-answer entry in the terminal (`enter_patient.py`, run with `python enter_patient.py`):
   - Questions are short and give no example, for example `Age in years (required):`. A wrong answer gives a
     friendly message with an example (`Please type the age as a whole number, for example 58.`) and asks again.
   - Only the required questions are marked `(required)`: name, age, pregnancy, conditions to treat. One line at
     the top explains the rest: `Questions marked (required) must be answered. You can leave the others empty:
     press Enter.` Optional questions (weight, eGFR, creatinine, existing conditions, allergies, medicines
     already taken) have no label. The pregnancy question says `(required, yes or no)` and accepts yes/y/no/n.
   - Conditions, existing conditions, allergies and medicines already taken are chosen from numbered lists.
     The numbers may be separated by spaces, commas or both. Conditions are planned in the order typed.
     Only the 10 drugs can be chosen.
   - Under 18: the adults-only message is shown, and the user may type the age again (in case of a typing
     mistake) or press Enter to stop.
   - (Removed in decision 21: "Explain a drug?". Earlier text:) After the plan is printed: `Explain a drug? Type its name, or press Enter to finish:` runs the short
     `why` for that drug, together with the recommended option.

8. (Changed by decision 20: the patient report now shows the points, like the demo.) The reader-facing
   printout (`format_plan`) shows no ranking points. It shows the order and labels: "Caution" (allowed,
   something to watch), "Interaction caution" (two medicines can affect each other; counts more), and
   "Check the dose". The points still appear in `run_demo.py`, the version for presenting the project.

9. Show at most 5 options, followed by "(N more options with more concerns are not shown)". If more than 5
   options are tied for best, show all of the tied ones. `run_demo.py` still shows every option.
10. Keep full condition names in the table, even though a 5-condition table is about 100 characters wide.
11. Option rows are labeled "Option 1", "Option 2", ...; a line above the table says "Recommended: Option 1." or
    "Options 1 to N are equally good. They differ only in ..." ("Options 1 and 2" when two are tied).
    A drug pair with a medicine already taken is written "Ibuprofen + already-taken Warfarin".
12. Wording and grouping (first version, may be changed later):
    - Cautions and Not suitable are grouped by reason: each reason is written once as a heading, followed
      by the medicines it affects, for example `Pregnancy  Acetaminophen, Amlodipine (all options), Glipizide (option 2)`.
    - "drug interaction" instead of "interaction". Moderate interactions go under the heading
      "Drug interactions" as pairs (`Apixaban + Ibuprofen`), with one note: "These can affect each other.
      Use together with care." A Major one goes under "Serious drug interaction":
      `Warfarin + Ibuprofen: must not be taken together`.
    - Assumption 1 (liver disease) is shown as the liver impairment the patient actually has, for example
      "Moderate liver impairment", so both kinds of liver restriction share one heading.
    - A blocked condition says, for example, "Severe liver impairment rules out Ibuprofen and Acetaminophen."
13. `why(patient, drug, regimen, full=False)`: the short version (default) shows the steps only for goals
    that succeed; `full=True` shows every step. The answers are the same.
14. Weight stays optional (it is only used by the Apixaban dose note). When a shown option has Apixaban
    without the dose note, but weight or creatinine was not recorded and the missing number could make it
    2 of 3, "Check the dose" says what is missing, asks the reader to check it, and says why, for example:
    `Weight was not recorded. Please check it: a lower dose may be needed if the patient weighs 60 kg or less,`
    `because creatinine is already 1.5 or higher (1.9).` (With nothing already true and both numbers missing,
    the two conditions are joined with "and"; otherwise with "or".) This is a plain check in the printout,
    not a rule (a rule would need "not recorded"). It does not change the ranking.
15. Metformin has no pregnancy fact in the KB. The source (ref 17) says "no clear association with major birth
    defects/miscarriage in published studies; not first-line". It was decided not to add a pregnancy
    caution for it, so the KB is unchanged.
16. Every "=" and "-" separator line is as long as the longest line of text in that printout (never shorter
    than 66 characters), so it always covers the whole printout.
17. eGFR input check (a project choice, to catch typing mistakes such as 400 for 40; not a clinical limit,
    since the sources give no maximum): eGFR must be a number from 0 to 200 (`EGFR_LOWEST`, `EGFR_HIGHEST`
    in `kb.py`). Otherwise `enter_patient.py` asks again, and `plan()` stops with
    `The eGFR must be a number from 0 to 200. This patient's eGFR was entered as 400, so no plan was made.`
    Above 150 (`EGFR_UNUSUALLY_HIGH`) the value is allowed, but `enter_patient.py` warns and asks
    `Is it correct? (yes or no)`, and the printout adds
    `Note: an eGFR of 180 is unusually high (above 150). Please check it is not a typing mistake.`
    The answer key is unchanged (all test patients have eGFR from 25 to 105).
18. Two kinds of explanation for one drug. `explain(patient, drug, regimen)` is for the person running the
    program and is short: the answer and the reason on one line, for example
    `Metformin is NOT SUITABLE for Patient3: reduced kidney function (eGFR 40, between 30 and 44).`
    A drug that can be used shows its cautions (and the dose note). A not-suitable drug shows only the reason.
    It uses the same backward chainer as `why()`; only the wording differs. `why()` keeps the step-by-step
    trace, step by step, for presenting the method (SPEC section 8). `explain()` gives the "Answer:" lines of the steps view.
19. `run_demo.py` (every output starts with a blank line, so it does not run on from the command):
    - `python run_demo.py`: one overview row per test patient, then how to see one patient
      (`python run_demo.py Patient3`) and the steps (`python run_demo.py steps Patient3`). `steps` without a
      name shows the same overview.
    - `python run_demo.py Patient3` (any of the 8, any capitals): the search numbers, every option with points,
      "Why Option 1" (for each condition, why its drug was picked: the other drug is swapped in and judged by
      the forward chainer), and "Why some drugs are not suitable" (each problem once, with how many
      combinations it ruled out). This is the patient report of decision 20.
    - `python run_demo.py steps Patient3` (step by step, for presenting the method): PART 1, how the planner searched (every step of
      the depth-first search, with what the forward chainer said at that step); PART 2, how the planner
      explains each drug that is not suitable (backward chaining), each drug once. Each numbered question in
      PART 2 is a sub-goal that the backward chainer proves, written in plain words. The step-by-step trace in
      KB notation (`why`, SPEC section 8) is not printed by the demo; it stays in the code and the tests.
20. One patient report (`planner.patient_report`) for both `python run_demo.py Patient3` and `python enter_patient.py`:
    the patient (and any medicines already taken, warnings and notes), the search numbers, the options table
    with points (`*` marks the best) and one line "Options are listed from fewest to most concerns.", then
    "Cautions for the best option" (only the best option's drugs; Apixaban's dose note or missing-number
    reminder is in its row), "Why this is the best option", and "Why some drugs are not suitable".
    `enter_patient.py` then asks "Show the steps (how the planner searched and explained)? (yes or no)" (the
    same as `python run_demo.py steps Patient3`).
    Wording: reasons are said like a person would, keeping the KB's numbers, for example
    "the patient is 65 or older (age 82)" and "the patient has reduced kidney function (eGFR 40, between 30
    and 44)". A medicine already taken that is not suitable:
    `WARNING  Warfarin (already taken) is not suitable for this patient: active bleeding.`
    `         A doctor should review it.`
21. "Explain a drug?" is removed from `enter_patient.py`. The report already explains every drug that matters
    (the best option's cautions, why each drug was picked, and every drug that is not suitable), and the
    question accepted any of the 10 drugs, even ones for conditions the patient does not need.
22. The report's options table shows at most 10 options (`REPORT_OPTIONS_SHOWN` in `planner.py`), but always every
    option tied for best. If some are left out, a line under the table says so, for example
    `Showing the best 10 of 24 safe options. The other 14 have more concerns and are not shown.`
23. Numbers that are not real measurements: typing `nan`, `inf` or a huge number like `1e400` for any number
    question in `enter_patient.py` counts as "not a number" (`math.isfinite`), so the existing message for that
    question is shown and the question is asked again. In `plan()`, a NaN or infinite age, weight, eGFR or
    creatinine gives a message and no plan (a NaN age used to pass the age check, because "NaN < 18" is False):
    `The age must be a whole number from 18 to 130. Please correct the age and try again.`
    `The weight must be a number above 0. Please correct the weight and try again.`
    `The creatinine must be a number above 0. Please correct the creatinine and try again.`
    (The strange value itself, such as nan, is not shown. eGFR uses the existing decision-17 message.)
24. Age, weight and creatinine limits (project choices to catch typing mistakes, not clinical limits;
    constants in `kb.py` next to the eGFR ones). The questions themselves do not show a range; a range is
    only mentioned after a wrong or unusual answer.
    - Age: refused above 130 or if not a whole number; under 18 keeps the existing adults-only flow; above 110
      the user is asked to confirm it. Typed: `  Please type the age as a whole number from 18 to 130, for example 58.`
      and `  An age of 115 is unusually high (above 110). It may be a typing mistake.`
    - Weight: must still be above 0; under 35 or above 300 kg the user is asked to confirm it:
      `  A weight of 22 kg is unusually low (below 35). It may be a typing mistake.`
    - Creatinine: must still be above 0; under 0.3 or above 10 the user is asked to confirm it:
      `  A creatinine of 0.15 is unusually low (below 0.3). It may be a typing mistake.`
    - "yes" to `  Is it correct? (yes or no):` keeps the value; "no" asks the question again.
    - `plan()` (a patient written as a dictionary): `The age must be a whole number from 18 to 130. Please correct
      the age and try again.`, and `The weight must be a number above 0. Please correct the weight and try again.`
      (the same for creatinine) for 0 or less.
    - The report notes an unusual value that was accepted, like the eGFR note:
      `Note: a weight of 22 kg is unusually low (below 35). Please check it is not a typing mistake.`
25. Reminder when eGFR was not recorded. Without an eGFR the kidney checks are skipped (closed world), so drugs
    with kidney restrictions look free of concerns. When eGFR was not recorded and an option shown in the table
    contains such a drug, the report adds a note under the patient's details, for example:
    `Note: eGFR was not recorded. Please check it: Metformin, Ibuprofen and Glipizide have kidney restrictions.`
    Only the drugs that appear in the shown options are named ("has" for one drug). The drugs are read from the
    KB (the RejectIfHas and FlagIfHas facts for the attributes that rules B3 and B4 build from eGFR); no drug name
    is written into the code. This is a plain check in the printout, not a rule, and it does not change the ranking.
26. Unused code removed: the old reader printout (`format_plan` / `print_plan`, the "Version A" layout of
    decisions 5 and 9 to 12) and the helpers only it used, plus `print_why` and `print_explanation`. The patient
    report (decision 20) replaced the printout; `why()` stays (SPEC section 8). The tests of the old layout were
    removed or switched to the report. While switching them, a bug from decision 25 was found and fixed: a
    patient with no eGFR whose conditions are all already treated made the report crash (there is no options
    table to look at); a test now covers it.
27. One range per number, no "Is it correct?" questions (this replaces the confirmations of decisions 17 and 24):
    - age 18 to 130 (a whole number; under 18 keeps the adults-only flow), weight 20 to 500 kg (`WEIGHT_LOWEST`,
      `WEIGHT_HIGHEST`), eGFR 0 to 200, creatinine above 0 and up to 20 (`CREATININE_HIGHEST`). These are
      project choices to catch typing mistakes, not clinical limits.
    - In `enter_patient.py`, any wrong answer (text, nan, or outside the range) gets one message with the range,
      and the question is asked again:
      `  Please type the age as a whole number from 18 to 130, for example 58.`
      `  Please type the weight as a number from 20 to 500, for example 72.`
      `  Please type eGFR as a number from 0 to 200, for example 60.`
      `  Please type creatinine as a number above 0 and up to 20, for example 1.1.`
    - `plan()`: `The weight must be a number from 20 to 500. Please correct the weight and try again.` and
      `The creatinine must be a number above 0 and up to 20. Please correct the creatinine and try again.`
    - Unusual values inside the range (age above 110, weight below 35 or above 300 kg, eGFR above 150, creatinine
      below 0.3 or above 10) are accepted directly; the report keeps its note asking the reader to check them.
28. Clean stop: the top of `enter_patient.py` says `Press Ctrl+C at any time to stop.` Ctrl+C or Ctrl+D at any
    question prints an empty line and `No plan was made.` instead of a Python error.
