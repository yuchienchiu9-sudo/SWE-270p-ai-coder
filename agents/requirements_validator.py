# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""
Analyze declared requirement-to-test mappings.

This version does not prove functional correctness.
It reports which requirements have test annotations.
"""

import ast
import re


def extract_requirements(requirements: str) -> dict[str, str]:
    """Extract numbered functional requirements from input text."""
    matches = re.findall(
        r"(?ms)^\s*(\d+)\.\s+(.+?)(?=^\s*\d+\.\s+|\Z)",
        requirements,
    )

    return {
        f"FR{number}": description.strip()
        for number, description in matches
    }


def extract_test_mappings(test_code: str) -> dict[str, list[str]]:
    """Find requirement IDs declared in pytest function docstrings."""
    tree = ast.parse(test_code)
    mappings = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue

            docstring = ast.get_docstring(node) or ""

            requirement_ids = re.findall(
                r"\bFR\d+\b",
                docstring,
                flags=re.IGNORECASE,
            )

            mappings[node.name] = sorted({
                req.upper() for req in requirement_ids
            })

    return mappings


def analyze_coverage(
    requirements: str,
    test_code: str,
) -> dict:
    """Create a declared coverage report for all requirements."""
    reqs = extract_requirements(requirements)
    mappings = extract_test_mappings(test_code)

    report = {}

    for req_id, description in reqs.items():
        matching_tests = [
            name
            for name, ids in mappings.items()
            if req_id in ids
        ]

        report[req_id] = {
            "description": description,
            "tests": matching_tests,
            "status": (
                "declared"
                if matching_tests
                else "unverified"
            ),
        }

    return {
        "total_requirements": len(reqs),
        "declared_requirements": sum(
            item["status"] == "declared"
            for item in report.values()
        ),
        "requirements": report,
        "unmapped_tests": [
            name for name, ids in mappings.items() if not ids
        ],
        "unknown_requirement_ids": sorted({
            req_id
            for ids in mappings.values()
            for req_id in ids
            if req_id not in reqs
        }),
    }
