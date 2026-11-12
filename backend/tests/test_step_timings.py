"""Batch cook's step timings guessed from a step's words (0.8 wave 6, B1; cabledrawer 28 Oct)."""

import pytest

from mealwright import step_timings, step_waits
from mealwright.models import RecipeStep


def g(text: str, wait: step_waits.Wait | None = None) -> tuple[str, int, str]:
    found = step_timings.guess(text, wait)
    return found.hands, found.minutes, found.equipment


def test_pressure_cooking_waits_in_the_pressure_cooker() -> None:
    assert g("Wash the toor dal and pressure cook it with turmeric for 3 whistles.") == (
        "waiting",
        15,
        "pressure",
    )
    assert g("Pressure cook the dal for 20 minutes.") == ("waiting", 20, "pressure")
    assert g("Pressure cook the chickpeas until soft.") == ("waiting", 20, "pressure")


def test_simmering_and_boiling_wait_on_a_hob_ring() -> None:
    assert g("Simmer the sambar for 10 to 12 minutes.") == ("waiting", 12, "hob")
    assert g("Boil the vegetables in the tamarind water with sambar powder until soft.") == (
        "waiting",
        15,
        "hob",
    )
    assert g("Bring to a boil, then simmer for 1 hour 30 minutes.") == ("waiting", 90, "hob")


def test_frying_and_tempering_keep_the_hands_busy_on_a_hob_ring() -> None:
    assert g("Heat the oil and fry the onions for 5 minutes.") == ("hands", 5, "hob")
    assert g("Temper the mustard seeds and curry leaves in ghee.") == ("hands", 5, "hob")
    assert g("Sauté the garlic until golden.") == ("hands", 5, "hob")


def test_a_chettinad_step_with_two_times_adds_them_up() -> None:
    assert g("Fry the onions for 2 minutes, then add the chicken and cook for 10 minutes.")[1] == 12
    assert g("Add the chicken pieces and fry until the masala smells good, 8-10 minutes.") == (
        "hands",
        10,
        "hob",
    )


def test_chopping_grinding_mixing_and_kneading_are_hands_on_with_nothing() -> None:
    assert g("Chop the onion, tomato and drumsticks.") == ("hands", 5, "none")
    assert g("Grind the coconut, fennel and poppy seeds to a smooth paste.") == (
        "hands",
        5,
        "none",
    )
    assert g("Mix the flour, salt and water and knead for 10 minutes.") == ("hands", 10, "none")


def test_a_soak_counts_as_waiting_with_nothing() -> None:
    assert g("Soak the tamarind in warm water for 10 minutes.") == ("waiting", 10, "none")
    assert g("Soak the rice and urad dal for 4 to 5 hours.") == ("waiting", 300, "none")


def test_the_wait_from_wave_5_counts_as_waiting_and_gives_its_minutes() -> None:
    wait = step_waits.read_wait("Ferment the dosa batter overnight.")
    assert wait is not None
    assert g("Ferment the dosa batter overnight.", wait) == ("waiting", 720, "none")
    wait = step_waits.read_wait("Marinate the chicken for 2 hours.")
    assert wait is not None
    assert g("Marinate the chicken for 2 hours.", wait) == ("waiting", 120, "none")


def test_a_bake_waits_in_the_oven_and_a_dry_roast_in_a_pan_does_not() -> None:
    assert g("Preheat the oven to 180°C.")[2] == "oven"
    assert g("Bake for 35 to 40 minutes until a skewer comes out clean.") == (
        "waiting",
        40,
        "oven",
    )
    assert g("Roast the vegetables for 25 minutes.") == ("waiting", 25, "oven")
    assert g("Dry roast the cumin and coriander in a pan for 2 minutes.") == (
        "hands",
        2,
        "hob",
    )


def test_a_step_with_no_clue_is_hands_on_with_nothing() -> None:
    assert g("Garnish with coriander and serve.") == ("hands", 5, "none")
    assert g("") == ("hands", 5, "none")


def test_the_rest_of_something_is_not_resting() -> None:
    assert g("Add the rest of the stock.") == ("hands", 5, "none")


def test_a_very_long_step_is_read_in_part() -> None:
    assert g("Chop. " * 3000)[0] == "hands"


def _step(text: str, **set_by_hand: object) -> RecipeStep:
    return RecipeStep(
        household_id=1, recipe_id=1, position=0, kind="step", text=text, **set_by_hand
    )


def test_a_value_set_by_hand_wins_and_the_others_stay_guessed() -> None:
    timing = step_timings.of_step(_step("Simmer the sambar for 10 minutes.", timing_minutes=25))
    assert timing is not None
    assert (timing.hands, timing.minutes, timing.equipment) == ("waiting", 25, "hob")
    assert (timing.hands_guessed, timing.minutes_guessed, timing.equipment_guessed) == (
        True,
        False,
        True,
    )


def test_changing_the_words_changes_the_guess_but_never_a_hand_set_value() -> None:
    by_hand = {"timing_hands": "hands", "timing_equipment": "none"}
    before = step_timings.of_step(_step("Simmer for 10 minutes.", **by_hand))
    after = step_timings.of_step(_step("Pressure cook for 3 whistles.", **by_hand))
    assert before is not None and after is not None
    assert (before.hands, before.equipment, before.minutes) == ("hands", "none", 10)
    assert (after.hands, after.equipment, after.minutes) == ("hands", "none", 15)
    assert after.minutes_guessed


def test_a_heading_has_no_timing() -> None:
    heading = RecipeStep(household_id=1, recipe_id=1, position=0, kind="heading", text="Tadka")
    assert step_timings.of_step(heading) is None


def test_chillies_are_not_chilling() -> None:
    # B1 review r1 H1: "chill" matched "chillies", so chopping and tempering were waits.
    assert g("Chop the onions and green chillies.") == ("hands", 5, "none")
    assert g("Heat oil, add mustard seeds, curry leaves and dried red chillies.") == (
        "hands",
        5,
        "hob",
    )
    assert g("Dry roast the coriander seeds and red chillies in a pan") == ("hands", 5, "hob")
    assert g("Add chilli powder and stir.") == ("hands", 5, "none")
    assert g("Chill the dough for 30 minutes.") == ("waiting", 30, "none")
    assert g("Leave the kheer to chill.")[0] == "waiting"


def test_heat_or_cook_beside_add_still_uses_a_hob_ring() -> None:
    # B1 review r1 M2: "add" stopped heat and cook from counting as the hob.
    assert g("Heat oil in a pan and add the onions.") == ("hands", 5, "hob")
    assert g("Add the tomatoes and cook until soft.") == ("hands", 5, "hob")
    assert g("Add the dal to the kadai and stir.") == ("hands", 5, "hob")
    assert g("Add the cooking liquid and mix.")[2] == "none"


def test_a_pan_alone_is_not_a_hob_ring() -> None:
    # B1 review r2 M1: a tin or a pan that only holds food uses no hob ring.
    assert g("Pour into a loaf pan and chill for 4 hours.") == ("waiting", 240, "none")
    assert g("Let the cake cool in the pan for 10 minutes")[2] == "none"
    assert g("Pour the batter into the prepared pan.")[2] == "none"
    assert g("Heat oil in a pan and add the onions.")[2] == "hob"


# --- Whole-0.8 review fixes (RF3): C11 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("Cook for 1/2 hour", 30),
        ("Simmer for 1 1/2 hours.", 90),
        ("Cook for ½ hour", 30),
        ("Simmer for 1½ hours", 90),
        ("Rest for 3/4 hour", 45),
        ("Bake for 1/4 hour, then 10 minutes", 25),
        ("Stir in 1/2 cup of milk and simmer for 10 minutes", 10),
    ],
)
def test_a_fraction_before_the_unit_is_read_as_a_fraction(text: str, minutes: int) -> None:
    assert step_timings.times_in(text) == minutes


def test_a_wait_suggested_from_words_reads_a_fraction_too() -> None:
    found = step_waits.read_wait("Soak the beans for 1 1/2 hours.")
    assert found is not None and found.min_minutes == 90


def test_steps_that_differ_only_after_what_is_read_share_one_kept_guess() -> None:
    step_timings.guess.cache_clear()
    head = "Simmer gently for 10 minutes. " + "x" * 1500
    first = step_timings.guess(head[:1500] + "A" * 3000)
    second = step_timings.guess(head[:1500] + "B" * 3000)
    assert first == second
    info = step_timings.guess.cache_info()
    assert info.currsize == 1 and info.hits == 1
    assert info.maxsize is not None and info.maxsize <= 2048


def test_tidying_the_words_before_keeping_them_changes_no_guess() -> None:
    spaced = "Fry   2 minutes,\n then   simmer 10 minutes"
    assert step_timings.guess(spaced) == step_timings.guess("Fry 2 minutes, then simmer 10 minutes")


# F231 (cabledrawer 12 Nov): the Dosa Batter steps that read wrong on the 0.8.0 hand test.
DOSA_FERMENT = (
    "During colder season, ferment in the oven with the light on for 12 hours, "
    "or use the IP yogurt setting 8 hours."
)
DOSA_GRIND = (
    "Drain the soaked rice and dal and grind to a smooth & bubbly batter. "
    "Transfer to a large bowl or an instant pot steel insert."
)


def test_f231_alternatives_are_not_added_up_and_8_hours_is_8_hours() -> None:
    assert g(DOSA_FERMENT)[:2] == ("waiting", 720)  # the longer way, not 12 h + 8 h
    assert g("Use the IP yogurt setting 8 hours.") == ("waiting", 480, "none")
    assert g("Ferment 8 hours.") == ("waiting", 480, "none")
    assert g("Rest the dough for 30 minutes or 1 hour.")[1] == 60
    assert g("Fry for 2 minutes, then simmer for 10 minutes.")[1] == 12  # steps still add up


def test_f231_transfer_to_a_container_is_hands_on_and_names_no_appliance() -> None:
    assert g(DOSA_GRIND) == ("hands", 5, "none")
    assert g("Transfer the batter to an instant pot steel insert.") == ("hands", 5, "none")
    assert g("Pour the batter into the instant pot liner.") == ("hands", 5, "none")
    assert g("Move the dough to the inner pot of the instant pot.") == ("hands", 5, "none")
    assert g("Transfer the curry to a serving bowl.") == ("hands", 5, "none")


def test_f231_the_instant_pot_still_pressure_cooks_when_the_step_uses_it() -> None:
    assert g("Cook the dal in the instant pot for 15 minutes.")[2] == "pressure"
    assert g("Pressure cook in the instant pot for 3 whistles.")[2] == "pressure"
    assert g("Transfer to a pressure cooker and cook for 3 whistles.")[2] == "pressure"
