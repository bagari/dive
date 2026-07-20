"""Shared UI session state — referenced by multiple FURY callbacks.

The ``selected_item`` global is written by ComboBox2D callbacks in
:mod:`dive.ui.elements` and read by :class:`Show` methods in
:mod:`dive.ui.core`. It tracks the currently-selected ROI display name
across UI components.
"""
selected_item: str | None = None