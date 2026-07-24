import sys
import time
from facebook.trust_engine import TrustEngine

def main():
    print("========================================")
    print("   NEPAL CENTRAL NEWS - PAGE HEALTH")
    print("========================================")
    
    print("Initializing Trust Engine...")
    try:
        engine = TrustEngine()
        
        # Get 7-day rolling average
        rolling_avg = engine._get_rolling_average(days=7)
        avg_display = f"{rolling_avg:.2f}" if rolling_avg else "N/A (Not enough data)"
        print(f"\n📊 7-Day Rolling Average Reach: {avg_display}")
        
        print("\n🔍 Fetching current Meta Insights...")
        state, cycle_limit, skip_links = engine.evaluate_page_health()
        
        print("\n----------------------------------------")
        
        if state == "HEALTHY":
            print("✅ STATUS: HEALTHY")
            print("Your page is performing normally.")
        elif state == "RECOVERING":
            print("⚠️ STATUS: RECOVERING")
            print("Your page reach dropped recently, but is stabilizing.")
        elif state == "SHADOWBANNED":
            print("🚨 STATUS: SHADOWBANNED (Algorithmic Suppression)")
            print("Your page has suffered consecutive severe reach drops.")
        else:
            print(f"❓ STATUS: {state}")
            
        print("----------------------------------------")
        print(f"📌 ALLOWED POSTS PER CYCLE: {cycle_limit} (Min {engine.MIN_POSTS}, Max {engine.MAX_POSTS})")
        print(f"📌 SKIP LINK POSTS: {'YES (Protecting Reach)' if skip_links else 'NO'}")
        print("========================================")
        
    except Exception as e:
        print(f"\n❌ Error checking health: {e}")
        
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
