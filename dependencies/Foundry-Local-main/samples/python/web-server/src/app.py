import time
from types import SimpleNamespace
from foundry_local_sdk import Configuration, FoundryLocalManager

def main():
    # 1. Port setup
    web_config = SimpleNamespace(
        urls="http://127.0.0.1:8000",
        external_url="http://127.0.0.1:8000"
    )
    
    # 2. Verified initialization (No fake CORS parameters)
    config = Configuration(
        app_name="foundry_local_samples",
        web=web_config
    )
    
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    try:
        # 3. Start listener first
        manager.start_web_service()
        time.sleep(1)
        
        # 4. Get model and force WinML/NPU variant
        model = manager.catalog.get_model("qwen2.5-0.5b")
        variant = next((v for v in model.variants if "winml" in v.id.lower()), model.variants[0])
        
        print(f"Loading {variant.id} onto Snapdragon NPU...")
        variant.load()
        
        print(f"\n[STATUS: BRAIN IS LIVE ON NPU]")
        print("Listening at: http://127.0.0.1:8000")
        print("Ready for DSIE Codex Chat Widget.")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if 'model' in locals() and model.is_loaded:
            model.unload()
        manager.stop_web_service()

if __name__ == "__main__":
    main()
