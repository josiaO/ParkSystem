"""Reusable widget presentation, independent of API and hardware lifecycles."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFormLayout, QHeaderView,
    QLabel, QLineEdit, QScrollArea, QSizePolicy, QTableWidget, QWidget,
)


def configure_table(table: QTableWidget):
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setWordWrap(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(max(30, table.fontMetrics().height() + 14))
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setMinimumSectionSize(64)
    header.setDefaultSectionSize(140)
    header.setStretchLastSection(True)
    table.setAccessibleDescription("Read-only records. Use arrow keys to select a row; drag column borders to resize. Scroll horizontally for more columns.")


def label_for(text: str, field: QWidget) -> QLabel:
    label = QLabel(text)
    label.setBuddy(field)
    field.setAccessibleName(text.replace("&", ""))
    return label


def prepare_page(page: QWidget, title: str):
    """Add semantics and scalable typography without changing page callbacks."""
    page.setAccessibleName(title)
    layout = QWidget.layout(page)
    if layout:
        compact = bool(page.property("videoWorkspace"))
        layout.setContentsMargins(*( (0, 0, 0, 0) if compact else (16, 14, 16, 14) ))
        layout.setSpacing(0 if compact else 10)
        first = layout.itemAt(0)
        heading = first.widget() if first else None
        if isinstance(heading, QLabel) and "font-size:24px" in heading.styleSheet():
            heading.hide()
    for form in page.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for row in range(form.rowCount()):
            field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = field_item.widget() if field_item else None
            label = label_item.widget() if label_item else None
            if isinstance(label, QLabel) and field and label.text():
                label.setBuddy(field)
                if not field.accessibleName():
                    field.setAccessibleName(label.text().replace("&", ""))
    for field in page.findChildren(QLineEdit):
        if not field.accessibleName() and field.placeholderText():
            field.setAccessibleName(field.placeholderText())
    for field in page.findChildren(QComboBox):
        if not field.accessibleName() and field.toolTip():
            field.setAccessibleName(field.toolTip())
    for table in page.findChildren(QTableWidget):
        if not table.property("desktopTablePrepared"):
            configure_table(table)
            table.setProperty("desktopTablePrepared", True)
        table.verticalHeader().setDefaultSectionSize(max(30, table.fontMetrics().height() + 14))
        table.setAccessibleName(f"{title} records")
    scale = QApplication.font().pointSizeF() / 10
    for label in page.findChildren(QLabel):
        original = label.property("desktopTypography")
        if original is None and "font-size:" in label.styleSheet():
            original = label.styleSheet()
            label.setProperty("desktopTypography", original)
        if original:
            label.setStyleSheet(re.sub(
                r"font-size:\s*(\d+)px",
                lambda match: f"font-size:{max(9, round(int(match.group(1)) * 0.75 * scale))}pt",
                original,
            ))


def page_viewport(page: QWidget, title: str) -> QScrollArea:
    prepare_page(page, title)
    viewport = QScrollArea()
    viewport.setAccessibleName(f"{title} workspace")
    viewport.setWidgetResizable(True)
    viewport.setFrameShape(QScrollArea.Shape.NoFrame)
    viewport.setWidget(page)
    if page.__class__.__name__ == "Cameras":
        viewport.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    viewport.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return viewport
