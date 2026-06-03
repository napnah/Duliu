"""Offline test for stress compare (requires g++ on PATH)."""

import shutil
import subprocess

import pytest

from duliu.runner.executor import stress_compare

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not installed"
)


def test_stress_ab_plus():
    std = r"""#include <bits/stdc++.h>
using namespace std;
int main() {
    long long a, b;
    cin >> a >> b;
    cout << a + b << endl;
    return 0;
}
"""
    brute = std
    report = stress_compare(
        std,
        brute,
        ["3 4\n", "0 0\n"],
        "test-prob",
        "test-job",
        1000,
        1_000_000,
    )
    assert report["ok"] is True
    assert report["rounds"] == 2
