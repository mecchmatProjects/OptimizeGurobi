import pytest
from model_params import normalize_params, Params


def test_normalize_defaults():
    p = normalize_params(None, None)
    assert isinstance(p, Params)
    assert 'Acheck' in p.All_Check_List
    assert p.Mbig == 10**6


def test_normalize_from_dict_override():
    raw = {'All_Check_days': {'Acheck': 10}}
    p = normalize_params(raw, None)
    assert p.All_Check_days['Acheck'] == 10


def test_normalize_from_data():
    data = {'All_Check_durations_days': {'Acheck': 7}}
    p = normalize_params(None, data)
    assert p.All_Check_durations_days['Acheck'] == 7


def test_validate_params_good():
    p = normalize_params(None, None)
    # should not raise
    from model_params import validate_params
    validate_params(p)


def test_validate_params_bad():
    p = normalize_params(None, None)
    p.All_Check_List = []
    from model_params import validate_params
    import pytest
    with pytest.raises(ValueError):
        validate_params(p)
