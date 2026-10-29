"""Share the main project's profile reader without importing its runtime patches."""
import importlib.util
import os
from pathlib import Path


def reader():
    source = Path(os.environ.get("HOTEL_OTA_CONFIG_READER", "/opt/openclaw/workspaces/hotel-ota-ai/runtime/hotel_config.py"))
    if not source.is_file():
        source = Path(__file__).resolve().parents[2] / "hotel--ota-ai/runtime/hotel_config.py"
    spec = importlib.util.spec_from_file_location("hotel_profile_reader", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_environment():
    if os.environ.get("HOTEL_OTA_HOTEL_CONFIG_DIR"):
        reader().project_environment()


def view(kind):
    return reader().view(kind) if os.environ.get("HOTEL_OTA_HOTEL_CONFIG_DIR") else None


def hotel(hotel_id):
    return reader().profiles().get(hotel_id) if os.environ.get("HOTEL_OTA_HOTEL_CONFIG_DIR") else None
