"""Tests for Census surname data preprocessing."""
import json
import csv
import io
import pytest

from prepare_census_data import assign_tier, process_census_csv


class TestAssignTier:
    """assign_tier() maps rank to frequency tier."""

    def test_tier_1_top_100(self):
        assert assign_tier(1) == 1
        assert assign_tier(100) == 1

    def test_tier_2_top_1000(self):
        assert assign_tier(101) == 2
        assert assign_tier(1000) == 2

    def test_tier_3_top_10000(self):
        assert assign_tier(1001) == 3
        assert assign_tier(10000) == 3

    def test_tier_4_rare(self):
        assert assign_tier(10001) == 4
        assert assign_tier(50000) == 4


class TestProcessCensusCsv:
    """process_census_csv() converts CSV text to {surname: tier} dict."""

    def test_processes_sample_data(self):
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "SMITH,1,2442977,828.19,828.19,70.90,23.11,0.50,0.89,2.19,2.40\n"
        csv_text += "JOHNSON,2,1932812,655.24,1483.44,58.97,34.63,0.54,0.94,2.56,2.36\n"
        csv_text += "OKAFOR,15000,1234,0.42,98000.00,1.00,95.00,0.50,0.10,1.40,2.00\n"
        result = process_census_csv(csv_text)
        assert result["smith"] == 1
        assert result["johnson"] == 1
        assert result["okafor"] == 4

    def test_handles_suppressed_values(self):
        """Census uses '(S)' for suppressed values -- should still process rank."""
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "RAMIREZ,500,500000,169.54,50000.00,(S),(S),(S),(S),(S),76.73\n"
        result = process_census_csv(csv_text)
        assert result["ramirez"] == 2

    def test_lowercase_keys(self):
        csv_text = "name,rank,count,prop100k,cum_prop100k,pctwhite,pctblack,pctapi,pctaian,pct2prace,pcthispanic\n"
        csv_text += "GARCIA,8,1166120,395.32,5000.00,5.38,0.48,1.43,0.47,1.16,91.08\n"
        result = process_census_csv(csv_text)
        assert "garcia" in result
        assert "GARCIA" not in result
