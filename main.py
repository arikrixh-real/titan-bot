from titan_brain.news_memory_engine import run_news_memory_engine
from titan_brain.market_condition_engine import store_market_condition
from titan_brain.outcome_tracker import run_outcome_tracker
from titan_brain.learning_engine import run_learning_engine
from titan_brain.evolution_engine import run_evolution_engine

from engines.setup_engine import scan_for_setups


def main():
    print("===================================")
    print("🚀 TITAN MASTER SYSTEM STARTED")
    print("===================================")

    try:
        print("\n📰 Updating news memory...")
        run_news_memory_engine()
    except Exception as e:
        print(f"[MAIN NEWS ERROR] {e}")

    try:
        print("\n📊 Storing market condition...")
        store_market_condition()
    except Exception as e:
        print(f"[MAIN MARKET ERROR] {e}")

    try:
        print("\n🎯 Tracking trade outcomes...")
        run_outcome_tracker()
    except Exception as e:
        print(f"[MAIN OUTCOME ERROR] {e}")

    try:
        print("\n📈 Scanning for setups...")
        setups = scan_for_setups()

        if setups:
            print(f"✅ Setups found: {len(setups)}")
            for setup in setups:
                print(setup)
        else:
            print("No valid setups found.")

    except Exception as e:
        print(f"[MAIN SCAN ERROR] {e}")

    try:
        print("\n🧠 Running learning engine...")
        run_learning_engine()
    except Exception as e:
        print(f"[MAIN LEARNING ERROR] {e}")

    try:
        print("\n🧬 Running evolution engine...")
        run_evolution_engine()
    except Exception as e:
        print(f"[MAIN EVOLUTION ERROR] {e}")

    print("\n✅ TITAN MASTER SYSTEM COMPLETED")


if __name__ == "__main__":
    main()