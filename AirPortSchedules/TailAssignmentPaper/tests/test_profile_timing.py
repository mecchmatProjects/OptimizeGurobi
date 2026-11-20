from experiments.generate_profile_timing import (
    build_heterogeneous_instance,
    build_instance,
    build_option_a_overnight_instance,
)
from src.benchmark_validation import (
    certify_option_a_input,
    certify_option_b_input,
    validate_benchmark_certificate,
)


def test_profile_timing_generator_is_deterministic_and_certified():
    first, first_certificate = build_instance(3, 4, 0)
    repeated, repeated_certificate = build_instance(3, 4, 0)
    other, other_certificate = build_instance(3, 4, 1)

    assert first == repeated
    assert first_certificate == repeated_certificate
    assert first["Cost_Matrix"] != other["Cost_Matrix"]
    assert certify_option_b_input(first)["status"] == "SUPPORTED"
    assert certify_option_b_input(other)["status"] == "SUPPORTED"
    for instance, certificate in (
        (first, first_certificate),
        (other, other_certificate),
    ):
        report = validate_benchmark_certificate(
            instance,
            certificate,
            capacity_semantics="simultaneous",
            strict_a_hour_limit=True,
        )
        assert report["status"] == "PASS"


def test_heterogeneous_profile_timing_generator_is_certified():
    first, first_certificate = build_heterogeneous_instance(10, 7, 0)
    repeated, repeated_certificate = build_heterogeneous_instance(10, 7, 0)

    assert first == repeated
    assert first_certificate == repeated_certificate
    assert len([airport for airport, capacity in first["Station_Capacity"].items()
                if capacity > 1]) >= 2
    assert first["Parameters"]["Topology"] == "shared_spokes_multi_hub"
    assert certify_option_b_input(first)["status"] == "SUPPORTED"
    report = validate_benchmark_certificate(
        first,
        first_certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    assert report["status"] == "PASS"
    assert report["milp_representable"]


def test_option_a_overnight_generator_crosses_midnight_and_limits_option_b():
    instance, certificate = build_option_a_overnight_instance(4, 4, 0)

    assert any(int(flight[3] // 1440) != int(flight[4] // 1440)
               for flight in instance["Flights"])
    assert instance["Parameters"]["Cross_Midnight_Flights"] is True
    assert certify_option_a_input(instance)["status"] == "SUPPORTED"
    option_b = certify_option_b_input(instance)
    assert option_b["status"] == "UNSUPPORTED"
    assert any("crosses a day boundary" in error for error in option_b["errors"])
    report = validate_benchmark_certificate(
        instance,
        certificate,
        capacity_semantics="simultaneous",
        strict_a_hour_limit=True,
    )
    assert report["status"] == "PASS"
    assert report["milp_representable"]
