from improved_model import build_full_model


def _minimal_data():
    # Minimal instance compatible with model_builder.build_model_from_data
    return {
        'Airports': ['A'],
        'Aircrafts': [1],
        'Flight': [
            {'flight': 1, 'origin': 'A', 'destination': 'A', 'departureTime': 0, 'arrivalTime': 60}
        ],
        'Nbflight': 1,
        'cost': [[0]],
        'a0': {1: 'A'}
    }


def test_each_toggle_creates_or_hides_constraints():
    data = _minimal_data()

    flag_to_attr = {
        'add_equipment_turn': 'equipment_turn_constraints',
        'enable_z_check': 'z_check',
        'enable_maint_spacing': 'maint_spacing',
        'enable_maint_spacing2': 'maint_spacing2',
        'enable_maint_cumulative': 'maint_cumulative',
        'enable_maint_cumulative_start': 'maint_cumulative_start',
        'enable_maint_checks_days': 'maint_checks_days',
        'enable_maint_capacity': 'maint_capacity',
        'enable_maint_hierarchy': 'maint_hierarchy',
        'enable_overlap_checks': 'flight_overlap',
    }

    # Baseline: all enabled -> attributes should exist (when relevant)
    model, _, _, _ = build_full_model(data, add_maint_block=True,
                                     add_equipment_turn=True,
                                     enable_z_check=True,
                                     enable_maint_spacing=True,
                                     enable_maint_spacing2=True,
                                     enable_maint_cumulative=True,
                                     enable_maint_cumulative_start=True,
                                     enable_maint_block_checks=True,
                                     enable_maint_checks_days=True,
                                     enable_maint_capacity=True,
                                     enable_maint_link=True,
                                     enable_maint_hierarchy=True,
                                     enable_overlap_checks=True)

    for attr in flag_to_attr.values():
        assert hasattr(model, attr)

    # Now test disabling each flag hides the attribute added by improved_model
    for flag, attr in flag_to_attr.items():
        kwargs = {
            'add_maint_block': True,
            'add_equipment_turn': True,
            'enable_z_check': True,
            'enable_maint_spacing': True,
            'enable_maint_spacing2': True,
            'enable_maint_cumulative': True,
            'enable_maint_cumulative_start': True,
            'enable_maint_block_checks': True,
            'enable_maint_checks_days': True,
            'enable_maint_capacity': True,
            'enable_maint_link': True,
            'enable_maint_hierarchy': True,
            'enable_overlap_checks': True,
        }
        # disable one
        kwargs[flag] = False
        model2, _, _, _ = build_full_model(data, **kwargs)
        assert not hasattr(model2, attr)
