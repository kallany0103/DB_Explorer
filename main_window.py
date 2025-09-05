# main_window.py

import sys
import os
import time
import datetime
import psycopg2
import sqlite3 as sqlite
from functools import partial
import pandas as pd
import uuid

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QTabWidget,
    QSplitter, QLineEdit, QTextEdit, QComboBox, QTableView, QVBoxLayout, QWidget, QStatusBar, QToolBar, QFileDialog,
    QSizePolicy, QPushButton, QInputDialog, QMessageBox, QMenu, QAbstractItemView, QDialog, QFormLayout, QHBoxLayout,
    QStackedWidget, QLabel, QGroupBox, QDialogButtonBox, QCheckBox, QRadioButton, QStyle, QHeaderView, QFrame,
    QPlainTextEdit
)
from PyQt6.QtGui import (
    QAction, QIcon, QStandardItemModel, QStandardItem, QFont, QMovie, QDesktopServices, QColor, QBrush, QPainter,
    QTextFormat, QPolygon
)
from PyQt6.QtCore import (
    Qt, QDir, QModelIndex, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QTimer, QUrl, QRect, QPoint
)

# Importing classes from the dialogs folder
from dialogs.postgres_dialog import PostgresConnectionDialog
from dialogs.sqlite_dialog import SQLiteConnectionDialog
# db Importing modules
import dialogs.db as db
# count rows

# <<< NEW CLASS >>> Line number widget for the code editor


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)

    def mousePressEvent(self, event):
        self.codeEditor.handle_line_number_area_click(event)


# <<< NEW CLASS >>> Custom code editor with line numbers and folding
class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        # folding_markers: {start_line_num: {'end': end_line_num, 'open': bool}}
        self.folding_markers = {}

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.textChanged.connect(self.on_text_changed)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    # <<< FIX #2 >>> ADDED THE MISSING highlightCurrentLine METHOD

    def handle_line_number_area_click(self, event):
        # Qt6: .position()
        y = event.position().y() if hasattr(event, "position") else event.pos().y()

        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(
            block).translated(self.contentOffset()).top()

        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                bn = block.blockNumber()
                if bn in self.folding_markers:
                    self.toggle_fold(bn)
                break
            block = block.next()
            top = bottom

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # marker এলাকাতে হলে কার্সর বদলান
        self.lineNumberArea.setCursor(Qt.CursorShape.PointingHandCursor)

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            # selection = self.ExtraSelection()
            selection = QTextEdit.ExtraSelection()

            # You can change the highlight color here
            lineColor = QColor("#e8f4ff")  # A light blue color
            selection.format.setBackground(lineColor)

            # This makes the highlight span the entire width of the editor
            selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True)

            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)

    def on_text_changed(self):
        # A simple debounce mechanism could be added here if performance is an issue
        self.update_folding_markers()

    def lineNumberAreaWidth(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        # Add space for folding markers (approx 15px) + padding
        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(
                0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(
            QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    # <<< FIX #1 >>> CORRECTED THE PAINT EVENT FOR FOLDING MARKERS
    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#f0f0f0"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = self.blockBoundingGeometry(
            block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
               # === Line Number ===
                number = str(blockNumber + 1)
                painter.setPen(Qt.GlobalColor.darkGray)
                painter.drawText(
                    0, int(top),
                    self.lineNumberArea.width() - 18, height,
                    Qt.AlignmentFlag.AlignRight,
                    number
                )

                # === Folding Marker ===
                if blockNumber in self.folding_markers:
                    marker_rect = QRect(self.lineNumberArea.width() - 16,
                                        int(top) + (height - 10) // 2,
                                        10, 10)
                    painter.setPen(Qt.GlobalColor.black)
                    painter.setBrush(QBrush(Qt.GlobalColor.black))

                    if self.folding_markers[blockNumber]['open']:
                        # ▼ Down triangle
                        points = [
                            QPoint(marker_rect.left(), marker_rect.top()),
                            QPoint(marker_rect.right(), marker_rect.top()),
                            QPoint(marker_rect.center().x(),
                                   marker_rect.bottom())
                        ]
                    else:
                        # ► Right triangle
                        points = [
                            QPoint(marker_rect.left(), marker_rect.top()),
                            QPoint(marker_rect.left(), marker_rect.bottom()),
                            QPoint(marker_rect.right(),
                                   marker_rect.center().y())
                        ]
                    # Moved this line outside the if/else to draw in both cases
                    painter.drawPolygon(QPolygon(points))

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            blockNumber += 1

    def update_folding_markers(self):
        new_markers = {}
        processed_lines = set()

        block = self.document().begin()
        while block.isValid():
            block_num = block.blockNumber()
            if block_num in processed_lines:
                block = block.next()
                continue

            # Find end of statement
            temp_block = block
            statement_text = ""
            end_block_num = -1
            while temp_block.isValid():
                statement_text += temp_block.text()
                if ';' in statement_text.strip():
                    end_block_num = temp_block.blockNumber()
                    break
                temp_block = temp_block.next()

            if end_block_num > block_num:
                # Found a multi-line statement
                is_open = self.folding_markers.get(
                    block_num, {'open': True})['open']
                new_markers[block_num] = {
                    'end': end_block_num, 'open': is_open}
                for i in range(block_num, end_block_num + 1):
                    processed_lines.add(i)

            # Move to the next block after the processed statement
            if end_block_num != -1:
                block = self.document().findBlockByNumber(end_block_num).next()
            else:
                block = block.next()

        self.folding_markers = new_markers
        self.lineNumberArea.update()

    def mousePressEvent(self, event):
        margin = self.viewportMargins().left()
        click_x = event.pos().x()

        # Click in line number/folding area
        if click_x < margin:
            block = self.firstVisibleBlock()
            top = self.blockBoundingGeometry(
                block).translated(self.contentOffset()).top()

            while block.isValid():
                bottom = top + self.blockBoundingRect(block).height()
                if top <= event.pos().y() < bottom:
                    if block.blockNumber() in self.folding_markers:
                        self.toggle_fold(block.blockNumber())
                        return
                    break
                block = block.next()
                top = bottom

        super().mousePressEvent(event)

    def toggle_fold(self, block_number: int) -> None:
        # """
        #  Fold/unfold the region that starts at `block_number`.
        # Expects self.folding_markers[block_number] = {"open": bool, "end": int}
        # """
       
        if not hasattr(self, "folding_markers") or block_number not in self.folding_markers:
            return

        marker = self.folding_markers[block_number]
        is_open = marker.get("open", True)
        end_block_num = marker.get("end", block_number)

        # toggle state update
        marker["open"] = not is_open

        doc = self.document()
        start_block = doc.findBlockByNumber(block_number)

        # terget end-block find (invalid than end)
        end_block = doc.findBlockByNumber(end_block_num)
        if not end_block.isValid():
            # fallback
            end_block_num = doc.blockCount() - 1
            end_block = doc.findBlockByNumber(end_block_num)

        # 
        block = start_block.next()
        while block.isValid() and block.blockNumber() <= end_block_num:
            block.setVisible(not is_open)  
            block = block.next()

       
        start_pos = start_block.position()
        end_pos = end_block.position() + end_block.length()
        doc.markContentsDirty(start_pos, max(0, end_pos - start_pos))

        # ---- UI refresh ----
        # Text area ও line number area update
        self.viewport().update()
        if hasattr(self, "lineNumberArea") and self.lineNumberArea is not None:
            self.lineNumberArea.update()


# <<< NEW CLASS >>> column edit
class ColumnEditDialog(QDialog):
    def __init__(self, db_type, column_data, parent=None):
        super().__init__(parent)
        self.db_type = db_type
        self.column_data = column_data
        self.setWindowTitle(f"Edit Column - {column_data.get('name', '')}")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)
        self.name_edit = QLineEdit(column_data.get('name', ''))
        self.type_combo = QComboBox()
        self.length_edit = QLineEdit(str(column_data.get('length', '')))
        self.default_edit = QLineEdit(str(column_data.get('default', '')))
        self.not_null_check = QCheckBox()
        self.not_null_check.setChecked(column_data.get('not_null', False))

        layout.addRow("Name:", self.name_edit)
        layout.addRow("Data type:", self.type_combo)
        layout.addRow("Length/Precision:", self.length_edit)
        layout.addRow("Default value:", self.default_edit)
        layout.addRow("Not NULL?", self.not_null_check)

        self._populate_types()
        self.type_combo.setCurrentText(column_data.get('type', ''))

        if self.db_type == 'sqlite':
            self.type_combo.setEnabled(False)
            self.length_edit.setEnabled(False)
            self.default_edit.setEnabled(False)
            self.not_null_check.setEnabled(False)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def _populate_types(self):
        if self.db_type == 'postgres':
            types = [
                "bigint", "boolean", "character varying", "character", "date", "double precision",
                "integer", "json", "jsonb", "numeric", "real", "smallint", "text",
                "time", "timestamp", "uuid", "xml"
            ]
        else:  # SQLite
            types = ["TEXT", "NUMERIC", "INTEGER", "REAL", "BLOB"]

        self.type_combo.addItems(types)
        self.type_combo.setEditable(True)

    def get_data(self):
        return {
            "name": self.name_edit.text(),
            "type": self.type_combo.currentText(),
            "length": self.length_edit.text(),
            "default": self.default_edit.text(),
            "not_null": self.not_null_check.isChecked()
        }


class NotificationWidget(QWidget):
    closed = pyqtSignal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("notificationWidget")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        self.icon_label = QLabel()
        self.message_label = QLabel()
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("notificationCloseButton")
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.close_widget)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.message_label)
        layout.addStretch()
        layout.addWidget(self.close_button)

    def show_message(self, message, is_error=False):
        self.message_label.setText(message)
        if is_error:
            self.setProperty("isError", True)
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
        else:
            self.setProperty("isError", False)
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        self.icon_label.setPixmap(icon.pixmap(16, 16))
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        self.show()

    def close_widget(self):
        self.closed.emit(self)
        self.close()


class NotificationManager:
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.notifications = []
        self.spacing = 10
        self.margin = 15

    def show_message(self, message, is_error=False):
        notification = NotificationWidget(self.parent)
        notification.closed.connect(self.on_notification_closed)
        self.notifications.insert(0, notification)
        notification.show_message(message, is_error)
        self.reposition_notifications()

    def on_notification_closed(self, notification_widget):
        try:
            self.notifications.remove(notification_widget)
        except ValueError:
            pass
        self.reposition_notifications()

    def reposition_notifications(self):
        if not self.parent:
            return
        parent_rect = self.parent.geometry()
        status_bar_height = 0
        if hasattr(self.parent, 'statusBar') and self.parent.statusBar():
            status_bar_height = self.parent.statusBar().height()
        y = parent_rect.height() - status_bar_height - self.margin
        for notification in self.notifications:
            y -= notification.height()
            x = parent_rect.width() - notification.width() - self.margin
            notification.move(x, y)
            y -= self.spacing


class ExportDialog(QDialog):
    def __init__(self, parent=None, default_filename="export.csv"):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(550)
        main_layout = QVBoxLayout(self)
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        general_tab = QWidget()
        options_tab = QWidget()
        tab_widget.addTab(general_tab, "General")
        tab_widget.addTab(options_tab, "Options")
        general_layout = QFormLayout(general_tab)
        general_layout.addRow("Action:", QLabel("Export"))
        self.filename_edit = QLineEdit(default_filename)
        browse_btn = QPushButton()
        browse_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_DirOpenIcon))
        browse_btn.setFixedSize(30, 25)
        browse_btn.clicked.connect(self.browse_file)
        filename_layout = QHBoxLayout()
        filename_layout.addWidget(self.filename_edit)
        filename_layout.addWidget(browse_btn)
        general_layout.addRow("Filename:", filename_layout)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["csv", "xlsx"])
        self.format_combo.setCurrentText("csv")
        self.format_combo.currentTextChanged.connect(self.on_format_change)
        general_layout.addRow("Format:", self.format_combo)
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(['UTF-8', 'LATIN1', 'windows-1252'])
        self.encoding_combo.setEditable(True)
        general_layout.addRow("Encoding:", self.encoding_combo)
        options_layout = QFormLayout(options_tab)
        self.options_layout = options_layout
        self.header_check = QCheckBox("Header")
        self.header_check.setChecked(True)
        options_layout.addRow("Options:", self.header_check)
        self.delimiter_label = QLabel("Delimiter:")
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems([',', ';', '|', '\\t'])
        self.delimiter_combo.setEditable(True)
        self.quote_label = QLabel("Quote character:")
        self.quote_edit = QLineEdit('"')
        self.quote_edit.setMaxLength(1)
        options_layout.addRow(self.delimiter_label, self.delimiter_combo)
        options_layout.addRow(self.quote_label, self.quote_edit)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self.on_format_change(self.format_combo.currentText())

    def on_format_change(self, format_text):
        is_csv = (format_text == 'csv')
        self.encoding_combo.setEnabled(is_csv)
        self.delimiter_label.setVisible(is_csv)
        self.delimiter_combo.setVisible(is_csv)
        self.quote_label.setVisible(is_csv)
        self.quote_edit.setVisible(is_csv)
        current_filename = self.filename_edit.text()
        base_name, _ = os.path.splitext(current_filename)
        self.filename_edit.setText(f"{base_name}.{format_text}")

    def browse_file(self):
        file_filter = "CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Output File", self.filename_edit.text(), file_filter)
        if path:
            self.filename_edit.setText(path)

    def get_options(self):
        delimiter = self.delimiter_combo.currentText()
        if delimiter == '\\t':
            delimiter = '\t'
        return {
            "filename": self.filename_edit.text(),
            "encoding": self.encoding_combo.currentText(),
            "format": self.format_combo.currentText(),
            "header": self.header_check.isChecked(),
            "delimiter": delimiter,
            "quote": self.quote_edit.text()
        }

class TablePropertiesDialog(QDialog):
    def __init__(self, item_data, table_name, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.table_name = table_name
        self.conn_data = self.item_data['conn_data']
        self.db_type = self.item_data['db_type']
        self.schema_name = self.item_data.get('schema_name')
        self.qualified_table_name = f'"{self.schema_name}"."{self.table_name}"' if self.db_type == 'postgres' else f'"{self.table_name}"'

        self.setWindowTitle(f"Properties - {self.table_name}")
        self.setMinimumSize(850, 600)

        self.main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.refresh_properties()

        button_box = QHBoxLayout()
        button_box.addStretch()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_box.addWidget(ok_button)
        self.main_layout.addLayout(button_box)

    # <<< MODIFIED >>> new method: UI refresh
    def refresh_properties(self):
        # Clear existing tabs
        while self.tab_widget.count() > 0:
            self.tab_widget.removeTab(0)

        try:
            general_tab = self._create_general_tab()
            columns_tab = self._create_columns_tab()
            constraints_tab = self._create_constraints_tab()

            self.tab_widget.addTab(general_tab, "General")
            self.tab_widget.addTab(columns_tab, "Columns")
            self.tab_widget.addTab(constraints_tab, "Constraints")
        except Exception as e:
            # If tabs are already gone, a simple label is fine
            if self.tab_widget.count() == 0:
                error_label = QLabel(f"Failed to load table properties:\n{e}")
                error_label.setWordWrap(True)
                self.main_layout.insertWidget(0, error_label)
            else:  # If error happens during creation, show it in the first tab
                error_label = QLabel(f"Failed to load table properties:\n{e}")
                error_label.setWordWrap(True)
                self.tab_widget.currentWidget().layout().addWidget(error_label)

    def _create_general_tab(self):
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(10)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        properties = {}
        if self.db_type == 'postgres':
            properties = self._fetch_postgres_general_properties()
        else:
            properties = self._fetch_sqlite_general_properties()
        self.name_field = QLineEdit(properties.get("Name", ""))
        self.name_field.setReadOnly(True)
        self.owner_combo = QComboBox()
        self.schema_field = QLineEdit(properties.get("Schema", ""))
        self.schema_field.setReadOnly(True)
        self.tablespace_combo = QComboBox()
        self.partitioned_check = QCheckBox()
        self.comment_edit = QTextEdit(properties.get("Comment", ""))
        if self.db_type == 'postgres':
            if "all_owners" in properties:
                self.owner_combo.addItems(properties.get("all_owners", []))
            if "all_tablespaces" in properties:
                self.tablespace_combo.addItems(
                    properties.get("all_tablespaces", []))
            self.owner_combo.setCurrentText(properties.get("Owner", ""))
            self.tablespace_combo.setCurrentText(
                properties.get("Table Space", "default"))
            self.partitioned_check.setChecked(
                properties.get("Is Partitioned", False))
        else:
            self.owner_combo.setEnabled(False)
            self.tablespace_combo.setEnabled(False)
            self.partitioned_check.setEnabled(False)
        layout.addRow("Name:", self.name_field)
        layout.addRow("Owner:", self.owner_combo)
        layout.addRow("Schema:", self.schema_field)
        layout.addRow("Tablespace:", self.tablespace_combo)
        layout.addRow("Partitioned table?:", self.partitioned_check)
        layout.addRow("Comment:", self.comment_edit)
        return widget

    def _create_tag_button(self, text):
        button = QPushButton(f"{text}  ×")
        button.setStyleSheet(
            "QPushButton { background-color: #e1e1e1; border: 1px solid #c1c1c1; border-radius: 4px; padding: 3px 6px; font-size: 9pt; text-align: center; } QPushButton:hover { background-color: #d1d1d1; } QPushButton:pressed { background-color: #c1c1c1; }")
        button.clicked.connect(lambda: self._remove_inheritance_tag(button))
        return button

    def _remove_inheritance_tag(self, button_to_remove):
        table_name = button_to_remove.text().split("  ×")[0]
        button_to_remove.deleteLater()
        current_items = [self.add_parent_combo.itemText(
            i) for i in range(self.add_parent_combo.count())]
        if table_name not in current_items:
            self.add_parent_combo.addItem(table_name)
            self.add_parent_combo.model().sort(0)

    def _add_inheritance_tag(self, index):
        table_to_add = self.add_parent_combo.itemText(index)
        if not table_to_add:
            return
        for i in range(self.inheritance_layout.count()):
            widget = self.inheritance_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.text().startswith(table_to_add):
                self.add_parent_combo.setCurrentIndex(0)
                return
        new_tag = self._create_tag_button(table_to_add)
        self.inheritance_layout.insertWidget(
            self.inheritance_layout.indexOf(self.add_parent_combo), new_tag)
        self.add_parent_combo.removeItem(index)
        self.add_parent_combo.setCurrentIndex(0)

    # <<< MODIFIED >>> Edit Column 
    def _edit_column(self, column_name):
        conn = None
        column_data = {}
        try:
            # Fetch current details for the specific column
            if self.db_type == 'postgres':
                pg_conn_data = {key: self.conn_data.get(
                    key) for key in ['host', 'port', 'database', 'user', 'password']}
                conn = db.create_postgres_connection(**pg_conn_data)
                cursor = conn.cursor()
                col_query = """
                    SELECT c.column_name, c.udt_name, c.character_maximum_length, c.numeric_precision,
                           c.is_nullable, c.column_default
                    FROM information_schema.columns AS c
                    WHERE c.table_schema = %s AND c.table_name = %s AND c.column_name = %s;
                """
                cursor.execute(col_query, (self.schema_name,
                               self.table_name, column_name))
                res = cursor.fetchone()
                if res:
                    column_data = {
                        "name": res[0], "type": res[1],
                        "length": res[2] if res[2] is not None else res[3],
                        "not_null": res[4] == "NO", "default": res[5] or ""
                    }
            else:  # SQLite
                conn = db.create_sqlite_connection(self.conn_data['db_path'])
                cursor = conn.cursor()
                cursor.execute(f'PRAGMA table_info("{self.table_name}");')
                for row in cursor.fetchall():
                    if row[1] == column_name:
                        column_data = {
                            "name": row[1], "type": row[2], "not_null": bool(row[3]),
                            "default": row[4] or "", "length": ""
                        }
                        break

            if not column_data:
                QMessageBox.critical(
                    self, "Error", f"Could not find details for column '{column_name}'.")
                return

            dialog = ColumnEditDialog(self.db_type, column_data, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_data()
                self._update_column_in_db(column_data, new_data)

        except Exception as e:
            QMessageBox.critical(
                self, "DB Error", f"Error editing column: {e}")
        finally:
            if conn:
                conn.close()

    def _update_column_in_db(self, old_data, new_data):
        queries = []
        if self.db_type == 'postgres':
            if old_data['name'] != new_data['name']:
                queries.append(
                    f'ALTER TABLE {self.qualified_table_name} RENAME COLUMN "{old_data["name"]}" TO "{new_data["name"]}";')

            type_str = new_data['type']
            if new_data['length'] and new_data['type'] in ['character varying', 'character', 'numeric']:
                type_str = f"{new_data['type']}({new_data['length']})"

            if old_data['type'] != new_data['type'] or str(old_data.get('length', '')) != new_data['length']:
                # Note: Type casting can be complex. This is a simplified approach.
                queries.append(
                    f'ALTER TABLE {self.qualified_table_name} ALTER COLUMN "{new_data["name"]}" TYPE {type_str} USING "{new_data["name"]}"::{type_str};')

            if old_data['not_null'] != new_data['not_null']:
                action = "SET NOT NULL" if new_data['not_null'] else "DROP NOT NULL"
                queries.append(
                    f'ALTER TABLE {self.qualified_table_name} ALTER COLUMN "{new_data["name"]}" {action};')

            if old_data['default'] != new_data['default']:
                action = f"SET DEFAULT '{new_data['default']}'" if new_data['default'] else "DROP DEFAULT"
                queries.append(
                    f'ALTER TABLE {self.qualified_table_name} ALTER COLUMN "{new_data["name"]}" {action};')

        elif self.db_type == 'sqlite':
            # SQLite only supports RENAME COLUMN easily.
            if old_data['name'] != new_data['name']:
                queries.append(
                    f'ALTER TABLE {self.qualified_table_name} RENAME COLUMN "{old_data["name"]}" TO "{new_data["name"]}";')

        if not queries:
            QMessageBox.information(
                self, "No Changes", "No changes were detected.")
            return

        conn = None
        try:
            if self.db_type == 'postgres':
                pg_conn_data = {key: self.conn_data.get(
                    key) for key in ['host', 'port', 'database', 'user', 'password']}
                conn = db.create_postgres_connection(**pg_conn_data)
            else:
                conn = db.create_sqlite_connection(self.conn_data['db_path'])

            cursor = conn.cursor()
            full_query = "\n".join(queries)
            cursor.execute(full_query)
            conn.commit()
            QMessageBox.information(
                self, "Success", "Column updated successfully.")
            self.refresh_properties()  # Refresh the view
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Query Error",
                                 f"Failed to update column:\n{e}")
        finally:
            if conn:
                conn.close()

    def _delete_column(self, column_name):
        reply = QMessageBox.question(
            self, "Delete Column", f"Are you sure you want to delete the column '{column_name}'?\nThis action cannot be undone.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        query = f'ALTER TABLE {self.qualified_table_name} DROP COLUMN "{column_name}";'
        conn = None
        try:
            if self.db_type == 'postgres':
                pg_conn_data = {key: self.conn_data.get(
                    key) for key in ['host', 'port', 'database', 'user', 'password']}
                conn = db.create_postgres_connection(**pg_conn_data)
            else:  # SQLite requires a more complex process not implemented here for safety
                QMessageBox.warning(
                    self, "Not Supported", "Deleting columns from SQLite tables is not directly supported via this tool.")
                return

            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            QMessageBox.information(
                self, "Success", f"Column '{column_name}' deleted successfully.")
            self.refresh_properties()
        except Exception as e:
            if conn:
                conn.rollback()
            QMessageBox.critical(self, "Query Error",
                                 f"Failed to delete column:\n{e}")
        finally:
            if conn:
                conn.close()

    def _create_columns_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 0)
        inheritance_group = QGroupBox("Inherited from table(s)")
        inheritance_frame = QFrame()
        inheritance_frame.setObjectName("inheritanceFrame")
        inheritance_frame.setStyleSheet(
            "#inheritanceFrame { border: 1px solid #a9a9a9; border-radius: 3px; }")
        self.inheritance_layout = QHBoxLayout(inheritance_frame)
        self.inheritance_layout.setContentsMargins(2, 2, 2, 2)
        self.inheritance_layout.setSpacing(6)
        group_layout = QVBoxLayout(inheritance_group)
        group_layout.addWidget(inheritance_frame)
        layout.addWidget(inheritance_group)
        if self.db_type == 'postgres':
            inherited_tables = self._fetch_postgres_inheritance()
            all_tables = self._fetch_all_connection_tables()
            possible_new_parents = sorted(
                [t for t in all_tables if t != self.qualified_table_name and t not in inherited_tables])
            for table_name in inherited_tables:
                tag = self._create_tag_button(table_name)
                self.inheritance_layout.addWidget(tag)
            self.add_parent_combo = QComboBox()
            self.add_parent_combo.addItems([""] + possible_new_parents)
            self.add_parent_combo.setMinimumWidth(200)
            self.add_parent_combo.setStyleSheet("QComboBox { border: none; }")
            self.add_parent_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.add_parent_combo.activated.connect(self._add_inheritance_tag)
            self.inheritance_layout.addWidget(self.add_parent_combo)
            self.inheritance_layout.addStretch(0)
        else:
            inheritance_group.setEnabled(False)
        columns_group = QGroupBox("Columns")
        columns_layout = QVBoxLayout(columns_group)
        layout.addWidget(columns_group)
        table_view = QTableView()
        columns_layout.addWidget(table_view)
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(
            ['Edit', 'Delete', 'Name', 'Data type', 'Length/Precision', 'Scale', 'Not NULL?', 'Primary key?', 'Default'])
        table_view.setModel(model)
        table_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        # Resize modes: icon columns fixed, name Stretch
        table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)   # Edit
        table_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed)   # Delete
        table_view.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)  # Name
        table_view.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background-color: ##e0e0e0; padding: 4px; }")

        # Header center + padding
        table_view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.setColumnWidth(0, 56)
        table_view.setColumnWidth(1, 56)
        columns_data = self._fetch_postgres_columns(
        ) if self.db_type == 'postgres' else self._fetch_sqlite_columns()
        edit_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        delete_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogCancelButton)
        gray_brush = QBrush(QColor("gray"))
        for row_idx, row_data in enumerate(columns_data):
            is_local = row_data[7] if self.db_type == 'postgres' else True
            edit_item, delete_item = QStandardItem(""), QStandardItem("")
            name_text = f"{row_data[0]} (inherited)" if not is_local else str(
                row_data[0])
            name_item = QStandardItem(name_text)
            type_item, len_item, scale_item = QStandardItem(str(row_data[1])), QStandardItem(
                str(row_data[2])), QStandardItem(str(row_data[3]))
            default_item, not_null_item, pk_item = QStandardItem(
                str(row_data[6])), QStandardItem(""), QStandardItem("")
            all_items = [edit_item, delete_item, name_item, type_item,
                         len_item, scale_item, not_null_item, pk_item, default_item]
            if not is_local:
                for item in all_items:
                    item.setForeground(gray_brush)
                    flags = item.flags()
                    flags &= ~Qt.ItemFlag.ItemIsSelectable
                    item.setFlags(flags)
            edit_item.setEditable(False)
            delete_item.setEditable(False)
            not_null_item.setEditable(False)
            pk_item.setEditable(False)
            model.appendRow(all_items)
            edit_btn = QPushButton()
            edit_btn.setIcon(edit_icon)
            edit_btn.setFixedSize(22, 22)
            edit_btn.clicked.connect(partial(self._edit_column, row_data[0]))
            delete_btn = QPushButton()
            delete_btn.setIcon(delete_icon)
            delete_btn.setFixedSize(22, 22)
            delete_btn.clicked.connect(
                partial(self._delete_column, row_data[0]))
            if not is_local:
                edit_btn.setEnabled(False)
                delete_btn.setEnabled(False)
            table_view.setIndexWidget(model.index(row_idx, 0), edit_btn)
            table_view.setIndexWidget(model.index(row_idx, 1), delete_btn)
            is_not_null, is_pk = (row_data[4] == "✔"), (row_data[5] == "✔")
            not_null_switch, pk_switch = QCheckBox(), QCheckBox()
            not_null_switch.setChecked(is_not_null)
            not_null_switch.setEnabled(False)
            pk_switch.setChecked(is_pk)
            pk_switch.setEnabled(False)
            for col_idx, switch_widget in [(6, not_null_switch), (7, pk_switch)]:
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(switch_widget)
                h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                h_layout.setContentsMargins(0, 0, 0, 0)
                table_view.setIndexWidget(
                    model.index(row_idx, col_idx), container)
        return widget

    # <<< MODIFIED >>> 
    def _create_constraints_tab(self):
        container_widget = QWidget()
        main_layout = QVBoxLayout(container_widget)
        main_layout.setContentsMargins(0, 5, 0, 0)
        constraints_tab_widget = QTabWidget()
        main_layout.addWidget(constraints_tab_widget)
        constraints_by_type = self._fetch_postgres_constraints(
        ) if self.db_type == 'postgres' else self._fetch_sqlite_constraints()
        tab_definitions = [
            ("Primary Key", 'PRIMARY KEY', ['Name', 'Columns']),
            ("Foreign Key", 'FOREIGN KEY', [
             'Name', 'Columns', 'Referenced Table', 'Referenced Columns']),
            ("Check", 'CHECK', ['Name', 'Definition']),
            ("Unique", 'UNIQUE', ['Name', 'Columns'])
        ]
        for title, key, headers in tab_definitions:
            data = constraints_by_type.get(key, [])
            table_view = QTableView()
            table_view.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers)
            table_view.setAlternatingRowColors(True)
            table_view.horizontalHeader().setStyleSheet(
                "QHeaderView::section { background-color: #e0e0e0; padding: 4px; }")
            table_view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

            # table_view 
            table_view.verticalHeader().setVisible(False)
            table_view.verticalHeader().setDefaultSectionSize(26)
            table_view.setWordWrap(False)

            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(headers)
            table_view.setModel(model)

            for row_data in data:
                items = [QStandardItem(str(item)) for item in row_data]
                model.appendRow(items)

            for row in range(model.rowCount()):
                for col in range(model.columnCount()):
                    item = model.item(row, col)
                    if item:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

               # Header align + look
            table_view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

            
            for row in range(model.rowCount()):
                for col in range(model.columnCount()):
                    item = model.item(row, col)
                    if not item:
                        continue
                    if col == 0:  # Name
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    else:      
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Set resize modes for better display
            header = table_view.horizontalHeader()
            for col in range(model.columnCount()):
                header.setSectionResizeMode(
                    col, QHeaderView.ResizeMode.Interactive)
            # if model.columnCount() > 0:
            #     header.setSectionResizeMode(
            #         model.columnCount() - 1, QHeaderView.ResizeMode.Stretch)

            if model.columnCount() > 0:
                for c in range(model.columnCount()):
                    header.setSectionResizeMode(
                        c, QHeaderView.ResizeMode.Stretch)

            constraints_tab_widget.addTab(table_view, title)
        return container_widget

    def _fetch_sqlite_general_properties(self):
        return {"Name": self.table_name, "Owner": "N/A", "Schema": "main", "Table Space": "N/A", "Comment": "N/A"}

    def _fetch_all_connection_tables(self):
        tables = []
        if self.db_type != 'postgres':
            return tables
        conn = None
        try:
            pg_conn_data = {key: self.conn_data.get(
                key) for key in ['host', 'port', 'database', 'user', 'password']}
            conn = db.create_postgres_connection(**pg_conn_data)
            cursor = conn.cursor()
            cursor.execute("SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND table_type = 'BASE TABLE' ORDER BY table_schema, table_name;")
            tables = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            QMessageBox.critical(
                self, "DB Error", f"Error fetching connection tables:\n{e}")
        finally:
            if conn:
                conn.close()
        return tables

    def _fetch_postgres_inheritance(self):
        inherited_from = []
        conn = None
        try:
            pg_conn_data = {key: self.conn_data.get(
                key) for key in ['host', 'port', 'database', 'user', 'password']}
            conn = db.create_postgres_connection(**pg_conn_data)
            cursor = conn.cursor()
            query = "SELECT pn.nspname || '.' || parent.relname FROM pg_inherits JOIN pg_class AS child ON pg_inherits.inhrelid = child.oid JOIN pg_namespace AS cns ON child.relnamespace = cns.oid JOIN pg_class AS parent ON pg_inherits.inhparent = parent.oid JOIN pg_namespace AS pn ON parent.relnamespace = pn.oid WHERE child.relname = %s AND cns.nspname = %s;"
            cursor.execute(query, (self.table_name, self.schema_name))
            inherited_from = [row[0] for row in cursor.fetchall()]
        finally:
            if conn:
                conn.close()
        return inherited_from

    def _fetch_postgres_general_properties(self):
        props = {"Name": self.table_name, "Schema": self.schema_name}
        conn = None
        try:
            pg_conn_data = {key: self.conn_data.get(
                key) for key in ['host', 'port', 'database', 'user', 'password']}
            conn = db.create_postgres_connection(**pg_conn_data)
            cursor = conn.cursor()
            query = "SELECT u.usename as owner, ts.spcname as tablespace, d.description, c.relispartition FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace LEFT JOIN pg_user u ON u.usesysid = c.relowner LEFT JOIN pg_tablespace ts ON ts.oid = c.reltablespace LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0 WHERE n.nspname = %s AND c.relname = %s"
            cursor.execute(query, (self.schema_name, self.table_name))
            res = cursor.fetchone()
            if res:
                props["Owner"], props["Table Space"], props["Comment"], props[
                    "Is Partitioned"] = res[0] or "N/A", res[1] or "default", res[2] or "", res[3]
            cursor.execute(
                "SELECT rolname FROM pg_roles WHERE rolcanlogin = true ORDER BY rolname;")
            props["all_owners"] = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT spcname FROM pg_tablespace ORDER BY spcname;")
            props["all_tablespaces"] = ["default"] + [row[0]
                                                      for row in cursor.fetchall()]
        finally:
            if conn:
                conn.close()
        return props

    def _fetch_sqlite_columns(self):
        columns = []
        conn = None
        try:
            conn = db.create_sqlite_connection(self.conn_data['db_path'])
            cursor = conn.cursor()
            cursor.execute(f'PRAGMA table_info("{self.table_name}");')
            pk_cols = {row[1] for row in cursor.fetchall() if row[5] > 0}
            cursor.execute(f'PRAGMA table_info("{self.table_name}");')
            for row in cursor.fetchall():
                columns.append([row[1], row[2], "", "", "✔" if row[3]
                               else "", "✔" if row[1] in pk_cols else "", row[4] or ""])
        finally:
            if conn:
                conn.close()
        return columns

    def _fetch_postgres_columns(self):
        columns = []
        conn = None
        try:
            pg_conn_data = {key: self.conn_data.get(
                key) for key in ['host', 'port', 'database', 'user', 'password']}
            conn = db.create_postgres_connection(**pg_conn_data)
            cursor = conn.cursor()
            pk_query = "SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s AND tc.table_name = %s;"
            cursor.execute(pk_query, (self.schema_name, self.table_name))
            pk_columns = {row[0] for row in cursor.fetchall()}
            col_query = "SELECT c.column_name, c.udt_name, c.character_maximum_length, c.numeric_precision, c.numeric_scale, c.is_nullable, c.column_default, a.attislocal FROM information_schema.columns AS c JOIN pg_catalog.pg_class AS pc ON c.table_name = pc.relname JOIN pg_catalog.pg_namespace AS pn ON pc.relnamespace = pn.oid AND c.table_schema = pn.nspname JOIN pg_catalog.pg_attribute AS a ON a.attrelid = pc.oid AND a.attname = c.column_name WHERE c.table_schema = %s AND c.table_name = %s AND a.attnum > 0 AND NOT a.attisdropped ORDER BY c.ordinal_position;"
            cursor.execute(col_query, (self.schema_name, self.table_name))
            for row in cursor.fetchall():
                length_precision = row[2] if row[2] is not None else row[3]
                columns.append([row[0], row[1], length_precision or "", row[4] or "", "✔" if row[5]
                               == "NO" else "", "✔" if row[0] in pk_columns else "", row[6] or "", row[7]])
        finally:
            if conn:
                conn.close()
        return columns

    def _fetch_sqlite_constraints(self):
        constraints = {'PRIMARY KEY': [],
                       'FOREIGN KEY': [], 'UNIQUE': [], 'CHECK': []}
        conn = None
        try:
            conn = db.create_sqlite_connection(self.conn_data['db_path'])
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{self.table_name}';")
            sql_def_row = cursor.fetchone()
            sql_def = sql_def_row[0] if sql_def_row else ""
            cursor.execute(f'PRAGMA table_info("{self.table_name}");')
            pk_info = [row for row in cursor.fetchall() if row[5] > 0]
            if pk_info:
                pk_name = f"PK_{self.table_name}"
                if "CONSTRAINT" in sql_def.upper() and "PRIMARY KEY" in sql_def.upper():
                    for line in sql_def.split('\n'):
                        if "CONSTRAINT" in line.upper() and "PRIMARY KEY" in line.upper():
                            pk_name = line.split()[1].strip('`"')
                            break
                pk_cols = [row[1] for row in pk_info]
                constraints['PRIMARY KEY'].append(
                    [pk_name, ", ".join(pk_cols)])
            cursor.execute(f'PRAGMA foreign_key_list("{self.table_name}");')
            fks = {}
            for row in cursor.fetchall():
                fk_id, _, ref_table, from_col, to_col, _, _, _ = row
                if fk_id not in fks:
                    fks[fk_id] = {'from': [], 'to': [], 'ref_table': ref_table}
                fks[fk_id]['from'].append(from_col)
                fks[fk_id]['to'].append(to_col)
            fk_names = {}
            if sql_def:
                fk_counter = 0
                for line in sql_def.split('\n'):
                    if line.strip().upper().startswith("CONSTRAINT") and "FOREIGN KEY" in line.upper():
                        fk_names[fk_counter] = line.split()[1].strip('`"')
                        fk_counter += 1
            for i, fk_id in enumerate(fks):
                name = fk_names.get(
                    i, f"FK_{self.table_name}_{fks[fk_id]['ref_table']}_{fk_id}")
                constraints['FOREIGN KEY'].append([name, ", ".join(
                    fks[fk_id]['from']), fks[fk_id]['ref_table'], ", ".join(fks[fk_id]['to'])])
            cursor.execute(f'PRAGMA index_list("{self.table_name}")')
            for index in cursor.fetchall():
                if index[2] == 1 and "sqlite_autoindex" not in index[1]:
                    cursor.execute(f'PRAGMA index_info("{index[1]}")')
                    cols = ", ".join([info[2] for info in cursor.fetchall()])
                    constraints['UNIQUE'].append([index[1], cols])
            if sql_def:
                for line in sql_def.split('\n'):
                    line, upper_line = line.strip().rstrip(','), line.upper()
                    if upper_line.startswith("CONSTRAINT") and "CHECK" in upper_line:
                        constraints['CHECK'].append(
                            [line.split()[1].strip('`"'), line[line.find('('):].strip()])
                    elif upper_line.startswith("CHECK"):
                        constraints['CHECK'].append(
                            [f"CK_{self.table_name}", line[line.find('('):].strip()])
        finally:
            if conn:
                conn.close()
        return constraints

    def _fetch_postgres_constraints(self):
        constraints = {'PRIMARY KEY': [],
                       'FOREIGN KEY': [], 'UNIQUE': [], 'CHECK': []}
        conn = None
        try:
            pg_conn_data = {key: self.conn_data.get(
                key) for key in ['host', 'port', 'database', 'user', 'password']}
            conn = db.create_postgres_connection(**pg_conn_data)
            cursor = conn.cursor()
            query_key = "SELECT tc.constraint_name, tc.constraint_type, STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) FROM information_schema.table_constraints AS tc JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema WHERE tc.table_name = %s AND tc.table_schema = %s AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE') GROUP BY tc.constraint_name, tc.constraint_type;"
            cursor.execute(query_key, (self.table_name, self.schema_name))
            for name, type, cols in cursor.fetchall():
                constraints[type].append([name, cols])
            query_fk = "SELECT rc.constraint_name, STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position), ccu.table_schema, ccu.table_name, STRING_AGG(ccu.column_name, ', ' ORDER BY ccu.ordinal_position) FROM information_schema.referential_constraints AS rc JOIN information_schema.key_column_usage AS kcu ON kcu.constraint_name = rc.constraint_name AND kcu.table_schema = %s JOIN information_schema.key_column_usage AS ccu ON ccu.constraint_name = rc.unique_constraint_name AND ccu.table_schema = rc.unique_constraint_schema WHERE kcu.table_name = %s AND kcu.table_schema = %s GROUP BY rc.constraint_name, ccu.table_schema, ccu.table_name;"
            cursor.execute(query_fk, (self.schema_name,
                           self.table_name, self.schema_name))
            for name, f_cols, p_schema, p_table, p_cols in cursor.fetchall():
                constraints['FOREIGN KEY'].append(
                    [name, f_cols, f"{p_schema}.{p_table}", p_cols])
            query_check = "SELECT con.conname, pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = %s AND n.nspname = %s AND con.contype = 'c';"
            cursor.execute(query_check, (self.table_name, self.schema_name))
            for name, definition in cursor.fetchall():
                constraints['CHECK'].append([name, definition])
        finally:
            if conn:
                conn.close()
        return constraints


class QuerySignals(QObject):
    finished = pyqtSignal(dict, str, list, list, int, float, bool)
    error = pyqtSignal(str)


class ProcessSignals(QObject):
    started = pyqtSignal(str, dict)
    finished = pyqtSignal(str, str, float)
    error = pyqtSignal(str, str)


class RunnableExport(QRunnable):
    def __init__(self, process_id, item_data, table_name, export_options, signals):
        super().__init__()
        self.process_id = process_id
        self.item_data = item_data
        self.table_name = table_name
        self.export_options = export_options
        self.signals = signals

    def run(self):
        start_time = time.time()
        conn = None
        try:
            conn_data = self.item_data['conn_data']
            db_type = self.item_data.get('db_type')
            if db_type == 'sqlite':
                conn = db.create_sqlite_connection(conn_data["db_path"])
                query = f'SELECT * FROM "{self.table_name}"'
            elif db_type == 'postgres':
                conn = db.create_postgres_connection(
                    host=conn_data["host"], database=conn_data["database"], user=conn_data["user"], password=conn_data["password"], port=int(conn_data["port"]))
                schema_name = self.item_data.get("schema_name")
                query = f'SELECT * FROM "{schema_name}"."{self.table_name}"'
            else:
                raise ValueError("Unsupported database type for export.")
            if not conn:
                raise ConnectionError(
                    "Failed to connect to the database for export.")
            df = pd.read_sql_query(query, conn)
            file_path, file_format = self.export_options['filename'], self.export_options['format']
            if file_format == 'xlsx':
                df.to_excel(file_path, index=False,
                            header=self.export_options['header'])
            else:
                df.to_csv(file_path, index=False, header=self.export_options['header'], sep=self.export_options[
                          'delimiter'], encoding=self.export_options['encoding'], quotechar=self.export_options['quote'])
            time_taken = time.time() - start_time
            success_message = f"Successfully exported {len(df)} rows to {os.path.basename(file_path)}"
            self.signals.finished.emit(
                self.process_id, success_message, time_taken)
        except Exception as e:
            self.signals.error.emit(
                self.process_id, f"An error occurred during export: {e}")
        finally:
            if conn:
                conn.close()


class RunnableQuery(QRunnable):
    def __init__(self, conn_data, query, signals):
        super().__init__()
        self.conn_data = conn_data
        self.query = query
        self.signals = signals
        self._is_cancelled = False

    def cancel(self): self._is_cancelled = True

    def run(self):
        conn = None
        try:
            start_time = time.time()
            if not self.conn_data:
                raise ConnectionError("Incomplete connection information.")
            if "db_path" in self.conn_data and self.conn_data["db_path"]:
                conn = db.create_sqlite_connection(self.conn_data["db_path"])
            else:
                conn = db.create_postgres_connection(host=self.conn_data["host"], database=self.conn_data["database"],
                                                     user=self.conn_data["user"], password=self.conn_data["password"], port=int(self.conn_data["port"]))
            if not conn:
                raise ConnectionError(
                    "Failed to establish database connection.")
            cursor = conn.cursor()
            cursor.execute(self.query)
            if self._is_cancelled:
                conn.close()
                return
            row_count, is_select_query = 0, self.query.lower().strip().startswith("select")
            results, columns = [], []
            if is_select_query:
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    if not self._is_cancelled:
                        results = cursor.fetchall()
                        row_count = len(results)
                else:
                    row_count = 0
            else:
                conn.commit()
                row_count = cursor.rowcount if cursor.rowcount != -1 else 0
            if self._is_cancelled:
                conn.close()
                return
            elapsed_time = time.time() - start_time
            self.signals.finished.emit(
                self.conn_data, self.query, results, columns, row_count, elapsed_time, is_select_query)
        except Exception as e:
            if not self._is_cancelled:
                self.signals.error.emit(str(e))
        finally:
            if conn:
                conn.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SQL Client")
        self.setGeometry(100, 100, 1200, 800)
        self.thread_pool = QThreadPool.globalInstance()
        self.tab_timers = {}
        self.running_queries = {}
        self._create_actions()
        self._create_menu()
        self._create_centered_toolbar()
        self._initialize_processes_model() # <<< MODIFIED >>> Initialize shared model
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.main_splitter)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_message_label = QLabel("Ready")
        self.status.addWidget(self.status_message_label)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeView()
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.clicked.connect(self.item_clicked)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Object Explorer'])
        self.tree.setModel(self.model)
        self.left_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_vertical_splitter.addWidget(self.tree)
        self.schema_tree = QTreeView()
        self.schema_model = QStandardItemModel()
        self.schema_model.setHorizontalHeaderLabels(["Database Schema"])
        self.schema_tree.setModel(self.schema_model)
        self.schema_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.schema_tree.customContextMenuRequested.connect(
            self.show_schema_context_menu)
        self.left_vertical_splitter.addWidget(self.schema_tree)
        self.left_vertical_splitter.setSizes([400, 400])
        left_layout.addWidget(self.left_vertical_splitter)
        self.main_splitter.addWidget(left_panel)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        add_tab_btn = QPushButton("New")
        add_tab_btn.clicked.connect(self.add_tab)
        self.tab_widget.setCornerWidget(add_tab_btn)
        self.main_splitter.addWidget(self.tab_widget)
        self.thread_monitor_timer = QTimer()
        self.thread_monitor_timer.timeout.connect(
            self.update_thread_pool_status)
        self.thread_monitor_timer.start(1000)
        self.load_data()
        self.add_tab()
        self.main_splitter.setSizes([280, 920])
        self.notification_manager = NotificationManager(self)
        self._apply_styles()

    # <<< MODIFIED >>> This now only creates the central data model for processes.
    def _initialize_processes_model(self):
        self.processes_model = QStandardItemModel()
        self.processes_model.setHorizontalHeaderLabels(
            ["PID", "Type", "Status", "Server", "Object", "Time Taken (sec)", "Start Time", "Details"])

    def _create_actions(self):
        self.exit_action = QAction(QIcon("assets/exit_icon.png"), "Exit", self)
        self.exit_action.triggered.connect(self.close)
        self.execute_action = QAction(
            QIcon("assets/execute_icon.png"), "Execute", self)
        self.execute_action.triggered.connect(self.execute_query)
        self.cancel_action = QAction(
            QIcon("assets/cancel_icon.png"), "Cancel", self)
        self.cancel_action.triggered.connect(self.cancel_current_query)
        self.cancel_action.setEnabled(False)
        self.undo_action = QAction("Undo", self)
        self.undo_action.triggered.connect(self.undo_text)
        self.redo_action = QAction("Redo", self)
        self.redo_action.triggered.connect(self.redo_text)
        self.cut_action = QAction("Cut", self)
        self.cut_action.triggered.connect(self.cut_text)
        self.copy_action = QAction("Copy", self)
        self.copy_action.triggered.connect(self.copy_text)
        self.paste_action = QAction("Paste", self)
        self.paste_action.triggered.connect(self.paste_text)
        self.delete_action = QAction("Delete", self)
        self.delete_action.triggered.connect(self.delete_text)
        self.query_tool_action = QAction("Query Tool", self)
        self.query_tool_action.triggered.connect(self.add_tab)
        self.restore_action = QAction("Restore Layout", self)
        self.restore_action.triggered.connect(self.restore_tool)
        self.refresh_action = QAction("Refresh Explorer", self)
        self.refresh_action.triggered.connect(self.refresh_object_explorer)
        self.minimize_action = QAction("Minimize", self)
        self.minimize_action.triggered.connect(self.showMinimized)
        self.zoom_action = QAction("Zoom", self)
        self.zoom_action.triggered.connect(self.toggle_maximize)
        self.sqlite_help_action = QAction("SQLite Website", self)
        self.sqlite_help_action.triggered.connect(
            lambda: self.open_help_url("https://www.sqlite.org/"))
        self.postgres_help_action = QAction("PostgreSQL Website", self)
        self.postgres_help_action.triggered.connect(
            lambda: self.open_help_url("https://www.postgresql.org/"))
        self.oracle_help_action = QAction("Oracle Website", self)
        self.oracle_help_action.triggered.connect(
            lambda: self.open_help_url("https://www.oracle.com/database/"))
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about_dialog)

    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.exit_action)
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)
        actions_menu = menubar.addMenu("&Actions")
        actions_menu.addAction(self.execute_action)
        actions_menu.addAction(self.cancel_action)
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.query_tool_action)
        tools_menu.addAction(self.refresh_action)
        tools_menu.addAction(self.restore_action)
        window_menu = menubar.addMenu("&Window")
        window_menu.addAction(self.minimize_action)
        window_menu.addAction(self.zoom_action)
        window_menu.addSeparator()
        close_action = QAction("Close", self)
        close_action.triggered.connect(self.close)
        window_menu.addAction(close_action)
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.sqlite_help_action)
        help_menu.addAction(self.postgres_help_action)
        help_menu.addAction(self.oracle_help_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)

    def _create_centered_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        left_spacer = QWidget()
        left_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        right_spacer = QWidget()
        right_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(left_spacer)
        toolbar.addAction(self.exit_action)
        toolbar.addAction(self.execute_action)
        toolbar.addAction(self.cancel_action)
        toolbar.addWidget(right_spacer)
        self.addToolBar(toolbar)

    def show_about_dialog(self):
        QMessageBox.about(self, "About SQL Client", "<b>SQL Client Application</b><p>Version 1.0.0</p><p>This is a versatile SQL client designed to connect to and manage multiple database systems including PostgreSQL and SQLite.</p><p><b>Features:</b></p><ul><li>Object Explorer for database schemas</li><li>Multi-tab query editor with syntax highlighting</li><li>Query history per connection</li><li>Asynchronous query execution to keep the UI responsive</li></ul><p>Developed to provide a simple and effective tool for database management.</p>")

    def _get_current_editor(self):
        current_tab = self.tab_widget.currentWidget()
        if not current_tab:
            return None
        editor_stack = current_tab.findChild(QStackedWidget, "editor_stack")
        if editor_stack and editor_stack.currentIndex() == 0:
            return current_tab.findChild(CodeEditor, "query_editor")
        return None

    def undo_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.undo()

    def redo_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.redo()

    def cut_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.cut()

    def copy_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.copy()

    def paste_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.paste()

    def delete_text(self):
        editor = self._get_current_editor()
        if editor:
            editor.textCursor().removeSelectedText()

    def restore_tool(self):
        self.main_splitter.setSizes([280, 920])
        self.left_vertical_splitter.setSizes([240, 360])
        current_tab = self.tab_widget.currentWidget()
        if current_tab:
            tab_splitter = current_tab.findChild(
                QSplitter, "tab_vertical_splitter")
            if tab_splitter:
                tab_splitter.setSizes([300, 300])
        self.status.showMessage("Layout restored to defaults.", 3000)

    def refresh_object_explorer(self):
        self.load_data()
        self.status.showMessage("Object Explorer refreshed.", 3000)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def open_help_url(self, url_string):
        if not QDesktopServices.openUrl(QUrl(url_string)):
            QMessageBox.warning(
                self, "Open URL", f"Could not open URL: {url_string}")

    def update_thread_pool_status(self):
        self.status.showMessage(
            f"ThreadPool: {self.thread_pool.activeThreadCount()} active of {self.thread_pool.maxThreadCount()}", 3000)
        
    def _apply_styles(self):
        primary_color, header_color, selection_color = "#D3D3D3", "#A9A9A9", "#A9A9A9"
        text_color_on_primary, alternate_row_color, border_color = "#000000", "#f0f0f0", "#A9A9A9"
        self.setStyleSheet(f"""QMainWindow, QToolBar, QStatusBar {{ background-color: {primary_color}; color: {text_color_on_primary}; }} QTreeView {{ background-color: white; alternate-background-color: {alternate_row_color}; border: 1px solid {border_color}; }} QTableView {{ alternate-background-color: {alternate_row_color}; background-color: white; gridline-color: #a9a9a9; border: 1px solid {border_color}; font-family: Arial, sans-serif; font-size: 9pt;}} QTableView::item {{ padding: 4px; }} QTableView::item:selected {{ background-color: {selection_color}; color: white; }} QHeaderView::section {{ background-color: {header_color}; color: white; padding: 4px; border: none; border-right: 1px solid #d3d3d3; border-bottom: 1px solid {border_color}; font-weight: bold; font-size: 9pt;  }} QTableView QTableCornerButton::section {{ background-color: {header_color}; border: 1px solid {border_color}; }} #resultsHeader QPushButton, #editorHeader QPushButton {{ background-color: #ffffff; border: 1px solid {border_color}; padding: 5px 15px; font-size: 9pt; }} #resultsHeader QPushButton:hover, #editorHeader QPushButton:hover {{ background-color: {primary_color}; }} #resultsHeader QPushButton:checked, #editorHeader QPushButton:checked {{ background-color: {selection_color}; border-bottom: 1px solid {selection_color}; font-weight: bold; color: white; }} #resultsHeader, #editorHeader {{ background-color: {alternate_row_color}; padding-bottom: -1px; }} #messageView, #history_details_view, QTextEdit {{ font-family: Consolas, monospace; font-size: 10pt; background-color: white; border: 1px solid {border_color}; }} #tab_status_label {{ padding: 3px 5px; background-color: {alternate_row_color}; border-top: 1px solid {border_color}; }} QGroupBox {{ font-size: 9pt; font-weight: bold; color: {text_color_on_primary}; }} QTabWidget::pane {{ border-top: 1px solid {border_color}; }} QTabBar::tab {{ background: #E0E0E0; border: 1px solid {border_color}; padding: 5px 10px; border-bottom: none; }} QTabBar::tab:selected {{ background: {selection_color}; color: white; }} QComboBox {{ border: 1px solid {border_color}; padding: 2px; background-color: white; }}""")
    
    def add_tab(self):
        tab_content = QWidget()
        layout = QVBoxLayout(tab_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        db_combo_box = QComboBox()
        db_combo_box.setObjectName("db_combo_box")
        layout.addWidget(db_combo_box)
        self.load_joined_items(db_combo_box)
        main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        main_vertical_splitter.setObjectName("tab_vertical_splitter")
        layout.addWidget(main_vertical_splitter)
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_header = QWidget()
        editor_header.setObjectName("editorHeader")
        editor_header_layout = QHBoxLayout(editor_header)
        editor_header_layout.setContentsMargins(0, 2, 5, 0)
        editor_header_layout.setSpacing(2)
        query_view_btn, history_view_btn = QPushButton(
            "Query"), QPushButton("Query History")
        history_view_btn.setMinimumWidth(120)
        query_view_btn.setCheckable(True)
        history_view_btn.setCheckable(True)
        query_view_btn.setChecked(True)
        editor_header_layout.addWidget(query_view_btn)
        editor_header_layout.addWidget(history_view_btn)
        editor_header_layout.addStretch()
        editor_layout.addWidget(editor_header)
        editor_stack = QStackedWidget()
        editor_stack.setObjectName("editor_stack")

        text_edit = CodeEditor()
        text_edit.setPlaceholderText("Write Query")
        text_edit.setObjectName("query_editor")

        editor_stack.addWidget(text_edit)
        history_widget = QSplitter(Qt.Orientation.Horizontal)
        history_list_view = QTreeView()
        history_list_view.setObjectName("history_list_view")
        history_list_view.setHeaderHidden(True)
        history_list_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        history_details_group = QGroupBox("Query Details")
        history_details_layout = QVBoxLayout(history_details_group)
        history_details_view = QTextEdit()
        history_details_view.setObjectName("history_details_view")
        history_details_view.setReadOnly(True)
        history_details_layout.addWidget(history_details_view)
        history_button_layout = QHBoxLayout()
        copy_history_btn, copy_to_edit_btn, remove_history_btn, remove_all_history_btn = QPushButton(
            "Copy"), QPushButton("Copy to Edit Query"), QPushButton("Remove"), QPushButton("Remove All")
        history_button_layout.addStretch()
        history_button_layout.addWidget(copy_history_btn)
        history_button_layout.addWidget(copy_to_edit_btn)
        history_button_layout.addWidget(remove_history_btn)
        history_button_layout.addWidget(remove_all_history_btn)
        history_details_layout.addLayout(history_button_layout)
        history_widget.addWidget(history_list_view)
        history_widget.addWidget(history_details_group)
        history_widget.setSizes([400, 400])
        editor_stack.addWidget(history_widget)
        editor_layout.addWidget(editor_stack)
        main_vertical_splitter.addWidget(editor_container)

        def switch_editor_view(index):
            editor_stack.setCurrentIndex(index)
            query_view_btn.setChecked(index == 0)
            history_view_btn.setChecked(index == 1)
            if index == 1:
                self.load_connection_history(tab_content)
        query_view_btn.clicked.connect(lambda: switch_editor_view(0))
        history_view_btn.clicked.connect(lambda: switch_editor_view(1))
        db_combo_box.currentIndexChanged.connect(lambda: editor_stack.currentIndex(
        ) == 1 and self.load_connection_history(tab_content))
        history_list_view.clicked.connect(
            lambda index: self.display_history_details(index, tab_content))
        copy_history_btn.clicked.connect(
            lambda: self.copy_history_query(tab_content))
        copy_to_edit_btn.clicked.connect(
            lambda: self.copy_history_to_editor(tab_content))
        remove_history_btn.clicked.connect(
            lambda: self.remove_selected_history(tab_content))
        remove_all_history_btn.clicked.connect(
            lambda: self.remove_all_history_for_connection(tab_content))
        
        results_container = QWidget()
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 5, 0, 0)
        results_layout.setSpacing(1)
        results_header = QWidget()
        results_header.setObjectName("resultsHeader")
        header_layout = QHBoxLayout(results_header)
        header_layout.setContentsMargins(0, 2, 5, 0)
        header_layout.setSpacing(2)
        
        output_btn, message_btn, notification_btn, processes_btn = QPushButton(
            "Data Output"), QPushButton("Messages"), QPushButton("Notifications"), QPushButton("Processes")
        output_btn.setMinimumWidth(100)
        message_btn.setMinimumWidth(100)
        notification_btn.setMinimumWidth(100)
        processes_btn.setMinimumWidth(100)
        output_btn.setMinimumWidth(100)
        output_btn.setCheckable(True)
        message_btn.setCheckable(True)
        notification_btn.setCheckable(True)
        processes_btn.setCheckable(True)
        output_btn.setChecked(True)
        
        header_layout.addWidget(output_btn)
        header_layout.addWidget(message_btn)
        header_layout.addWidget(notification_btn)
        header_layout.addWidget(processes_btn)
        
        # <<< MODIFICATION START >>> - Button removed
        # export_btn = QPushButton("Export Results")
        # export_btn.clicked.connect(self.export_current_results)
        # header_layout.addWidget(export_btn)
        # <<< MODIFICATION END >>>

        header_layout.addStretch()
        results_layout.addWidget(results_header)
        
        results_stack = QStackedWidget()
        results_stack.setObjectName("results_stacked_widget")
        
        table_view = QTableView()
        table_view.setObjectName("result_table")
        table_view.setAlternatingRowColors(True)

        # <<< MODIFICATION START >>> - Context menu added
        table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table_view.customContextMenuRequested.connect(self.show_results_context_menu)
        # <<< MODIFICATION END >>>

        results_stack.addWidget(table_view)
        table_view.verticalHeader().setVisible(False)
        table_view.verticalHeader().setDefaultSectionSize(28)

        message_view = QTextEdit()
        message_view.setObjectName("message_view")
        message_view.setReadOnly(True)
        results_stack.addWidget(message_view)
        
        notification_view = QLabel("Notifications will appear here.")
        notification_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        results_stack.addWidget(notification_view)
        
        processes_view = QTableView()
        processes_view.setObjectName("processes_view")
        processes_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        processes_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        processes_view.setAlternatingRowColors(True)
        processes_view.horizontalHeader().setStretchLastSection(True)
        processes_view.setModel(self.processes_model)
        processes_view.setColumnWidth(0, 150)
        processes_view.setColumnWidth(1, 100)
        processes_view.setColumnWidth(2, 100)
        processes_view.setColumnWidth(3, 150)
        processes_view.setColumnWidth(4, 150)
        processes_view.setColumnWidth(5, 120)
        processes_view.setColumnWidth(6, 150)
        results_stack.addWidget(processes_view)

        spinner_overlay_widget = QWidget()
        spinner_layout = QHBoxLayout(spinner_overlay_widget)
        spinner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_movie = QMovie("assets/spinner.gif")
        spinner_label = QLabel()
        spinner_label.setObjectName("spinner_label")
        if not spinner_movie.isValid():
            spinner_label.setText("Loading...")
        else:
            spinner_label.setMovie(spinner_movie)
            spinner_movie.setScaledSize(QSize(32, 32))
        loading_text_label = QLabel("Waiting for query to complete")
        font = QFont()
        font.setPointSize(10)
        loading_text_label.setFont(font)
        loading_text_label.setStyleSheet("color: #555;")
        spinner_layout.addWidget(spinner_label)
        spinner_layout.addWidget(loading_text_label)
        results_stack.addWidget(spinner_overlay_widget)
        results_layout.addWidget(results_stack)
        
        tab_status_label = QLabel("Ready")
        tab_status_label.setObjectName("tab_status_label")
        results_layout.addWidget(tab_status_label)
        
        button_group = [output_btn, message_btn, notification_btn, processes_btn]

        def switch_results_view(index):
            if results_stack.currentIndex() != 4:
                results_stack.setCurrentIndex(index)
                for i, btn in enumerate(button_group):
                    btn.setChecked(i == index)
        
        output_btn.clicked.connect(lambda: switch_results_view(0))
        message_btn.clicked.connect(lambda: switch_results_view(1))
        notification_btn.clicked.connect(lambda: switch_results_view(2))
        processes_btn.clicked.connect(lambda: switch_results_view(3))

        main_vertical_splitter.addWidget(results_container)
        main_vertical_splitter.setSizes([300, 300])
        tab_content.setLayout(layout)
        
        worksheet_count = self.tab_widget.count()
        index = self.tab_widget.insertTab(
            worksheet_count, tab_content, f"Worksheet {worksheet_count + 1}")
        self.tab_widget.setCurrentIndex(index)
        return tab_content

    # <<< NEW METHOD START >>>
    #position->user mouse position
    def show_results_context_menu(self, position):
        """Shows a context menu on the results table for exporting data."""
        table_view = self.sender()
        if not isinstance(table_view, QTableView):
            return

        menu = QMenu()
        model = table_view.model()
        selection_model = table_view.selectionModel()

        # Automatically select the row that was right-clicked
        index = table_view.indexAt(position)
        if index.isValid():
            table_view.selectRow(index.row())

        # Action to export only the selected row
        export_selected_action = QAction("Export Selected Row", self)
        export_selected_action.triggered.connect(self.export_selected_result_row)
        
        # Action to export all rows (original functionality)
        export_all_action = QAction("Export All Rows", self)
        export_all_action.triggered.connect(self.export_current_results)
        
        # Enable actions based on data and selection
        if not model or model.rowCount() == 0:
            export_selected_action.setEnabled(False)
            export_all_action.setEnabled(False)
        elif not selection_model or not selection_model.hasSelection():
            export_selected_action.setEnabled(False)

        menu.addAction(export_selected_action)
        menu.addAction(export_all_action)
        
        # Show the menu at the cursor's global position
        menu.exec(table_view.viewport().mapToGlobal(position))
    # <<< NEW METHOD END >>>

    # <<< NEW METHOD START >>>
    def export_selected_result_row(self):
        """Exports only the currently selected row from the results table."""
        current_tab = self.tab_widget.currentWidget()
        if not current_tab:
            return

        table_view = current_tab.findChild(QTableView, "result_table")
        model = table_view.model()
        selection_model = table_view.selectionModel()

        if not model or model.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
            return
        
        if not selection_model or not selection_model.hasSelection() or not selection_model.selectedRows():
            QMessageBox.warning(self, "No Selection", "Please select a row to export.")
            return

        # Prepare data for the selected row
        selected_row_index = selection_model.selectedRows()[0].row()#.row which find the row index
        columns = [model.headerData(i, Qt.Orientation.Horizontal) for i in range(model.columnCount())]
        row_data = [model.data(model.index(selected_row_index, col)) for col in range(model.columnCount())]
        
        dialog = ExportDialog(self, f"selected_row_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        options = dialog.get_options()
        file_path = options['filename']
        if not file_path:
            QMessageBox.warning(self, "No Filename", "Export cancelled. No filename specified.")
            return

        try:
            self.status_message_label.setText("Exporting selected row...")
            QApplication.processEvents()

            df = pd.DataFrame([row_data], columns=columns)

            if options['format'] == 'xlsx':
                df.to_excel(file_path, index=False, header=options['header'])
            else:
                df.to_csv(file_path, index=False, header=options['header'], sep=options['delimiter'],
                          encoding=options['encoding'], quotechar=options['quote'])

            QMessageBox.information(self, "Success", f"Selected row successfully exported to:\n{file_path}")
            self.status_message_label.setText(f"Exported 1 row to {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"An error occurred while exporting the data:\n{e}")
            self.status_message_label.setText("Export failed.")
    # <<< NEW METHOD END >>>

    def export_current_results(self):
        current_tab = self.tab_widget.currentWidget()
        if not current_tab:
            return
        table_view = current_tab.findChild(QTableView, "result_table")
        model = table_view.model()
        if not model or model.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
            return
        dialog = ExportDialog(
            self, f"query_results_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.get_options()
        file_path = options['filename']
        if not file_path:
            QMessageBox.warning(self, "No Filename",
                                "Export cancelled. No filename specified.")
            return
        try:
            self.status_message_label.setText("Exporting Data")
            QApplication.processEvents()
            columns = [model.headerData(i, Qt.Orientation.Horizontal)
                       for i in range(model.columnCount())]
            data = [[model.data(model.index(row, col)) for col in range(
                model.columnCount())] for row in range(model.rowCount())]
            df = pd.DataFrame(data, columns=columns)
            if options['format'] == 'xlsx':
                df.to_excel(file_path, index=False, header=options['header'])
            else:
                df.to_csv(file_path, index=False, header=options['header'], sep=options['delimiter'],
                          encoding=options['encoding'], quotechar=options['quote'])
            QMessageBox.information(
                self, "Success", f"Data successfully exported to:\n{file_path}")
            self.status_message_label.setText(
                f"Exported {len(data)} rows to {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", f"An error occurred while exporting the data:\n{e}")
            self.status_message_label.setText("Export failed.")

    def close_tab(self, index):
        if self.tab_widget.count() <= 1:
            QMessageBox.information(
                self, "Cannot Close", "At least one worksheet tab must remain open.")
            return
        
        tab_to_close = self.tab_widget.widget(index)
        if tab_to_close in self.running_queries:
            self.running_queries[tab_to_close].cancel()
            del self.running_queries[tab_to_close]
            if not self.running_queries:
                self.cancel_action.setEnabled(False)
        if tab_to_close in self.tab_timers:
            self.tab_timers[tab_to_close]["timer"].stop()
            if "timeout_timer" in self.tab_timers[tab_to_close]:
                self.tab_timers[tab_to_close]["timeout_timer"].stop()
            del self.tab_timers[tab_to_close]
            
        self.tab_widget.removeTab(index)
        self.renumber_tabs()

    def renumber_tabs(self):
        for i in range(self.tab_widget.count()):
            self.tab_widget.setTabText(i, f"Worksheet {i + 1}")

    def load_data(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Object Explorer"])
        for cat_data in db.get_hierarchy_data():
            cat_item = QStandardItem(cat_data['name'])
            cat_item.setEditable(False)
            cat_item.setData(cat_data['id'], Qt.ItemDataRole.UserRole + 1)
            for subcat_data in cat_data['subcategories']:
                subcat_item = QStandardItem(subcat_data['name'])
                subcat_item.setEditable(False)
                subcat_item.setData(
                    subcat_data['id'], Qt.ItemDataRole.UserRole + 1)
                for item_data in subcat_data['items']:
                    item_item = QStandardItem(item_data['name'])
                    item_item.setEditable(False)
                    item_item.setData(item_data, Qt.ItemDataRole.UserRole)
                    subcat_item.appendRow(item_item)
                cat_item.appendRow(subcat_item)
            self.model.appendRow(cat_item)

    def item_clicked(self, index):
        item = self.model.itemFromIndex(index)
        depth = self.get_item_depth(item)
        self.schema_model.clear()
        self.schema_model.setHorizontalHeaderLabels(["Database Schema"])
        if depth == 3:
            conn_data = item.data(Qt.ItemDataRole.UserRole)
            if not conn_data:
                return
            parent_group = item.parent()
            if not parent_group:
                return
            main_category = parent_group.parent()
            if not main_category:
                return
            category_name = main_category.text().lower()
            if "postgres" in category_name and conn_data.get("host"):
                self.status.showMessage(
                    f"Loading schema for {conn_data.get('name')}...", 3000)
                self.load_postgres_schema(conn_data)
            elif "sqlite" in category_name and conn_data.get("db_path"):
                self.status.showMessage(
                    f"Loading schema for {conn_data.get('name')}...", 3000)
                self.load_sqlite_schema(conn_data)
            elif "oracle" in category_name:
                self.status.showMessage(
                    "Oracle connections are not currently supported.", 5000)
                QMessageBox.information(
                    self, "Not Supported", "Connecting to Oracle databases is not supported in this version.")
            else:
                self.status.showMessage("Unknown connection type.", 3000)

    def get_item_depth(self, item):
        depth, parent = 0, item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        return depth + 1

    def show_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        depth = self.get_item_depth(item)
        menu = QMenu()
        if depth == 1:
            add_subcat = QAction("Add Group", self)
            add_subcat.triggered.connect(lambda: self.add_subcategory(item))
            menu.addAction(add_subcat)
        elif depth == 2:
            parent_category_item = item.parent()
            if parent_category_item:
                category_name = parent_category_item.text()
                if "postgres" in category_name.lower():
                    add_pg_action = QAction(
                        "Add New PostgreSQL Connection", self)
                    add_pg_action.triggered.connect(
                        lambda: self.add_postgres_connection(item))
                    menu.addAction(add_pg_action)
                elif "sqlite" in category_name.lower():
                    add_sqlite_action = QAction(
                        "Add New SQLite Connection", self)
                    add_sqlite_action.triggered.connect(
                        lambda: self.add_sqlite_connection(item))
                    menu.addAction(add_sqlite_action)
        elif depth == 3:
            conn_data = item.data(Qt.ItemDataRole.UserRole)
            if conn_data:
                view_details_action = QAction("View details", self)
                view_details_action.triggered.connect(
                    lambda: self.show_connection_details(item))
                menu.addAction(view_details_action)
                menu.addSeparator()
                if conn_data.get("db_path"):
                    edit_action = QAction("Edit Connection", self)
                    edit_action.triggered.connect(lambda: self.edit_item(item))
                    menu.addAction(edit_action)
                elif conn_data.get("host"):
                    edit_action = QAction("Edit Connection", self)
                    edit_action.triggered.connect(
                        lambda: self.edit_pg_item(item))
                    menu.addAction(edit_action)
                delete_action = QAction("Delete Connection", self)
                delete_action.triggered.connect(lambda: self.delete_item(item))
                menu.addAction(delete_action)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def show_connection_details(self, item):
      conn_data = item.data(Qt.ItemDataRole.UserRole)
      if not conn_data:
          QMessageBox.warning(self, "Error", "Could not retrieve connection data.")
          return

      details_title = f"Connection Details: {conn_data.get('name')}"

      if conn_data.get("host"):
          details_text = (
              f"<b>Name:</b> {conn_data.get('name', 'N/A')}<br>"
              f"<b>Type:</b> PostgreSQL<br>"
              f"<b>Host:</b> {conn_data.get('host', 'N/A')}<br>"
              f"<b>Port:</b> {conn_data.get('port', 'N/A')}<br>"
              f"<b>Database:</b> {conn_data.get('database', 'N/A')}<br>"
              f"<b>User:</b> {conn_data.get('user', 'N/A')}"
          )
      elif conn_data.get("db_path"):
          details_text = (
              f"<b>Name:</b> {conn_data.get('name', 'N/A')}<br>"
              f"<b>Type:</b> SQLite<br>"
              f"<b>Database Path:</b> {conn_data.get('db_path', 'N/A')}"
          )
      else:
          details_text = "Could not determine connection type or details."

      msg = QMessageBox(self)
      msg.setWindowTitle(details_title)
      msg.setIcon(QMessageBox.Icon.Information)
      msg.setStandardButtons(QMessageBox.StandardButton.Ok)

      label = QLabel(details_text)
      label.setTextFormat(Qt.TextFormat.RichText)
      label.setWordWrap(True)
      label.setMinimumSize(400, 200)
      msg.layout().addWidget(label, 0, 1)

      msg.exec()


    def add_subcategory(self, parent_item):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name:
            db.add_subcategory(name, parent_item.data(
                Qt.ItemDataRole.UserRole+1))
            self.load_data()

    def add_postgres_connection(self, parent_item):
        dialog = PostgresConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                db.add_item(dialog.get_data(), parent_item.data(
                    Qt.ItemDataRole.UserRole + 1))
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to save PostgreSQL connection:\n{e}")

    def add_sqlite_connection(self, parent_item):
        dialog = SQLiteConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                db.add_item(dialog.get_data(), parent_item.data(
                    Qt.ItemDataRole.UserRole + 1))
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to save SQLite connection:\n{e}")

    def edit_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        if conn_data and conn_data.get("db_path"):
            dialog = SQLiteConnectionDialog(self, conn_data=conn_data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    db.update_item(dialog.get_data())
                    self.load_data()
                    self.refresh_all_comboboxes()
                except Exception as e:
                    QMessageBox.critical(
                        self, "Error", f"Failed to update SQLite connection:\n{e}")

    def edit_pg_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        if not conn_data:
            return
        dialog = PostgresConnectionDialog(self, is_editing=True)
        dialog.name_input.setText(conn_data.get("name", ""))
        dialog.host_input.setText(conn_data.get("host", ""))
        dialog.port_input.setText(str(conn_data.get("port", "")))
        dialog.db_input.setText(conn_data.get("database", ""))
        dialog.user_input.setText(conn_data.get("user", ""))
        dialog.password_input.setText(conn_data.get("password", ""))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            new_data["id"] = conn_data.get("id")
            try:
                db.update_item(new_data)
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to update PostgreSQL connection:\n{e}")

    def delete_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete Connection", "Are you sure you want to delete this connection?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                db.delete_item(conn_data.get("id"))
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to delete item:\n{e}")

    def refresh_all_comboboxes(self):
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            combo_box = tab.findChild(QComboBox, "db_combo_box")
            if combo_box:
                self.load_joined_items(combo_box)

    def load_joined_items(self, combo_box):
        try:
            current_data = combo_box.currentData()
            combo_box.clear()
            for item in db.get_all_connections_from_db():
                conn_data = {key: item[key]
                             for key in item if key != 'display_name'}
                combo_box.addItem(item["display_name"], conn_data)
            if current_data:
                for i in range(combo_box.count()):
                    if combo_box.itemData(i) and combo_box.itemData(i)['id'] == current_data['id']:
                        combo_box.setCurrentIndex(i)
                        break
        except Exception as e:
            self.status.showMessage(f"Error loading connections: {e}", 4000)

    def execute_query(self):
        current_tab = self.tab_widget.currentWidget()
        #current_tab local variable
        if not current_tab:
            return
        editor_stack = current_tab.findChild(QStackedWidget, "editor_stack")
        if editor_stack and editor_stack.currentIndex() == 1:
            QMessageBox.information(
                self, "Info", "Cannot execute from History view. Switch to the Query view.")
            return
        if current_tab in self.running_queries:
            QMessageBox.warning(self, "Query in Progress",
                                "A query is already running in this tab.")
            return
        query_editor = current_tab.findChild(CodeEditor, "query_editor")
        db_combo_box = current_tab.findChild(QComboBox, "db_combo_box")
        conn_data, query = db_combo_box.currentData(), query_editor.toPlainText().strip()
        if not conn_data or not query:
            self.status.showMessage("Connection or query is empty", 3000)
            return
        results_stack = current_tab.findChild(
            QStackedWidget, "results_stacked_widget")
        spinner_label = results_stack.findChild(QLabel, "spinner_label")
        results_stack.setCurrentIndex(4)
        if spinner_label and spinner_label.movie():
            spinner_label.movie().start()
        tab_status_label = current_tab.findChild(QLabel, "tab_status_label")
        progress_timer, start_time, timeout_timer = QTimer(
            self), time.time(), QTimer(self)
        timeout_timer.setSingleShot(True)
        self.tab_timers[current_tab] = {
            "timer": progress_timer, "start_time": start_time, "timeout_timer": timeout_timer}
        progress_timer.timeout.connect(
            partial(self.update_timer_label, tab_status_label, current_tab))
        progress_timer.start(100)
        signals = QuerySignals()
        runnable = RunnableQuery(conn_data, query, signals)
        signals.finished.connect(
            partial(self.handle_query_result, current_tab))
        signals.error.connect(partial(self.handle_query_error, current_tab))
        self.running_queries[current_tab] = runnable
        self.cancel_action.setEnabled(True)
        self.thread_pool.start(runnable)

    def update_timer_label(self, label, tab):
        if not label or tab not in self.tab_timers:
            return
        elapsed_seconds = time.time() - self.tab_timers[tab]["start_time"]
        minutes, seconds_with_ms = divmod(elapsed_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        seconds_int, milliseconds = int(seconds_with_ms), int(
            (seconds_with_ms - int(seconds_with_ms)) * 1000)
        label.setText(
            f"Running... {hours:02.0f}:{minutes:02.0f}:{seconds_int:02d}.{milliseconds:03d}")

    def format_duration_ms(self, total_seconds):
        if total_seconds is None:
            return "00:00:00.000"
        seconds_int = int(total_seconds)
        milliseconds = int((total_seconds - seconds_int) * 1000)
        minutes, seconds = divmod(seconds_int, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def handle_query_error(self, current_tab, error_message):
        if current_tab in self.tab_timers:
            self.tab_timers[current_tab]["timer"].stop()
            self.tab_timers[current_tab]["timeout_timer"].stop()
            del self.tab_timers[current_tab]
        message_view = current_tab.findChild(QTextEdit, "message_view")
        tab_status_label = current_tab.findChild(QLabel, "tab_status_label")
        message_view.setText(f"Error:\n\n{error_message}")
        tab_status_label.setText(f"Error: {error_message}")
        self.status_message_label.setText("Error occurred")
        self.stop_spinner(current_tab, success=False)
        if current_tab in self.running_queries:
            del self.running_queries[current_tab]
        if not self.running_queries:
            self.cancel_action.setEnabled(False)

    def stop_spinner(self, current_tab, success=True):
        if not current_tab:
            return
        stacked_widget = current_tab.findChild(
            QStackedWidget, "results_stacked_widget")
        if stacked_widget:
            spinner_label = stacked_widget.findChild(QLabel, "spinner_label")
            if spinner_label and spinner_label.movie():
                spinner_label.movie().stop()
            header = current_tab.findChild(QWidget, "resultsHeader")
            buttons = header.findChildren(QPushButton)
            if success:
                stacked_widget.setCurrentIndex(0)
                if buttons:
                    buttons[0].setChecked(True)
                    buttons[1].setChecked(False)
                    buttons[2].setChecked(False)
                    buttons[3].setChecked(False)
            else:
                stacked_widget.setCurrentIndex(1)
                if buttons:
                    buttons[0].setChecked(False)
                    buttons[1].setChecked(True)
                    buttons[2].setChecked(False)
                    buttons[3].setChecked(False)

    def handle_query_result(self, current_tab, conn_data, query, results, columns, row_count, elapsed_time, is_select_query):
        if current_tab in self.tab_timers:
            self.tab_timers[current_tab]["timer"].stop()
            self.tab_timers[current_tab]["timeout_timer"].stop()
            del self.tab_timers[current_tab]
        self.save_query_to_history(
            conn_data, query, "Success", row_count, elapsed_time)
        table_view, message_view, tab_status_label = current_tab.findChild(QTableView, "result_table"), current_tab.findChild(
            QTextEdit, "message_view"), current_tab.findChild(QLabel, "tab_status_label")
        formatted_time = self.format_duration_ms(elapsed_time)
        if is_select_query:
            model = QStandardItemModel()
            model.setHorizontalHeaderLabels(columns)
            for row in results:
                model.appendRow([QStandardItem(str(cell)) for cell in row])
            table_view.setModel(model)
            msg, status = f"Query executed successfully.\n\nTotal rows: {row_count}\nTime: {formatted_time}", f"Query executed successfully | Total rows: {row_count} | Query complete {formatted_time}"
        else:
            table_view.setModel(QStandardItemModel())
            msg, status = f"Command executed successfully.\n\nRows affected: {row_count}\nTime: {formatted_time}", f"Command executed successfully | Rows affected: {row_count} | Query complete {formatted_time}"
        message_view.setText(msg)
        tab_status_label.setText(status)
        self.status_message_label.setText("Ready")
        self.stop_spinner(current_tab, success=True)
        if current_tab in self.running_queries:
            del self.running_queries[current_tab]
        if not self.running_queries:
            self.cancel_action.setEnabled(False)

    def cancel_current_query(self):
        current_tab = self.tab_widget.currentWidget()
        runnable = self.running_queries.get(current_tab)
        if runnable:
            runnable.cancel()
            if current_tab in self.tab_timers:
                self.tab_timers[current_tab]["timer"].stop()
                self.tab_timers[current_tab]["timeout_timer"].stop()
                del self.tab_timers[current_tab]
            cancel_message = "Query cancelled by user."
            current_tab.findChild(
                QTextEdit, "message_view").setText(cancel_message)
            current_tab.findChild(
                QLabel, "tab_status_label").setText(cancel_message)
            self.stop_spinner(current_tab, success=False)
            self.status_message_label.setText("Query Cancelled")
            if current_tab in self.running_queries:
                del self.running_queries[current_tab]
            if not self.running_queries:
                self.cancel_action.setEnabled(False)

    def save_query_to_history(self, conn_data, query, status, rows, duration):
        if not conn_data.get("id"):
            return
        try:
            db.save_query_history(conn_data.get(
                "id"), query, status, rows, duration)
        except Exception as e:
            self.status.showMessage(
                f"Could not save query to history: {e}", 4000)

    def load_connection_history(self, current_tab):
        history_list_view, history_details_view = current_tab.findChild(
            QTreeView, "history_list_view"), current_tab.findChild(QTextEdit, "history_details_view")
        db_combo_box = current_tab.findChild(QComboBox, "db_combo_box")
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Connection History'])
        history_list_view.setModel(model)
        history_details_view.clear()
        conn_data = db_combo_box.currentData()
        if not conn_data:
            return
        try:
            for row in db.get_query_history(conn_data.get("id")):
                history_id, query, ts, status, rows, duration = row
                short_query = ' '.join(query.split())[
                    :70] + ('...' if len(query) > 70 else '')
                dt = datetime.datetime.fromisoformat(ts)
                item = QStandardItem(
                    f"{short_query}\n{dt.strftime('%Y-%m-%d %H:%M:%S')}")
                item.setData({"id": history_id, "query": query, "timestamp": dt.strftime(
                    '%Y-%m-%d %H:%M:%S'), "status": status, "rows": rows, "duration": f"{duration:.3f} sec"}, Qt.ItemDataRole.UserRole)
                model.appendRow(item)
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to load query history:\n{e}")

    def display_history_details(self, index, current_tab):
        history_details_view = current_tab.findChild(
            QTextEdit, "history_details_view")
        if not index.isValid() or not history_details_view:
            return
        data = index.model().itemFromIndex(index).data(Qt.ItemDataRole.UserRole)
        history_details_view.setText(
            f"Timestamp: {data['timestamp']}\nStatus: {data['status']}\nDuration: {data['duration']}\nRows: {data['rows']}\n\n-- Query --\n{data['query']}")

    def _get_selected_history_item(self, current_tab):
        selected_indexes = current_tab.findChild(
            QTreeView, "history_list_view").selectionModel().selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(
                self, "No Selection", "Please select a history item first.")
            return None
        return selected_indexes[0].model().itemFromIndex(selected_indexes[0]).data(Qt.ItemDataRole.UserRole)

    def copy_history_query(self, current_tab):
        history_data = self._get_selected_history_item(current_tab)
        if history_data:
            QApplication.clipboard().setText(history_data['query'])
            self.status_message_label.setText("Query copied to clipboard.")

    def copy_history_to_editor(self, current_tab):
        history_data = self._get_selected_history_item(current_tab)
        if history_data:
            current_tab.findChild(CodeEditor, "query_editor").setPlainText(
                history_data['query'])
            current_tab.findChild(
                QStackedWidget, "editor_stack").setCurrentIndex(0)
            query_view_btn = current_tab.findChild(QPushButton, "Query")
            history_view_btn = current_tab.findChild(
                QPushButton, "Query History")
            if query_view_btn:
                query_view_btn.setChecked(True)
            if history_view_btn:
                history_view_btn.setChecked(False)
            self.status_message_label.setText("Query copied to editor.")

    def remove_selected_history(self, current_tab):
        history_data = self._get_selected_history_item(current_tab)
        if not history_data:
            return
        if QMessageBox.question(self, "Remove History", "Are you sure you want to remove the selected query history?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                db.delete_history_item(history_data['id'])
                self.load_connection_history(current_tab)
                current_tab.findChild(QTextEdit, "history_details_view").clear()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to remove history item:\n{e}")

    def remove_all_history_for_connection(self, current_tab):
        conn_data = current_tab.findChild(
            QComboBox, "db_combo_box").currentData()
        if not conn_data:
            QMessageBox.warning(self, "No Connection",
                                "Please select a connection first.")
            return
        conn_name = current_tab.findChild(
            QComboBox, "db_combo_box").currentText()
        if QMessageBox.question(self, "Remove All History", f"Are you sure you want to remove all history for the connection:\n'{conn_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                db.delete_all_history_for_connection(conn_data.get("id"))
                self.load_connection_history(current_tab)
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to clear history for this connection:\n{e}")
                

    def load_sqlite_schema(self, conn_data):
        self.schema_model.clear()
        self.schema_model.setHorizontalHeaderLabels(["Name", "Type"])
        self.schema_tree.setColumnWidth(0, 200)
        self.schema_tree.setColumnWidth(1, 100)
        
        header = self.schema_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.schema_tree.setStyleSheet("""
    QHeaderView {
        background-color: #a9a9a9;
                                       
    }
    QHeaderView::section {
        border-right: 1px solid #d3d3d3;
        padding: 4px;
        background-color: #a9a9a9;   
    }
    QTreeView {
        gridline-color: #a9a9a9;
    }
""")

        db_path = conn_data.get("db_path")
        if not db_path or not os.path.exists(db_path):
            self.status.showMessage(
                f"Error: SQLite DB path not found: {db_path}", 5000)
            return
        try:
            conn = sqlite.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name;")
            for name, type_str in cursor.fetchall():
                icon = QIcon(
                    "assets/table_icon.png") if type_str == 'table' else QIcon("assets/view_icon.png")
                name_item = QStandardItem(icon, name)
                name_item.setEditable(False)
                name_item.setData(
                    {'db_type': 'sqlite', 'conn_data': conn_data}, Qt.ItemDataRole.UserRole)
                type_item = QStandardItem(type_str.capitalize())
                type_item.setEditable(False)
                self.schema_model.appendRow([name_item, type_item])
            conn.close()
            if hasattr(self, '_expanded_connection'):
                try:
                    self.schema_tree.expanded.disconnect(
                        self._expanded_connection)
                except TypeError:
                    pass
        except Exception as e:
            self.status.showMessage(f"Error loading SQLite schema: {e}", 5000)

    def load_postgres_schema(self, conn_data):
        try:
            
            self.schema_model.clear()
            self.schema_model.setHorizontalHeaderLabels(["Name", "Type"])
            self.pg_conn = psycopg2.connect(host=conn_data["host"], database=conn_data["database"],
                                            user=conn_data["user"], password=conn_data["password"], port=int(conn_data["port"]))
            cursor = self.pg_conn.cursor()
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast') ORDER BY schema_name;")
            for (schema_name,) in cursor.fetchall():
                schema_item = QStandardItem(
                    QIcon("assets/schema_icon.png"), schema_name)
                schema_item.setEditable(False)
                schema_item.setData({'db_type': 'postgres', 'schema_name': schema_name,
                                    'conn_data': conn_data}, Qt.ItemDataRole.UserRole)
                schema_item.appendRow(QStandardItem("Loading..."))
                type_item = QStandardItem("Schema")
                type_item.setEditable(False)
                self.schema_model.appendRow([schema_item, type_item])
            if hasattr(self, '_expanded_connection'):
                try:
                    self.schema_tree.expanded.disconnect(
                        self._expanded_connection)
                except TypeError:
                    pass
            self._expanded_connection = self.schema_tree.expanded.connect(
                self.load_tables_on_expand)
        except Exception as e:
            self.status.showMessage(f"Error loading schemas: {e}", 5000)
            if hasattr(self, 'pg_conn') and self.pg_conn:
                self.pg_conn.close()
        self.schema_tree.setColumnWidth(0, 200)
        self.schema_tree.setColumnWidth(1, 100)
        header = self.schema_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.schema_tree.setStyleSheet("""
    QHeaderView {
        background-color: #a9a9a9;
                                       
    }
    QHeaderView::section {
        border-right: 1px solid #d3d3d3;
        padding: 4px;
        background-color: #a9a9a9;   
    }
    QTreeView {
        gridline-color: #a9a9a9;
    }
""")
    
    def show_schema_context_menu(self, position):
        index = self.schema_tree.indexAt(position)
        if not index.isValid():
            return
        item = self.schema_model.itemFromIndex(index)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if not (item_data and (item_data.get('db_type') == 'sqlite' or (item.parent() and item_data.get('db_type') == 'postgres'))):
            return
        table_name = item.text()
        menu = QMenu()
        view_menu = menu.addMenu("View/Edit Data")
        query_all_action = QAction("All Rows", self)
        query_all_action.triggered.connect(lambda: self.query_table_rows(
            item_data, table_name, limit=None, execute_now=True))
        view_menu.addAction(query_all_action)
        preview_100_action = QAction("First 100 Rows", self)
        preview_100_action.triggered.connect(lambda: self.query_table_rows(
            item_data, table_name, limit=100, execute_now=True))
        view_menu.addAction(preview_100_action)
        last_100_action = QAction("Last 100 Rows", self)
        last_100_action.triggered.connect(lambda: self.query_table_rows(
            item_data, table_name, limit=100, order='desc', execute_now=True))
        view_menu.addAction(last_100_action)
        count_rows_action = QAction("Count Rows", self)
        count_rows_action.triggered.connect(
            lambda: self.count_table_rows(item_data, table_name))
        view_menu.addAction(count_rows_action)
        menu.addSeparator()
        query_tool_action = QAction("Query Tool", self)
        query_tool_action.triggered.connect(
            lambda: self.open_query_tool_for_table(item_data, table_name))
        menu.addAction(query_tool_action)
        menu.addSeparator()
        export_rows_action = QAction("Export Rows", self)
        export_rows_action.triggered.connect(
            lambda: self.export_schema_table_rows(item_data, table_name))
        menu.addAction(export_rows_action)
        properties_action = QAction("Properties", self)
        properties_action.triggered.connect(
            lambda: self.show_table_properties(item_data, table_name))
        menu.addAction(properties_action)
        menu.exec(self.schema_tree.viewport().mapToGlobal(position))

    def show_table_properties(self, item_data, table_name):
        dialog = TablePropertiesDialog(item_data, table_name, self)
        dialog.exec()

    def export_schema_table_rows(self, item_data, table_name):
        if not item_data:
            return
        dialog = ExportDialog(
            self, f"{table_name}_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        options = dialog.get_options()
        if not options['filename']:
            QMessageBox.warning(self, "No Filename",
                                "Export cancelled. No filename specified.")
            return
            
        process_id = str(uuid.uuid4())
        conn_data = item_data['conn_data']
        object_name = f"{item_data.get('schema_name', 'public')}.{table_name}"
        initial_data = {"pid": process_id[:8], "type": "Export Data", "status": "Running", "server": conn_data['name'], "object": object_name, "time_taken": "...",
                        "start_time": datetime.datetime.now().strftime("%Y-%m-%d, %I:%M:%S %p"), "details": f"Exporting to {os.path.basename(options['filename'])}"}
        signals = ProcessSignals()
        signals.started.connect(self.handle_process_started)
        signals.finished.connect(self.handle_process_finished)
        signals.error.connect(self.handle_process_error)
        signals.started.emit(process_id, initial_data)
        self.thread_pool.start(RunnableExport(
            process_id, item_data, table_name, options, signals))

    def switch_to_processes_view(self):
        current_tab = self.tab_widget.currentWidget()
        if not current_tab:
            return

        results_stack = current_tab.findChild(QStackedWidget, "results_stacked_widget")
        header = current_tab.findChild(QWidget, "resultsHeader")
        buttons = header.findChildren(QPushButton)
        
        if results_stack and len(buttons) >= 4:
            results_stack.setCurrentIndex(3)
            buttons[0].setChecked(False)
            buttons[1].setChecked(False)
            buttons[2].setChecked(False)
            buttons[3].setChecked(True)

    def handle_process_started(self, process_id, data):
        self.switch_to_processes_view()
        row_items = []
        for key in ["pid", "type", "status", "server", "object", "time_taken", "start_time", "details"]:
            item = QStandardItem(data[key])
            if key == "pid":
                item.setData(process_id, Qt.ItemDataRole.UserRole)
            if key == "status":
                item.setIcon(QIcon("assets/running_icon.png"))
            row_items.append(item)
        self.processes_model.appendRow(row_items)

    def find_process_row(self, process_id):
        for row in range(self.processes_model.rowCount()):
            if self.processes_model.item(row, 0).data(Qt.ItemDataRole.UserRole) == process_id:
                return row
        return -1

    def handle_process_finished(self, process_id, message, time_taken):
        row = self.find_process_row(process_id)
        if row == -1:
            return
        status_item = QStandardItem("Finished")
        status_item.setBackground(QBrush(QColor("#d4edda")))
        status_item.setIcon(QIcon("assets/finished_icon.png"))
        self.processes_model.setItem(row, 2, status_item)
        self.processes_model.item(row, 5).setText(f"{time_taken:.2f}")
        self.processes_model.item(row, 7).setText(message)

    def handle_process_error(self, process_id, error_message):
        row = self.find_process_row(process_id)
        if row == -1:
            return
        status_item = QStandardItem("Error")
        status_item.setBackground(QBrush(QColor("#f8d7da")))
        status_item.setIcon(QIcon("assets/error_icon.png"))
        self.processes_model.setItem(row, 2, status_item)
        self.processes_model.item(row, 7).setText(error_message)

    def count_table_rows(self, item_data, table_name):
        if not item_data:
            return
        conn_data = item_data.get('conn_data')
        query = f'SELECT COUNT(*) FROM "{item_data.get("schema_name")}"."{table_name}";' if item_data.get(
            'db_type') == 'postgres' else f'SELECT COUNT(*) FROM "{table_name}";'
        self.status_message_label.setText(f"Counting rows for {table_name}...")
        signals = QuerySignals()
        runnable = RunnableQuery(conn_data, query, signals)
        signals.finished.connect(self.handle_count_result)
        signals.error.connect(self.handle_count_error)
        self.thread_pool.start(runnable)

    def handle_count_result(self, conn_data, query, results, columns, row_count, elapsed_time, is_select_query):
        try:
            if results and len(results[0]) > 0:
                self.notification_manager.show_message(
                    f"Table rows counted: {results[0][0]}")
                self.status_message_label.setText(
                    f"Successfully counted rows in {elapsed_time:.2f} sec.")
            else:
                self.handle_count_error("Could not retrieve count.")
        except Exception as e:
            self.handle_count_error(str(e))

    def handle_count_error(self, error_message):
        self.notification_manager.show_message(
            f"Error: {error_message}", is_error=True)
        self.status_message_label.setText("Failed to count rows.")

    # <<< MODIFIED FUNCTION START >>>
    def open_query_tool_for_table(self, item_data, table_name):
        if not item_data:
            return
        
        conn_data = item_data.get('conn_data')
        
        # Create a new blank tab
        new_tab = self.add_tab()
        
        # Find the database connection dropdown in the new tab
        db_combo_box = new_tab.findChild(QComboBox, "db_combo_box")
        
        # Find and set the correct connection in the dropdown
        for i in range(db_combo_box.count()):
            if db_combo_box.itemData(i) and db_combo_box.itemData(i).get('id') == conn_data.get('id'):
                db_combo_box.setCurrentIndex(i)
                break
        
        # Switch focus to the new tab
        self.tab_widget.setCurrentWidget(new_tab)
    # <<< MODIFIED FUNCTION END >>>

    def query_table_rows(self, item_data, table_name, limit=None, execute_now=True, order=None):
        if not item_data:
            return
        conn_data = item_data.get('conn_data')
        new_tab = self.add_tab()
        db_combo_box = new_tab.findChild(QComboBox, "db_combo_box")
        for i in range(db_combo_box.count()):
            if db_combo_box.itemData(i) and db_combo_box.itemData(i).get('id') == conn_data.get('id'):
                db_combo_box.setCurrentIndex(i)
                break
        query = f'SELECT * FROM "{item_data.get("schema_name")}"."{table_name}"' if item_data.get(
            'db_type') == 'postgres' else f'SELECT * FROM "{table_name}"'
        if order:
            if item_data.get('db_type') == 'postgres':
                query += f" ORDER BY 1 {order.upper()}"
            else:
                query += f" ORDER BY 1 {order.upper()}"

        if limit:
            query += f" LIMIT {limit}"

        new_tab.findChild(CodeEditor, "query_editor").setPlainText(query)

        if execute_now:
            self.tab_widget.setCurrentWidget(new_tab)
            self.execute_query()

    def load_tables_on_expand(self, index: QModelIndex):
        item = self.schema_model.itemFromIndex(index)
        if not item or (item.rowCount() > 0 and item.child(0).text() != "Loading..."):
            return
        item.removeRows(0, item.rowCount())
        item_data = item.data(Qt.ItemDataRole.UserRole)
        schema_name = item_data.get('schema_name')
        try:
            cursor = self.pg_conn.cursor()
            cursor.execute(
                "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_type, table_name;", (schema_name,))
            for (table_name, table_type) in cursor.fetchall():
                icon_path = "assets/table_icon.png" if "TABLE" in table_type else "assets/view_icon.png"
                display_type = "Table" if "TABLE" in table_type else "View"
                table_item = QStandardItem(QIcon(icon_path), table_name)
                table_item.setEditable(False)
                table_item.setData(item_data, Qt.ItemDataRole.UserRole)
                type_item = QStandardItem(display_type)
                type_item.setEditable(False)
                item.appendRow([table_item, type_item])
        except Exception as e:
            self.status.showMessage(f"Error expanding schema: {e}", 5000)
