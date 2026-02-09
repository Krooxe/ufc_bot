# test_full_card.py
from ufc_stats_api import get_todays_ufc_event_results

print("=" * 70)
print("ПОЛНЫЙ КАРД ТУРНИРА (ВСЕ БОИ)")
print("=" * 70)

fights = get_todays_ufc_event_results()

if fights:
    print(f"\n🎯 ТУРНИР НАЙДЕН!")
    print(f"🥊 ВСЕГО БОЕВ: {len(fights)}")
    print("=" * 50)
    
    # Показываем ВСЕ бои
    for i, fight in enumerate(fights, 1):
        # Определяем иконку результата
        if fight['winner'] == fight['fighter1']:
            result_icon = "👊"
            result_text = f"{fight['fighter1']} (1)"
        elif fight['winner'] == fight['fighter2']:
            result_icon = "🥊"
            result_text = f"{fight['fighter2']} (2)"
        elif fight['winner'] == 'draw':
            result_icon = "🤝"
            result_text = "Ничья"
        elif fight['winner'] == 'nc':
            result_icon = "❌"
            result_text = "No Contest"
        else:
            result_icon = "❓"
            result_text = "Неизвестно"
        
        print(f"{i:2}. {fight['fighter1']:25} vs {fight['fighter2']:25}")
        print(f"    {result_icon} Победитель: {result_text}")
        print()
    
    print("=" * 50)
    
    # Статистика
    wins_fighter1 = sum(1 for f in fights if f['winner'] == f['fighter1'])
    wins_fighter2 = sum(1 for f in fights if f['winner'] == f['fighter2'])
    draws = sum(1 for f in fights if f['winner'] == 'draw')
    nc = sum(1 for f in fights if f['winner'] == 'nc')
    
    print(f"📊 СТАТИСТИКА:")
    print(f"• Побед первого бойца: {wins_fighter1}")
    print(f"• Побед второго бойца: {wins_fighter2}")
    print(f"• Ничьих: {draws}")
    print(f"• No Contest: {nc}")
    
else:
    print("\n❌ Не найден подходящий турнир")