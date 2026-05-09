from titan_brain.news_memory_engine import run_news_memory_engine
from titan_brain.market_condition_engine import store_market_condition
from titan_brain.outcome_tracker import run_outcome_tracker
from titan_brain.learning_engine import run_learning_engine
from titan_brain.evolution_engine import run_evolution_engine

from engines.setup_engine import scan_for_setups
from utils.market_hours import is_trade_window, trade_window_text


def main():
    print("===================================")
    print("🚀 TITAN FULL SYSTEM RUN STARTED")
    print("===================================")

    try:
        print("\n📰 Updating news memory...")
        run_news_memory_engine()
    except Exception as e:
        print(f"[TEST RUN NEWS ERROR] {e}")

    try:
        print("\n📊 Storing market condition...")
        store_market_condition()
    except Exception as e:
        print(f"[TEST RUN MARKET CONDITION ERROR] {e}")

    if is_trade_window():
        try:
            print("\n🎯 Tracking open trade outcomes...")
            run_outcome_tracker()
        except Exception as e:
            print(f"[TEST RUN OUTCOME TRACKER ERROR] {e}")
    else:
        print(f"\nOutside trade window ({trade_window_text()}). Outcome tracker skipped.")

    try:
        print("\n📈 Scanning for trade setups...")
        setups = scan_for_setups()

        print("\n=== SETUPS FOUND ===")
        if setups:
            for setup in setups:
                print(setup)
        else:
            print("No valid setups found.")

    except Exception as e:
        print(f"[TEST RUN SCAN ERROR] {e}")

    try:
        print("\n🧠 Running learning engine...")
        run_learning_engine()
    except Exception as e:
        print(f"[TEST RUN LEARNING ERROR] {e}")

    try:
        print("\n🧬 Running evolution engine...")
        run_evolution_engine()
    except Exception as e:
        print(f"[TEST RUN EVOLUTION ERROR] {e}")

    print("\n✅ TITAN FULL SYSTEM RUN COMPLETED")


if __name__ == "__main__":
    main()
