# The Prescription Planner

An intelligent agent that plans drug regimens for patients who need several medicines at once. I built it as a
term project for an Artificial Intelligence course. It is a course project, not a clinical tool.

## What it does

Patients with several conditions often need several medicines at the same time. A medicine that treats one
condition can interact badly with another medicine, or be unsuitable because of the patient's other
conditions, age, pregnancy or allergies. My agent takes a patient profile and the conditions to treat, and:

1. **searches** the possible drug combinations (depth-first search with backtracking),
2. uses a **knowledge base** of facts and rules, with **forward chaining**, to rule out unsafe combinations,
3. **ranks** the safe combinations by their concerns and recommends the best one,
4. **explains** its decisions, using **backward chaining**.

The knowledge base covers 5 conditions with 2 candidate drugs each (10 drugs) and five kinds of restriction:
drug-drug interactions, drug-condition restrictions, age, pregnancy and allergy. It has 61 facts and 29 rules in
first-order logic. The `ref` numbers in `kb_facts.py` point to the Restriction Table submitted with the project.

## How to run it

It needs Python 3 and nothing else (standard library only). In a terminal, in this folder:

| Command | What it shows |
|---|---|
| `python run_demo.py` | An overview of the 8 test patients, one row each |
| `python run_demo.py Patient3` | One patient in detail: every safe option with its points, cautions for the best option, why it is the best option, and why some drugs are not suitable |
| `python run_demo.py steps Patient3` | Step by step: how the planner searched (search and forward chaining), and how it explains each drug that is not suitable (backward chaining) |
| `python enter_patient.py` | Type in a new patient and get the same report |
| `python -m unittest` | Run all the tests |

Any of the 8 test patients can be used: Patient1, Patient2, Patient3, Patient3b, Patient4, Patient5, Patient5b,
Patient6 (3b and 5b are variations of 3 and 5).

## Files

| File | What it contains |
|---|---|
| `kb_facts.py` | The facts: conditions and drugs, interactions, restrictions, cut-off numbers and ranking weights |
| `kb.py` | The knowledge base: the 29 rules (as data), the forward chainer, the backward chainer, and the input checks |
| `search.py` | The depth-first search with backtracking, and the ranking |
| `planner.py` | `plan(patient)`, the explanations (`why`, `explain`), and the report |
| `run_demo.py` | The demo for the 8 test patients |
| `enter_patient.py` | The question-and-answer entry for a new patient |
| `test_planner.py` | The tests |
| `test_patients.py` | The 8 test patients and their expected results (the answer key) |
| `reference_evaluator.py` | A separate, simple version of the same judgments, used only to cross-check the program |
| `SPEC.md` | The design: the patient profile, the facts, all 29 rules, the search, the ranking, and every design decision |

## How I tested it

`python -m unittest` runs 150 tests, including: the answer key for the 8 test patients; a cross-check of every
result against `reference_evaluator.py`; 500 random patients; the search compared with trying every combination;
every restriction and every caution; the cut-off boundaries; missing information; the consistency of the facts;
and a check that forward and backward chaining always reach the same answers.

## Limitations

- Only two drugs per condition, so some patients have no complete plan (the agent says so and plans the rest).
- The agent chooses drugs, not doses (it only reminds about Apixaban's dose).
- The ranking weights express a judgment of seriousness; they are not clinically calibrated.
- A missing value is treated as absent (closed-world assumption); the report warns about missing weight,
  creatinine and eGFR.
- The input limits are project choices to catch typing mistakes, not clinical ranges.
