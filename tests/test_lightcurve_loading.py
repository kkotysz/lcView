from pathlib import Path

import numpy as np
import pytest

from lcview.core.lightcurve import read_light_curve, read_light_curve_table
from lcview.core.prewhitening import PrewhiteningEngine


def test_read_light_curve_selects_columns_from_csv_header(tmp_path: Path):
    path = tmp_path / "lc.csv"
    path.write_text("hjd,airmass,mag,err\n1.0,1.2,10.1,0.01\n2.0,1.3,10.4,0.02\n")

    table = read_light_curve_table(path)
    light_curve = read_light_curve(path, columns=(0, 2, 3))

    assert table.has_header
    assert table.delimiter_name == "comma"
    assert table.column_names == ["hjd", "airmass", "mag", "err"]
    assert light_curve.time.tolist() == [1.0, 2.0]
    assert light_curve.flux.tolist() == [10.1, 10.4]
    assert light_curve.error.tolist() == [0.01, 0.02]


def test_read_light_curve_supports_tsv_without_header(tmp_path: Path):
    path = tmp_path / "lc.tsv"
    path.write_text("1.0\t10.1\t0.01\t99\n2.0\t10.4\t0.02\t88\n")

    table = read_light_curve_table(path)
    light_curve = read_light_curve(path)

    assert not table.has_header
    assert table.delimiter_name == "tab"
    assert table.column_names == ["col1", "col2", "col3", "col4"]
    assert light_curve.to_array().tolist() == [[1.0, 10.1, 0.01], [2.0, 10.4, 0.02]]


def test_read_light_curve_supports_comment_header_and_whitespace(tmp_path: Path):
    path = tmp_path / "lc.dat"
    path.write_text("# time mag err sky\n1.0 10.1 0.01 100\n2.0 10.4 0.02 101\n")

    table = read_light_curve_table(path)
    light_curve = read_light_curve(path, columns=(0, 1, 2))

    assert table.has_header
    assert table.delimiter_name == "whitespace"
    assert table.column_names == ["time", "mag", "err", "sky"]
    assert np.allclose(light_curve.error, [0.01, 0.02])


def test_read_light_curve_requires_three_numeric_columns(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("time,label\n1,a\n")

    with pytest.raises(ValueError, match="Need at least three numeric columns"):
        read_light_curve(path)


def test_engine_from_file_uses_and_persists_selected_columns(tmp_path: Path):
    path = tmp_path / "lc.csv"
    path.write_text("time,flag,flux,error\n1.0,0,10.1,0.01\n2.0,1,10.4,0.02\n")

    engine = PrewhiteningEngine.from_file(path, columns=(0, 2, 3))

    assert engine.light_curve.flux.tolist() == [10.1, 10.4]
    assert engine.state.settings.time_column == 0
    assert engine.state.settings.flux_column == 2
    assert engine.state.settings.error_column == 3
