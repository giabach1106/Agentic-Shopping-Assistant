from __future__ import annotations

from app.orchestrator.domain_support import constraint_match_score, title_matches_constraints


def test_standing_desk_rejects_accessory_title() -> None:
    constraints = {
        "category": "standing desk",
        "widthMinInches": 55,
    }

    assert not title_matches_constraints(
        "VIVO Under Desk 36 inch Mesh Net Cable Management with Power Strip Holder",
        constraints,
    )
    assert constraint_match_score(
        "VIVO Under Desk 36 inch Mesh Net Cable Management with Power Strip Holder",
        constraints,
    ) == 0


def test_standing_desk_penalizes_unknown_width_but_accepts_real_desk() -> None:
    constraints = {
        "category": "standing desk",
        "widthMinInches": 55,
    }

    assert title_matches_constraints(
        "FEZIBO Electric Standing Desk Workstation with Drawers",
        constraints,
    )
    assert constraint_match_score(
        "FEZIBO Electric Standing Desk Workstation with Drawers",
        constraints,
    ) > 0

