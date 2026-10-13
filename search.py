"""
The depth-first search with backtracking, and the ranking of the safe regimens.

The search builds a regimen one condition at a time, in the order of the patient's "needs" list.
After each new drug it runs the forward chainer (kb.chain_regimen). If the chainer concludes
InvalidRegimen, that branch is a dead end: the search backs up and tries the next drug.
This is a course project, not a clinical tool.
"""
import kb
import kb_facts as facts


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------

def depth_first_search(patient, index, chosen, record):
    """
    SEARCH(index, chosen) from SPEC section 7.
    index   which condition in patient["needs"] we are choosing a drug for now
    chosen  the drugs chosen so far, one for each earlier condition
    record  a dict that collects the results: the complete regimens, the dead ends, the number of
            states generated, and every step in the order it was taken (to show how the search went)
    """
    needs = patient["needs"]
    if index == len(needs):
        # Every condition has a drug, and every step on the way passed the checks.
        record["complete_regimens"].append(tuple(chosen))
        return
    for drug in facts.CONDITIONS[needs[index]]:
        record["states_generated"] += 1
        attempt = chosen + [drug]
        attempt_facts = kb.chain_regimen(patient, attempt)
        if ("InvalidRegimen", patient["name"]) in attempt_facts:
            # Dead end: keep the reasons so they can be explained, then try the next drug (backtracking).
            rejected_facts = kb.facts_named(attempt_facts, "Rejected")
            record["dead_ends"].append((tuple(attempt), rejected_facts))
            record["steps"].append((tuple(attempt), "not suitable", rejected_facts))
        else:
            if len(attempt) == len(needs):
                record["steps"].append((tuple(attempt), "complete", set()))
            else:
                record["steps"].append((tuple(attempt), "fine so far", set()))
            depth_first_search(patient, index + 1, attempt, record)


def run_search(patient):
    """Start the search at the root (no drugs chosen). The root counts as one state."""
    record = {"complete_regimens": [], "dead_ends": [], "states_generated": 1, "steps": []}
    depth_first_search(patient, 0, [], record)
    return record


# ---------------------------------------------------------------------------
# Scoring and ranking
# ---------------------------------------------------------------------------
# The weights are project choices, not clinical ratings (see kb_facts.py):
# a Moderate interaction flag costs 3 points, any other flag costs 1, and a dose note costs 0.

def score_regimen(patient, regimen):
    """
    Chain the complete regimen and count its concerns.
    Returns (points, flag_count, dose_note), where dose_note is True if Apixaban gets the dose note.
    """
    regimen_facts = kb.chain_regimen(patient, list(regimen))
    points = 0
    flag_count = 0
    for fact in kb.facts_named(regimen_facts, "Flagged"):
        reason = fact[3]
        flag_count += 1
        if isinstance(reason, tuple):
            # The reason is ("InteractionWith", other_drug): a Moderate interaction.
            points += facts.MODERATE_INTERACTION_POINTS
        else:
            points += facts.OTHER_FLAG_POINTS
    dose_note = len(kb.facts_named(regimen_facts, "DoseNote")) > 0
    return points, flag_count, dose_note


def rank_key(row):
    """Sort by points, then number of flags, then dose note (False before True), then the regimen itself."""
    regimen, points, flag_count, dose_note = row
    return (points, flag_count, dose_note, regimen)


def rank_regimens(patient, regimens):
    """Score every safe complete regimen and sort them, best first."""
    ranked = []
    for regimen in regimens:
        points, flag_count, dose_note = score_regimen(patient, regimen)
        ranked.append((regimen, points, flag_count, dose_note))
    ranked.sort(key=rank_key)
    return ranked


def find_winners(ranked):
    """The regimens tied for best: the same points, flag count and dose note as the first one."""
    winners = []
    if len(ranked) == 0:
        return winners
    best_regimen, best_points, best_flag_count, best_dose_note = ranked[0]
    for regimen, points, flag_count, dose_note in ranked:
        if (points, flag_count, dose_note) == (best_points, best_flag_count, best_dose_note):
            winners.append(regimen)
    return winners


# ---------------------------------------------------------------------------
# Counting and blocked conditions
# ---------------------------------------------------------------------------

def count_regimens(needs):
    """How many complete regimens exist: the number of candidates multiplied together."""
    total = 1
    for condition in needs:
        total = total * len(facts.CONDITIONS[condition])
    return total


def full_tree_size(needs):
    """
    How many states the full search tree has with no pruning, root included.
    With two candidates per condition this is 2 ** (number of conditions + 1) - 1.
    """
    total = 1
    states_on_this_level = 1
    for condition in needs:
        states_on_this_level = states_on_this_level * len(facts.CONDITIONS[condition])
        total = total + states_on_this_level
    return total


def find_blocked_conditions(patient):
    """The conditions where every candidate drug is rejected even on its own."""
    blocked = []
    for condition in patient["needs"]:
        allowed_drugs = []
        for drug in facts.CONDITIONS[condition]:
            drug_facts = kb.chain_regimen(patient, [drug])
            if ("InvalidRegimen", patient["name"]) not in drug_facts:
                allowed_drugs.append(drug)
        if len(allowed_drugs) == 0:
            blocked.append(condition)
    return blocked


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def search_and_rank(patient):
    """
    Run the search and the ranking for one patient. Returns the same fields as
    reference_evaluator.plan_reference, plus "dead_ends" (the rejected branches, for explaining) and
    "steps" (every step of the search in order, for showing how the search went).
    """
    record = run_search(patient)
    ranked = rank_regimens(patient, record["complete_regimens"])
    regimen_count = count_regimens(patient["needs"])
    blocked = []
    if len(ranked) == 0:
        blocked = find_blocked_conditions(patient)
    return {
        "regimen_count": regimen_count,
        "invalid_count": regimen_count - len(ranked),
        "ranked": ranked,
        "winners": find_winners(ranked),
        "blocked_conditions": blocked,
        "states_generated": record["states_generated"],
        "full_tree_size": full_tree_size(patient["needs"]),
        "dead_ends": record["dead_ends"],
        "steps": record["steps"],
    }
