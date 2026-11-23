# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Tests for the requirements coverage analyzer."""

from agents.requirements_validator import analyze_coverage


def test_reports_missing_requirement():
    """A requirement without a declared test is unverified."""
    requirements = """
1. Browse restaurants.
2. Add items to cart.
3. Reject invalid quantities.
"""

    test_code = '''
def test_browse():
    """FR1: Browse restaurants."""
    assert True

def test_add():
    """FR2: Add items to cart."""
    assert True

def test_other():
    assert True
'''

    result = analyze_coverage(requirements, test_code)

    assert result["total_requirements"] == 3
    assert result["declared_requirements"] == 2

    assert result["requirements"]["FR1"]["status"] == "declared"
    assert result["requirements"]["FR2"]["status"] == "declared"
    assert result["requirements"]["FR3"]["status"] == "unverified"

    assert result["unmapped_tests"] == ["test_other"]


def test_multiple_requirements_per_test():
    """One test may declare coverage for multiple requirements."""
    requirements = """
1. Place an order.
2. Clear the cart after an order.
"""

    test_code = '''
def test_checkout():
    """FR1, FR2: Successful checkout."""
    assert True
'''

    result = analyze_coverage(requirements, test_code)

    assert result["declared_requirements"] == 2
    assert result["requirements"]["FR1"]["tests"] == ["test_checkout"]
    assert result["requirements"]["FR2"]["tests"] == ["test_checkout"]


def test_unrecognized_requirement_annotation():
    """An invented FR number is flagged instead of counted as covered."""
    req = "1. Browse restaurants."
    code = '''
def test_browse():
    """FR1, FR99: Browse restaurants."""
    assert True
'''
    report = analyze_coverage(req, code)
    assert report["declared_requirements"] == 1
    assert report["unknown_requirement_ids"] == ["FR99"]


def test_requirement_description_spans_multiple_lines():
    """Multi-line requirement descriptions are not split into extra FRs."""
    req = "1. Browse restaurants.\n   Include ratings.\n2. Add to cart."
    code = '''
def test_cart():
    """FR2: Check cart."""
    assert True
'''
    report = analyze_coverage(req, code)
    assert report["total_requirements"] == 2
    assert "Include ratings." in report["requirements"]["FR1"]["description"]
    assert report["requirements"]["FR2"]["status"] == "declared"
