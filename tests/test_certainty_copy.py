"""Near-guarantee / certainty language must never reach public copy, on any
bet type. Regression: 2026-11-06 a 1.75 INVESTOR pick went to Instagram with
'about as close to a sure thing as sport gets' because the RG certainty
phrases were only enforced for GAMBLER_BET."""
import copy_validator
import render_brand_templates
import generate_pick


def test_certainty_phrases_blocked_for_investor():
    v = copy_validator.check_gambler_rg("This one's about as close to a sure thing as sport gets", "INVESTOR_BET")
    assert any("sure thing" in m for m in v), v


def test_certainty_phrases_blocked_for_all_bet_types():
    for bet_type in ("INVESTOR_BET", "PUNTER_BET", "GAMBLER_BET"):
        v = copy_validator.check_gambler_rg("lock of the day right here", bet_type)
        assert v, f"no violation for {bet_type}"


def test_gambler_chase_phrases_still_blocked():
    v = copy_validator.check_gambler_rg("go all in and chase it", "GAMBLER_BET")
    assert any("GAMBLER_BET" in m for m in v), v


def test_shipped_openers_pass_certainty_check():
    for bet_type, opener in generate_pick.BET_TYPE_OPENERS.items():
        v = copy_validator.check_gambler_rg(opener, bet_type)
        assert not v, f"{bet_type} opener fails certainty check: {v}"


def test_risk_tag_never_falls_through_to_template_default():
    # 2026-11-06: build_props left riskTag unset, so the Betslip Night
    # template rendered its schema default "LOW RISK" beside the pick's real
    # RISKY_PICK chip on the Avalanche breakdown card. The tag must always be
    # explicitly suppressed; the truthful risk signal stays in riskTagline.
    props = render_brand_templates.build_props({
        "match": "Colorado Avalanche vs Nashville Predators",
        "sport": "NHL", "selection": "Colorado Avalanche",
        "market": "Head to Head", "odds": 1.75,
        "bet_type": "INVESTOR_BET", "risk": "RISKY_PICK",
        "confidence_label": "MODERATE", "final_explanation": "Form backs it.",
    })
    assert props["riskTag"] == ""
    assert "Risky Pick" in props["riskTagline"]
    assert "Moderate confidence" in props["riskTagline"]
