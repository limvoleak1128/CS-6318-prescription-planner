"""
Question-and-answer patient entry for The Prescription Planner.
Run with: python enter_patient.py

The program asks for each part of the patient profile, checks each answer, and asks again if an answer
is wrong (SPEC section 12, decision 7). Then it prints the same patient report as `python run_demo.py
Patient3` (planner.patient_report), and offers the steps (how the planner searched and explained).

Every function here takes two inputs:
  read_line  how to read one typed answer (normally Python's input)
  write      how to show a line of text (normally Python's print)
so the tests can give typed answers from a list instead of the keyboard.
This is a course project, not a clinical tool.
"""
import math

import kb
import kb_facts as facts
import planner


# ---------------------------------------------------------------------------
# Small helpers for reading answers
# ---------------------------------------------------------------------------

def read_number(text):
    """
    Turn typed text into a number, or return None if it is not a number.
    "58" gives 58, "1.9" gives 1.9, "fifty" gives None.
    Python also reads "nan" (not a number), "inf" (infinity) and huge numbers like "1e400" (which become
    infinity) as numbers. They are not real measurements, so they also give None (SPEC section 12, decision 23).
    """
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    if value == int(value):
        return int(value)
    return value


def split_numbers(text):
    """Split typed choices like "4, 5 3" into ["4", "5", "3"]: commas and spaces both separate them."""
    return text.replace(",", " ").split()


# ---------------------------------------------------------------------------
# The questions
# ---------------------------------------------------------------------------

def ask_name(read_line, write):
    """Ask for the patient's name or label. It may not be empty."""
    while True:
        answer = read_line("Patient name or label (required): ").strip()
        if answer != "":
            return answer
        write("  Please type a name or label, for example Patient9.")


def ask_age(read_line, write):
    """
    Ask for the age in years: a whole number from 18 to 130 (kb.ADULT_AGE_YEARS to kb.AGE_HIGHEST). Any other
    answer is asked again, with the range in the message. Under 18, show the adults-only message and let the user
    type the age again (in case of a typing mistake), or press Enter to stop. Returns the age, or None to stop.
    An unusually high age (above 110) is accepted; the report notes it (decision 27).
    """
    age_message = (f"  Please type the age as a whole number from {kb.ADULT_AGE_YEARS} to {kb.AGE_HIGHEST}, "
                   "for example 58.")
    while True:
        answer = read_line("Age in years (required): ").strip()
        age = read_number(answer)
        if age is None or not isinstance(age, int) or age < 0 or age > kb.AGE_HIGHEST:
            write(age_message)
            continue
        message = kb.age_problem({"age": age})
        if message is None:
            return age
        write("  " + message)
        again = read_line("  If this was a typing mistake, type the age again, or press Enter to stop: ").strip()
        if again == "":
            return None
        age = read_number(again)
        if (age is not None and isinstance(age, int) and age <= kb.AGE_HIGHEST
                and kb.age_problem({"age": age}) is None):
            return age
        write("  That age cannot be planned for either.")


def ask_optional_number(question, wrong_message, is_allowed, read_line, write):
    """
    Ask for a number that may be skipped by pressing Enter. Returns the number, or None if skipped.
    wrong_message  what to say when the answer is not allowed (it gives the range), before asking again
    is_allowed     a function that says whether a number is inside the allowed range
    """
    while True:
        answer = read_line(question + ": ").strip()
        if answer == "":
            return None
        value = read_number(answer)
        if value is None or not is_allowed(value):
            write(wrong_message)
            continue
        return value


def weight_is_allowed(weight):
    """A weight from 20 to 500 kg (kb.WEIGHT_LOWEST to kb.WEIGHT_HIGHEST, decision 27)."""
    return kb.WEIGHT_LOWEST <= weight <= kb.WEIGHT_HIGHEST


def egfr_is_allowed(egfr):
    """An eGFR from 0 to 200 (kb.EGFR_LOWEST to kb.EGFR_HIGHEST, decision 17)."""
    return kb.EGFR_LOWEST <= egfr <= kb.EGFR_HIGHEST


def creatinine_is_allowed(creatinine):
    """A creatinine above 0 and up to 20 (kb.CREATININE_HIGHEST, decision 27)."""
    return 0 < creatinine <= kb.CREATININE_HIGHEST


def ask_yes_no(question, read_line, write, hint="yes or no"):
    """
    Ask a yes-or-no question. Accepts yes, y, no and n (in any capitals).
    hint  shown in brackets after the question, for example "required, yes or no".
    """
    while True:
        answer = read_line(f"{question} ({hint}): ").strip().lower()
        if answer in ["yes", "y"]:
            return True
        if answer in ["no", "n"]:
            return False
        write("  Please type yes or no.")


def ask_choices(title, choices, required, example, read_line, write):
    """
    Show a numbered list and ask for the numbers of the chosen items.
    choices   a list of (value, words): the value is stored in the profile, the words are shown
    required  True if at least one must be chosen; otherwise Enter means "none"
    Returns the chosen values, in the order they were typed.
    """
    write("")
    write(title + ":")
    for number, (value, words) in enumerate(choices, start=1):
        write(f"  {number:>2} {words}")
    if required:
        question = "Type the numbers, in the order to plan them (required): "
    else:
        question = "Type the numbers: "

    while True:
        typed = split_numbers(read_line(question))
        if len(typed) == 0 and not required:
            return []
        chosen = []
        problem = False
        for text in typed:
            number = read_number(text)
            if number is None or not isinstance(number, int) or number < 1 or number > len(choices):
                problem = True
            elif choices[number - 1][0] in chosen:
                problem = True
            else:
                chosen.append(choices[number - 1][0])
        if len(chosen) > 0 and not problem:
            return chosen
        write(f"  Please type numbers from the list, each once, for example {example}.")


# ---------------------------------------------------------------------------
# The whole entry
# ---------------------------------------------------------------------------

def condition_choices():
    """The 5 conditions, with the words the printout uses."""
    choices = []
    for condition in facts.CONDITIONS:
        choices.append((condition, planner.CONDITION_WORDS[condition]))
    return choices


def attribute_choices():
    """The 11 typed yes/no attributes, with plain words."""
    choices = []
    for attribute in facts.TYPED_ATTRIBUTES:
        choices.append((attribute, planner.TYPED_ATTRIBUTE_WORDS[attribute]))
    return choices


def drug_choices():
    """The 10 drugs."""
    choices = []
    for drug in kb.all_drug_names():
        choices.append((drug, drug))
    return choices


def enter_patient(read_line, write):
    """Ask all the questions and return the patient profile (a dict), or None if the user stopped."""
    write("")   # a blank line, so the questions do not start right after the command
    write("THE PRESCRIPTION PLANNER: NEW PATIENT")
    write("Questions marked (required) must be answered. You can leave the others empty: press Enter.")
    write("Press Ctrl+C at any time to stop.")
    write("")
    name = ask_name(read_line, write)
    age = ask_age(read_line, write)
    if age is None:
        write("No plan was made.")
        return None
    patient = {"name": name, "age": age}

    weight = ask_optional_number(
        "Weight in kg",
        f"  Please type the weight as a number from {kb.WEIGHT_LOWEST} to {kb.WEIGHT_HIGHEST}, for example 72.",
        weight_is_allowed, read_line, write)
    egfr = ask_optional_number(
        "eGFR",
        f"  Please type eGFR as a number from {kb.EGFR_LOWEST} to {kb.EGFR_HIGHEST}, for example 60.",
        egfr_is_allowed, read_line, write)
    creatinine = ask_optional_number(
        "Creatinine in mg/dL",
        f"  Please type creatinine as a number above 0 and up to {kb.CREATININE_HIGHEST}, for example 1.1.",
        creatinine_is_allowed, read_line, write)
    # Closed-world assumption: a skipped number is left out of the profile, never guessed.
    if weight is not None:
        patient["weight"] = weight
    if egfr is not None:
        patient["egfr"] = egfr
    if creatinine is not None:
        patient["creatinine"] = creatinine

    patient["pregnant"] = ask_yes_no("Is the patient pregnant?", read_line, write, "required, yes or no")
    patient["needs"] = ask_choices("Conditions to treat", condition_choices(), True, "4 5 3", read_line, write)
    patient["has"] = ask_choices("Existing conditions", attribute_choices(), False, "3 4", read_line, write)
    patient["allergies"] = ask_choices("Allergies", drug_choices(), False, "1 9", read_line, write)
    patient["current_medications"] = ask_choices("Medicines the patient already takes", drug_choices(),
                                                 False, "5", read_line, write)
    return patient


def main(read_line=input, write=print):
    """
    Run the entry: ask the questions, print the patient report (the same one as `python run_demo.py Patient3`),
    then offer the steps (how the planner searched and explained).
    read_line and write are the keyboard and the screen, unless a test gives others.
    Pressing Ctrl+C (KeyboardInterrupt) or Ctrl+D (EOFError, the end of the typed input) at any question stops
    the program cleanly with "No plan was made." instead of a Python error (decision 28).
    """
    try:
        patient = enter_patient(read_line, write)
        if patient is None:
            return
        write("")
        write("\n".join(planner.patient_report(patient)))
        if planner.plan(patient)["message"] is not None:
            return
        write("")
        if ask_yes_no("Show the steps (how the planner searched and explained)?", read_line, write):
            write("\n".join(planner.steps_report(patient)))
    except (KeyboardInterrupt, EOFError):
        write("")   # an empty line, so the message does not run on from the question
        write("No plan was made.")


if __name__ == "__main__":
    main()
