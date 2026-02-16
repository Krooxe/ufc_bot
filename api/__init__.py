"""
UFC API Module
Работа с внешними API для получения данных о турнирах, боях и результатах
"""

# Events
from .events import get_upcoming_event, get_next_ppv_event

# Fights
from .fights import get_event_fights

# Results
from .results import (
    fetch_event_results,
    get_todays_ufc_event_results,
    parse_date,
    get_test_results
)

# Test data
from .test_data import get_test_ppv_event

__all__ = [
    # Events
    'get_upcoming_event',
    'get_next_ppv_event',  # ⭐ Это то что нужно для admin.py!
    
    # Fights
    'get_event_fights',
    
    # Results
    'fetch_event_results',
    'get_todays_ufc_event_results',
    'parse_date',
    'get_test_results',
    
    # Test data
    'get_test_ppv_event',
]
