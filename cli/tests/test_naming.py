from __future__ import annotations

import pytest

from claudeforanything.naming import check_plugin_name, check_skill_name, plugin_kind


@pytest.mark.parametrize(
    "name",
    ["claude-for-photo-editing", "crm-for-claude", "claude-for-3d-modeling"],
)
def test_valid_plugin_names(name: str) -> None:
    assert check_plugin_name(name) == []


@pytest.mark.parametrize(
    "name",
    [
        "photo-editing",  # neither convention
        "claude-for-",  # no action
        "claude--for-x",  # consecutive hyphens
        "-crm-for-claude",  # leading hyphen
        "CRM-for-claude",  # uppercase
        "claude-for-photo-editing-for-claude",  # both conventions
    ],
)
def test_rejected_plugin_names(name: str) -> None:
    assert check_plugin_name(name), f"{name!r} should have been rejected"


def test_saas_named_plugin_passes_shape_check() -> None:
    """The shape is valid even though the name is wrong.

    `claude-for-photoshop` names a product rather than an action. No regex can
    catch that, which is why review-plugin asks a human to check it by hand.
    """
    assert check_plugin_name("claude-for-photoshop") == []


@pytest.mark.parametrize("name", ["new-plugin", "a", "a1-b2"])
def test_valid_skill_names(name: str) -> None:
    assert check_skill_name(name) == []


@pytest.mark.parametrize("name", ["-x", "x-", "a--b", "Ab", "", "x" * 65])
def test_rejected_skill_names(name: str) -> None:
    assert check_skill_name(name)


def test_skill_names_are_not_held_to_the_plugin_convention() -> None:
    assert check_skill_name("add-contact") == []
    assert check_plugin_name("add-contact")


def test_plugin_kind() -> None:
    assert plugin_kind("claude-for-photo-editing") == "an action Claude performs"
    assert plugin_kind("crm-for-claude") == "a tool Claude uses"
