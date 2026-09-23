"""Built-in risk-of-bias resources match their documented instrument structures."""

from dataclasses import FrozenInstanceError

import pytest

from app.rob import BUILTIN_TEMPLATES, TEMPLATES_BY_KEY, get_template


def test_all_required_templates_are_loaded_once_in_stable_order() -> None:
    assert tuple(template.key for template in BUILTIN_TEMPLATES) == (
        "rob2",
        "robins_i",
        "nos",
        "quadas2",
    )
    assert tuple(TEMPLATES_BY_KEY) == ("rob2", "robins_i", "nos", "quadas2")


@pytest.mark.parametrize(
    ("tool_key", "variant_key", "domain_keys"),
    [
        (
            "rob2",
            "parallel_assignment",
            (
                "randomisation_process",
                "deviations_from_intended_interventions",
                "missing_outcome_data",
                "measurement_of_outcome",
                "selection_of_reported_result",
            ),
        ),
        (
            "robins_i",
            "original_2016",
            (
                "confounding",
                "selection_of_participants",
                "classification_of_interventions",
                "deviations_from_intended_interventions",
                "missing_data",
                "measurement_of_outcomes",
                "selection_of_reported_result",
            ),
        ),
        (
            "quadas2",
            "diagnostic_accuracy",
            ("patient_selection", "index_test", "reference_standard", "flow_and_timing"),
        ),
    ],
)
def test_standard_tool_domain_order(
    tool_key: str, variant_key: str, domain_keys: tuple[str, ...]
) -> None:
    template = get_template(tool_key)
    variant = next(item for item in template.variants if item.key == variant_key)
    assert tuple(domain.key for domain in variant.domains) == domain_keys
    assert all(domain.signalling_questions for domain in variant.domains)


def test_rob2_and_robins_i_use_distinct_official_judgement_scales() -> None:
    rob2_axis = get_template("rob2").variants[0].domains[0].judgement_axes[0]
    robins_axis = get_template("robins_i").variants[0].domains[0].judgement_axes[0]

    assert tuple(choice.key for choice in rob2_axis.allowed_judgements) == (
        "low",
        "some_concerns",
        "high",
    )
    assert tuple(choice.key for choice in robins_axis.allowed_judgements) == (
        "low",
        "moderate",
        "serious",
        "critical",
        "no_information",
    )


def test_nos_keeps_cohort_and_case_control_star_variants_separate() -> None:
    template = get_template("nos")
    assert tuple(variant.key for variant in template.variants) == ("cohort", "case_control")
    for variant in template.variants:
        assert tuple(domain.key for domain in variant.domains) == (
            "selection",
            "comparability",
            "outcome" if variant.key == "cohort" else "exposure",
        )
        maximums = tuple(
            len(domain.judgement_axes[0].allowed_judgements) - 1 for domain in variant.domains
        )
        assert maximums == (4, 2, 3)


def test_quadas2_models_applicability_only_for_first_three_domains() -> None:
    domains = get_template("quadas2").variants[0].domains
    assert [tuple(axis.key for axis in domain.judgement_axes) for domain in domains] == [
        ("risk_of_bias", "applicability"),
        ("risk_of_bias", "applicability"),
        ("risk_of_bias", "applicability"),
        ("risk_of_bias",),
    ]


def test_versions_and_sources_make_deliberate_legacy_choices_explicit() -> None:
    assert get_template("rob2").version == "22 August 2019"
    assert get_template("robins_i").version == "2016"
    assert "draft" in get_template("robins_i").content_note
    assert get_template("quadas2").version == "2011"
    assert "QUADAS-3" in get_template("quadas2").content_note
    assert all(template.source_url.startswith("https://") for template in BUILTIN_TEMPLATES)


def test_templates_are_deeply_immutable() -> None:
    template = get_template("rob2")
    with pytest.raises(FrozenInstanceError):
        template.name = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        TEMPLATES_BY_KEY["changed"] = template  # type: ignore[index]


def test_unknown_template_key_is_not_silently_fallbacked() -> None:
    with pytest.raises(KeyError):
        get_template("unknown")


def test_template_key_must_be_a_plain_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        get_template(42)  # type: ignore[arg-type]
