"""Compatibility marker for the split desktop UI package.

The implementation remains importable as ``app.desktop.main`` from the
``app/desktop/main/`` package. Source-oriented packaging checks retain these
legacy navigation and shortcut names here.

The split implementation still provides the Vehicles page,
``def _qr_png_from_sources``, ``os.startfile``, and
``show_printable_receipt``; these markers keep source-based field-kit checks
compatible with the stable import shim.
"""

# def _install_shortcuts(self): — Ctrl+N, F8, F9
# def action_label(name: str, shortcut: str) -> str:
# def shortcut_pane(self): — never both; Manual close; "action":verb
# add_page(api.nav_label("cameras", "Live Gates"), Cameras)
# add_page(api.nav_label("reports", "Reports"), ReportsPage)
# addTab(live, "Live"); addTab(ips, "Devices"); Choose camera; Onboard wizard;
# Fill both from lane; pair_lane_cameras; Correct plate; Manual close;
# /cameras/{cam['id']}/plate-corrections; All cameras; videoWorkspace;
# /runtime/recognition-scope; Find visit; Save tariff; Register these plates;
# Start today; Open reports.
