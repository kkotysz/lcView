import time

from lcview.core.frequency_model import FrequencyHistory, FrequencyModel
from lcview.core.combinations import (
    candidates_from_peaks,
    classify_peak,
    clear_combination_cache,
    combination_cache_info,
    matching_combinations,
    rayleigh_resolution,
)


def test_freq_round_trip_and_mutation():
    model = FrequencyModel.from_freq_text(
        """\
    2    3
    1.000000
    2.000000
       1   0
       0   1
       1   1
"""
    )
    assert model.bases == [1.0, 2.0]
    assert model.frequency_for_term((1, 1)) == 3.0
    assert "1   1" in model.to_freq_text()

    model.add_independent(4.0)
    combo_index = model.add_combination((1, -1, 1))
    assert model.frequency_for_term((1, -1, 1)) == 3.0
    model.set_term_enabled(combo_index, False)
    assert (1, -1, 1) not in model.active_terms()


def test_frequency_history_undo_redo():
    history = FrequencyHistory()
    history.snapshot()
    history.current.add_independent(1.5)
    assert history.current.bases == [1.5]
    assert history.undo()
    assert history.current.bases == []
    assert history.redo()
    assert history.current.bases == [1.5]


def test_clear_frequency_model():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_combination((2,))
    model.set_term_enabled(1, False)
    model.clear()
    assert model.bases == []
    assert model.terms == []
    assert model.disabled_terms == set()


def test_remove_base_removes_identity_and_dependent_terms():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.0)
    model.add_combination((1, 1))

    model.remove_base(0)

    assert model.bases == [2.0]
    assert model.terms == [(1,)]


def test_set_base_frequency_updates_dependent_term_frequencies():
    model = FrequencyModel.empty()
    model.add_independent(2.0)
    model.add_independent(3.0)
    combination = (1, 1)
    model.add_combination(combination)

    model.set_base_frequency(0, 1.0)

    assert model.bases == [1.0, 3.0]
    assert model.frequency_for_term((1, 0)) == 1.0
    assert model.frequency_for_term(combination) == 4.0


def test_classify_peak_combination():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.0)
    candidate = classify_peak(3.0, 0.2, model, baseline=100.0)
    assert candidate.kind == "combination"
    assert candidate.coefficients == (1, 1)
    assert rayleigh_resolution(100.0) == 0.005


def test_classify_peak_can_limit_combination_label_bases():
    model = FrequencyModel.empty()
    for frequency in (1.0, 2.0, 2.98):
        model.add_independent(frequency)

    full = classify_peak(4.98, 0.2, model, baseline=1000.0, start_frequency=0.0, end_frequency=10.0)
    limited = classify_peak(
        4.98,
        0.2,
        model,
        baseline=1000.0,
        start_frequency=0.0,
        end_frequency=10.0,
        combination_base_indexes=(0, 1),
    )
    selected_late_bases = classify_peak(
        4.98,
        0.2,
        model,
        baseline=1000.0,
        start_frequency=0.0,
        end_frequency=10.0,
        combination_base_indexes=(1, 2),
    )

    assert full.coefficients == (0, 1, 1)
    assert full.label == "f2 + f3"
    assert limited.kind == "independent"
    assert limited.label == "new"
    assert limited.coefficients == (0, 0, 0)
    assert selected_late_bases.coefficients == (0, 1, 1)


def test_fast_classification_matches_harmonics_two_and_simple_three_terms():
    harmonic_model = FrequencyModel.empty()
    harmonic_model.add_independent(1.5)
    harmonic = classify_peak(3.0, 0.2, harmonic_model, baseline=1000.0, start_frequency=0.0, end_frequency=10.0)
    assert harmonic.kind == "harmonic"
    assert harmonic.coefficients == (2,)

    two_model = FrequencyModel.empty()
    two_model.add_independent(1.0)
    two_model.add_independent(2.0)
    two_term = classify_peak(3.0, 0.2, two_model, baseline=1000.0, start_frequency=0.0, end_frequency=10.0)
    assert two_term.kind == "combination"
    assert two_term.coefficients == (1, 1)

    three_model = FrequencyModel.empty()
    for frequency in (1.0, 2.3, 4.1):
        three_model.add_independent(frequency)
    three_term = classify_peak(5.4, 0.2, three_model, baseline=1000.0, start_frequency=0.0, end_frequency=10.0)
    assert three_term.kind == "combination"
    assert three_term.coefficients == (-1, 1, 1)


def test_fast_classification_does_not_generate_four_term_matches_by_default():
    model = FrequencyModel.empty()
    for frequency in (1.01, 2.03, 3.07, 4.11):
        model.add_independent(frequency)

    matches = matching_combinations(10.22, model, baseline=1000.0, start_frequency=0.0, end_frequency=12.0, limit=50)

    assert (1, 1, 1, 1) not in [coefficients for coefficients, _, _ in matches]
    assert all(sum(1 for value in coefficients if value) <= 3 for coefficients, _, _ in matches)


def test_fast_classification_ignores_negative_bases_for_candidate_generation():
    model = FrequencyModel.empty()
    model.add_independent(-1.0)
    model.add_independent(2.0)

    candidate = classify_peak(1.0, 0.2, model, baseline=1000.0, start_frequency=0.0, end_frequency=5.0)

    assert candidate.kind == "independent"
    assert candidate.label == "new"
    assert candidate.coefficients == (0, 0)


def test_candidates_for_many_bases_reuse_combination_index():
    clear_combination_cache()
    model = FrequencyModel.empty()
    for frequency in [2.831, 2.769, 2.665, 1.974, 2.509, 2.972, 2.545]:
        model.add_independent(frequency)
    peaks = [
        {"frequency": 2.831 + index * 0.001, "amplitude": 1.0 / (index + 1), "snr": 4.0}
        for index in range(8)
    ]

    candidates = candidates_from_peaks(peaks, model, baseline=278.0)
    cache = combination_cache_info()
    candidates_from_peaks(peaks, model, baseline=278.0)
    cache_after_repeat = combination_cache_info()

    assert len(candidates) == len(peaks)
    assert cache.misses == 1
    assert cache.hits == 0
    assert cache_after_repeat.misses == 1
    assert cache_after_repeat.hits == 1


def test_candidates_for_many_bases_are_fast_enough_for_gui_smoke():
    clear_combination_cache()
    model = FrequencyModel.empty()
    for frequency in [2.710707, 2.80118, 2.856856, 2.130927, 3.823947, 4.710507, 14.319544, 0.236658, 2.603257, -1.225853, 4.430682, 2.304929, 4.943379, 0.539251, 5.812692]:
        model.add_independent(frequency)
    peaks = [
        {"frequency": 0.5 + index * 0.17, "amplitude": 1.0 / (index + 1), "snr": 4.0}
        for index in range(50)
    ]

    started = time.perf_counter()
    candidates = candidates_from_peaks(peaks, model, baseline=278.0, start_frequency=0.0, end_frequency=10.0)
    elapsed = time.perf_counter() - started

    assert len(candidates) == len(peaks)
    assert elapsed < 0.5
