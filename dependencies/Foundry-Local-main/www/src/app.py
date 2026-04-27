import time
from types import SimpleNamespace
from foundry_local_sdk import Configuration, FoundryLocalManager

def main():
    # 1. Config with GA-compliant Shim
    web_config = SimpleNamespace(urls="http://127.0.0.1:8000", external_url="http://127.0.0.1:8000")
    config = Configuration(app_name="foundry_local_samples", web=web_config)
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    try:
        manager.start_web_service()
        time.sleep(1)

        # 2. LOCK THE NATIVE WINML VARIANT
        # Using the '-winml' suffix forces the Snapdragon NPU native path
        model = manager.catalog.get_model("qwen2.5-0.5b-instruct-winml")
        print(f"Loading native NPU variant: {model.alias}")
        model.load()
        
        print(f"\n[STATUS: BRAIN IS LIVE ON NPU]")
        print("Endpoint: http://127.0.0.1:8000/v1")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutdown...")
    finally:
        manager.stop_web_service()

if __name__ == "__main__":
    main()
