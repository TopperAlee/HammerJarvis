from dataclasses import dataclass


@dataclass(frozen=True)
class PanelSpec:
    panel_id: str
    rows: int
    columns: int


SUPPORTED_PANELS: dict[str, PanelSpec] = {
    "OP7": PanelSpec("OP7", rows=4, columns=20),
    "TD17_4x20": PanelSpec("TD17_4x20", rows=4, columns=20),
    "TD17_8x40": PanelSpec("TD17_8x40", rows=8, columns=40),
    "OP17_4x20": PanelSpec("OP17_4x20", rows=4, columns=20),
    "OP17_8x40": PanelSpec("OP17_8x40", rows=8, columns=40),
    "OP27_8x40": PanelSpec("OP27_8x40", rows=8, columns=40),
}


def get_panel_spec(panel: str) -> PanelSpec:
    try:
        return SUPPORTED_PANELS[panel]
    except KeyError as exc:
        supported = ", ".join(sorted(SUPPORTED_PANELS))
        raise ValueError(f"Unsupported panel '{panel}'. Supported panels: {supported}") from exc
