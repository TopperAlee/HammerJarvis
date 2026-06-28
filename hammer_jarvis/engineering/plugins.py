ENGINEERING_MODULES: list[dict[str, str]] = [
    {"id": "protool", "name": "ProTool Assistant", "status": "available"},
    {"id": "wincc_flexible", "name": "WinCC flexible Assistant", "status": "planned"},
    {"id": "tia", "name": "TIA Project Indexer", "status": "planned"},
    {"id": "step7", "name": "STEP7 Classic Assistant", "status": "planned"},
    {"id": "translator", "name": "HMI Translation Studio", "status": "planned"},
    {"id": "diagnostics", "name": "Engineering Diagnostics", "status": "planned"},
]


def get_engineering_modules() -> list[dict[str, str]]:
    return [module.copy() for module in ENGINEERING_MODULES]

