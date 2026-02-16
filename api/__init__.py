"""
UFC API Module
Работа с внешними API для получения данных о турнирах, боях и результатах
"""

# Events
from .events import get_upcoming_event, get_next_ppv_event, get_completed_event_for_results

# Fights
from .fights import get_event_fights, _get_fights_from_event

# Results
from .results import (
    fetch_event_results,
    get_todays_ufc_event_results,
    parse_date,
    # get_test_results убрали отсюда - её нет в results.py!
)

# Test data - импортируем отдельно из test_data
from .test_data import get_test_ppv_event, get_test_results

__all__ = [
    # Events
    'get_upcoming_event',
    'get_next_ppv_event',
    'get_completed_event_for_results',
    
    # Fights
    'get_event_fights',
    '_get_fights_from_event',
    
    # Results
    'fetch_event_results',
    'get_todays_ufc_event_results',
    'parse_date',
    
    # Test data
    'get_test_ppv_event',
    'get_test_results',  # теперь импортируется из test_data
]