from pathlib import Path

path = Path("scripts/direct_offer_refresh.py")
text = path.read_text(encoding="utf-8")

old = '''    if not unified_daily_sources:
        print("ERROR: unifiedDailySources is empty", file=sys.stderr)
        return 2
'''
new = '''    unified_sources_declared = "unifiedDailySources" in policy
    if unified_sources_declared and not unified_daily_sources:
        print("ERROR: unifiedDailySources is empty", file=sys.stderr)
        return 2
    if not unified_sources_declared:
        unified_daily_sources = list(comparison_sources)
'''
if text.count(old) != 1:
    raise SystemExit(f"legacy empty block count={text.count(old)}")
text = text.replace(old, new, 1)

old = '''    invalid_unified = [
        x for x in unified_daily_sources
        if sources[x].get("new_game_discovery_enabled") is not True
    ]
'''
new = '''    invalid_unified = [] if not unified_sources_declared else [
        x for x in unified_daily_sources
        if sources[x].get("new_game_discovery_enabled") is not True
    ]
'''
if text.count(old) != 1:
    raise SystemExit(f"legacy validation block count={text.count(old)}")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
