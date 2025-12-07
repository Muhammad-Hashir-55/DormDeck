# tests/test_time_and_ranking.py
import sys
import os

# Get the parent directory path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# Add parent directory to Python path
sys.path.insert(0, parent_dir)

# Now import directly
from dormdeck_engine import is_shop_open, parse_time, calculate_location_score, get_recommendations, add_service_entry
from datetime import datetime, time

# Your test code here...

def test_parse_time_247():
    assert parse_time("24/7") == "24/7"
    assert parse_time("247") == "24/7"

def test_midnight_crossing():
    # simulate 23:00
    now = datetime(2025,1,1,23,0,0)
    assert is_shop_open("18:00", "03:00", now) is True
    # simulate 02:00
    now2 = datetime(2025,1,2,2,0,0)
    assert is_shop_open("18:00", "03:00", now2) is True
    # simulate 15:00 -> closed
    now3 = datetime(2025,1,2,15,0,0)
    assert is_shop_open("18:00", "03:00", now3) is False

def test_same_hostel_score():
    assert calculate_location_score("H-5", "H-5") == 1.0

def test_adjacent_hostel_score():
    assert calculate_location_score("H-5", "H-4") == 0.4 or calculate_location_score("H-5", "H-6") == 0.4
