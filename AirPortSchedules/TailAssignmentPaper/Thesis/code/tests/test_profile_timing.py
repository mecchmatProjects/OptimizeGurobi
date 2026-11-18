from experiments.generate_profile_timing import build_instance
from src.benchmark_validation import certify_option_b_input, validate_benchmark_certificate


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
