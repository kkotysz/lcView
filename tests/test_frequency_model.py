from lcview.core.frequency_model import FrequencyHistory, FrequencyModel
from lcview.core.combinations import classify_peak, rayleigh_resolution


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


def test_classify_peak_combination():
    model = FrequencyModel.empty()
    model.add_independent(1.0)
    model.add_independent(2.0)
    candidate = classify_peak(3.0, 0.2, model, baseline=100.0)
    assert candidate.kind == "combination"
    assert candidate.coefficients == (1, 1)
    assert rayleigh_resolution(100.0) == 0.005
