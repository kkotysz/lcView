from pathlib import Path

from lcview.legacy.parsers import read_freq, read_freq_poss, read_resid_max


def test_legacy_parsers(tmp_path: Path):
    freq = tmp_path / "freq"
    freq.write_text("    1    1\n    2.000000\n   1\n")
    model = read_freq(freq)
    assert model.bases == [2.0]
    assert model.terms == [(1,)]

    resid = tmp_path / "resid.max"
    resid.write_text("% header\n  1 2.000000 0.500000 0.120000 4.5\n")
    rows = read_resid_max(resid)
    assert rows[0]["frequency"] == 2.0
    assert rows[0]["snr"] == 4.5

    poss = tmp_path / "freq.poss"
    poss.write_text("  1.20      2    2    3  0.0010   1   1\n")
    combos = read_freq_poss(poss)
    assert combos[0]["coefficients"] == (1, 1)
