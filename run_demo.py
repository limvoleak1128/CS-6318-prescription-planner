"""
Shows the results for the 8 test patients, for the slides. Run with:
  python run_demo.py                  an overview of the 8 test patients (one row each)
  python run_demo.py Patient3         one patient in detail
  python run_demo.py steps Patient3   how the planner searched, and how it explains each drug that is not
                                      suitable, step by step (for presenting the method)

This is the version for presenting the project, so the details show every
option, the ranking points, and the search numbers (SPEC section 12, decisions 8, 9 and 19).
"""
import sys

import kb_facts as facts
import planner
from test_patients import PATIENTS


def patient_summary(patient):
    """One patient in detail: the same report that enter_patient.py shows (planner.patient_report)."""
    return planner.patient_report(patient)


def steps_lines(patient):
    """The steps for one patient, for presenting the method (planner.steps_report)."""
    return planner.steps_report(patient)


def recommended_text(result):
    """The Recommended column of the overview: the best regimen, the number of tied ones, or why there is none."""
    if len(result["winners"]) == 1:
        return " + ".join(result["winners"][0])
    if len(result["winners"]) > 1:
        return f"{len(result['winners'])} tied options (see the details)"
    blocked_words = []
    for condition in result["blocked_conditions"]:
        blocked_words.append(planner.CONDITION_WORDS[condition])
    if len(blocked_words) > 0:
        return f"None ({', '.join(blocked_words)} blocked)"
    return "None"


def overview_lines():
    """One row per test patient: conditions, states made, safe regimens, and the recommendation."""
    rows = [["Patient", "Conditions", "States made", "Safe regimens", "Recommended"],
            ["-------", "----------", "-----------", "-------------", "-----------"]]
    for patient in PATIENTS:
        result = planner.plan(patient)
        safe = result["regimen_count"] - result["invalid_count"]
        rows.append([patient["name"], str(len(patient["needs"])),
                     f"{result['states_generated']} of {result['full_tree_size']}",
                     f"{safe} of {result['regimen_count']}", recommended_text(result)])
    return planner.table_lines(rows)


def patient_names():
    """The names of the 8 test patients, for example "Patient1, Patient2, ...". """
    names = []
    for patient in PATIENTS:
        names.append(patient["name"])
    return ", ".join(names)


def print_overview():
    """The overview, followed by how to see one patient in detail and how to see the steps."""
    print("THE PRESCRIPTION PLANNER: RESULTS FOR THE 8 TEST PATIENTS")
    print()
    print("\n".join(overview_lines()))
    print()
    print("To see one patient in detail:      python run_demo.py Patient3")
    print("To see the steps for one patient:  python run_demo.py steps Patient3")
    print(f"(Any of the 8 patients can be used: {patient_names()}.)")


def find_test_patient(name):
    """The test patient with this name (capitals do not matter), or None."""
    for patient in PATIENTS:
        if patient["name"].lower() == name.lower():
            return patient
    return None


def main(arguments):
    """
    python run_demo.py                  an overview of the 8 test patients, and how to see more
    python run_demo.py Patient3         one patient in detail: the same report as enter_patient.py (options
                                        with points, cautions for the best option, why it is the best option,
                                        and why some drugs are not suitable)
    python run_demo.py steps Patient3   how the planner searched, and how it explains each drug that is not
                                        suitable, step by step (for presenting the method)
    "steps" without a patient's name shows the overview, which says how to use it.
    """
    print()   # a blank line, so the output does not start right after the command
    if len(arguments) == 0 or (arguments[0].lower() == "steps" and len(arguments) == 1):
        print_overview()
        return

    if arguments[0].lower() == "steps":
        patient = find_test_patient(arguments[1])
    else:
        patient = find_test_patient(arguments[0])
    if patient is None:
        print(f"There is no test patient called {arguments[-1]}. Choose one of: {patient_names()}.")
        return

    if arguments[0].lower() == "steps":
        print("\n".join(steps_lines(patient)))
        return

    print(f"Points: {facts.MODERATE_INTERACTION_POINTS} for a drug interaction caution, "
          f"{facts.OTHER_FLAG_POINTS} for any other caution, {facts.DOSE_NOTE_POINTS} for a dose note.")
    print("(The weights express the project's judgment of seriousness: interaction > caution > dose note.")
    print(" They are not clinically calibrated.)")
    print()
    print("\n".join(patient_summary(patient)))


if __name__ == "__main__":
    main(sys.argv[1:])
