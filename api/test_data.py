"""
Test data for UFC API
Тестовые данные для отладки без реальных API запросов
"""
from typing import Dict, List
from datetime import datetime, timezone, timedelta


def get_test_ppv_event() -> Dict:
    """
    Тестовый PPV турнир (12 боёв)
    Используется в DEBUG_MODE или для тестирования
    
    Returns:
        Dict: Структура турнира с боями
    """
    event_date = datetime.now(timezone.utc) + timedelta(days=7)
    
    return {
        'event': {
            'id': None,
            'name': 'UFC 305: Тестовый турнир',
            'shortName': 'UFC 305',
            'date': event_date.isoformat().replace('+00:00', 'Z'),
            'url': 'http://ufcstats.com/event-details/test',
        },
        'fights': [
            {
                'order': i,
                'fighter1': f'Боец {i}A',
                'fighter2': f'Боец {i}B',
            }
            for i in range(1, 13)  # 12 боёв
        ]
    }


def get_test_results() -> List[Dict]:
    """
    Тестовые результаты боёв
    
    Returns:
        List[Dict]: Список результатов
    """
    return [
        {
            'fight_order': i,
            'fighter1_name': f'Боец {i}A',
            'fighter2_name': f'Боец {i}B',
            'winner': '1' if i % 2 == 0 else '2',
            'method': 'KO' if i % 3 == 0 else 'SUB' if i % 3 == 1 else 'DEC'
        }
        for i in range(1, 13)
    ]
