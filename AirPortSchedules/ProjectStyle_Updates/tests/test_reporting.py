import sys
import sys
import types
from pathlib import Path

from model_builder import build_model_from_data
from Model_28Oct import write_text_report, plot_schedule_from_model


def make_dummy_matplotlib():
    # create dummy matplotlib.pyplot and matplotlib.patches modules
    mod_pyplot = types.ModuleType('matplotlib.pyplot')

    class DummyAx:
        def barh(self, *a, **k):
            pass

        def text(self, *a, **k):
            pass

        def set_yticks(self, *a, **k):
            pass

        def set_yticklabels(self, *a, **k):
            pass

        def set_xlabel(self, *a, **k):
            pass

        def set_title(self, *a, **k):
            pass

        def legend(self, *a, **k):
            pass

    def subplots(figsize=(10, 6)):
        return (object(), DummyAx())

    def savefig(*a, **k):
        return None

    mod_pyplot.subplots = subplots
    mod_pyplot.savefig = savefig
    # no-op tight_layout used by plotting helper
    mod_pyplot.tight_layout = lambda *a, **k: None

    mod_patches = types.ModuleType('matplotlib.patches')

    class Patch:
        def __init__(self, *a, **k):
            pass

    mod_patches.Patch = Patch

    sys.modules['matplotlib'] = types.ModuleType('matplotlib')
    sys.modules['matplotlib.pyplot'] = mod_pyplot
    sys.modules['matplotlib.patches'] = mod_patches


def test_write_text_report_and_plot(tmp_path):
    # construct minimal data
    data = {
        'Airports': ['A', 'B'],
        'Nbflight': 2,
        'Flights': [
            {
                'flight': 1,
                'origin': 'A',
                'destination': 'B',
                'departureTime': 0.0,
                'arrivalTime': 60.0,
            },
            {
                'flight': 2,
                'origin': 'B',
                'destination': 'A',
                'departureTime': 120.0,
                'arrivalTime': 180.0,
            },
        ],
        'Aircrafts': [0, 1],
        'cost': [[10, 20], [30, 40]],
        'a0': {0: 'A', 1: 'B'},
    }

    model, FlightData, Days, AircraftInit = build_model_from_data(data)

    # set assignments manually
    # first fix all x variables to 0 so value() calls won't fail, then set the
    # desired assignments to 1
    for i in model.F:
        for j in model.P:
            model.x[i, j].fix(0)
    # assign flight1->plane0 and flight2->plane1
    model.x[1, 0].fix(1)
    model.x[2, 1].fix(1)

    # ensure other maintenance-related variables are numeric to avoid
    # value() raising on uninitialized Vars inside write_text_report
    if hasattr(model, 'y'):
        for k in list(model.y.keys()):
            model.y[k].fix(0)
    if hasattr(model, 'z'):
        for k in list(model.z.keys()):
            model.z[k].fix(0)
    if hasattr(model, 'mega_check'):
        for k in list(model.mega_check.keys()):
            model.mega_check[k].fix(0)

    # prepare dummy results object (no solver)
    results = object()

    out_txt = tmp_path / "report.txt"
    write_text_report(model, results, FlightData, str(out_txt))

    assert out_txt.exists()
    content = out_txt.read_text()
    assert "Aircraft Assignment and Maintenance Report" in content

    # prepare dummy matplotlib modules and call plot
    make_dummy_matplotlib()
    events = plot_schedule_from_model(model, FlightData, None)
    assert isinstance(events, list)
    # we expect at least two flight events
    flight_events = [e for e in events if e['type'] == 'flight']
    assert len(flight_events) >= 2