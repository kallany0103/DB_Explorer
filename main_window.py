# main_window.py

import sys
import os
import time
import datetime
import psycopg2
import sqlite3 as sqlite # This can be removed if not used elsewhere directly
from functools import partial
import uuid
import pandas as pd, time, os
from table_properties import TablePropertiesDialog
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QTabWidget,
    QSplitter, QLineEdit, QTextEdit, QComboBox, QTableView, QHeaderView, QVBoxLayout, QWidget, QStatusBar, QToolBar, QFileDialog,
    QSizePolicy, QPushButton, QInputDialog, QMessageBox, QMenu, QAbstractItemView, QDialog, QFormLayout, QHBoxLayout,
    QStackedWidget, QLabel, QGroupBox,QCheckBox,QStyle,QDialogButtonBox, QPlainTextEdit, QButtonGroup
)
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtGui import QAction, QIcon, QStandardItemModel, QStandardItem, QFont, QMovie, QDesktopServices, QColor, QBrush
from PyQt6.QtCore import Qt, QDir, QModelIndex, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QTimer, QUrl
from dialogs.postgres_dialog import PostgresConnectionDialog
from dialogs.sqlite_dialog import SQLiteConnectionDialog
import db
from code_editor import CodeEditor


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
           "format": self.format_combo.currentText(),   # <<< ADD THIS
           "encoding": self.encoding_combo.currentText(),
           "header": self.header_check.isChecked(),
           "delimiter": delimiter,
           "quote": self.quote_edit.text()
       }



# --- Signals class for QRunnable worker ---
# class QuerySignals(QObject):
#     finished = pyqtSignal(dict, str, list, list, int, float, bool)
#     error = pyqtSignal(str)



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
            error_msg = f"An error occurred during export: {e}"
            print(error_msg)   # ✅ Print to console for debugging
            import traceback
            traceback.print_exc()   # ✅ Show full error stack
            self.signals.error.emit(self.process_id, error_msg)

        finally:
            if conn:
                conn.close()



# class RunnableExport(QRunnable):
#     def _init_(self, process_id, item_data, table_name, export_options, signals):
#         super()._init_()
#         self.process_id = process_id
#         self.item_data = item_data
#         self.table_name = table_name
#         self.export_options = export_options
#         self.signals = signals

#     def run(self):
#         start_time = time.time()
#         conn = None
#         try:
#             # Step 1: Database connection and query setup 
#             conn_data = self.item_data['conn_data']
#             db_type = self.item_data.get('db_type')
            
#             if db_type == 'sqlite':
#                 conn = db.create_sqlite_connection(conn_data["db_path"])
#                 query = f'SELECT * FROM "{self.table_name}"'
#             elif db_type == 'postgres':
#                 conn = db.create_postgres_connection(
#                     host=conn_data["host"], database=conn_data["database"], user=conn_data["user"], password=conn_data["password"], port=int(conn_data["port"]))
#                 schema_name = self.item_data.get("schema_name")
#                 query = f'SELECT * FROM "{schema_name}"."{self.table_name}"'
#             else:
#                 raise ValueError("Unsupported database type for export.")
            
#             if not conn:
#                 raise ConnectionError("Failed to connect to the database for export.")

#             # Step 2: Manually create DataFrame 
#             cursor = conn.cursor()
#             cursor.execute(query)
            
#             # get column name
#             headers = [desc[0] for desc in cursor.description]
            
#             # fetches all rows from the execute query result
#             data = cursor.fetchall()
            
#             # DataFrame 
#             df = pd.DataFrame(data, columns=headers)
            
            
#             file_path = self.export_options['filename']
#             file_format = self.export_options['format']
#             if file_format == 'xlsx':
#                 df.to_excel(file_path, index=False,
#                             header=self.export_options['header'])
#             else:
#                 df.to_csv(file_path, index=False, header=self.export_options['header'], sep=self.export_options[
#                           'delimiter'], encoding=self.export_options['encoding'], quotechar=self.export_options['quote'])
            
#             time_taken = time.time() - start_time
#             success_message = f"Successfully exported {len(df)} rows to {os.path.basename(file_path)}"
#             self.signals.finished.emit(
#                 self.process_id, success_message, time_taken)
                
#         except Exception as e:
#             error_msg = f"An error occurred during export: {e}"
#             print(error_msg)
#             import traceback
#             traceback.print_exc()
#             self.signals.error.emit(self.process_id, error_msg)

#         finally:
#             if conn:
#                 conn.close()


class RunnableExportFromModel(QRunnable):
    def __init__(self, process_id, model, export_options, signals):
        super().__init__()
        self.process_id = process_id
        self.model = model
        self.export_options = export_options
        self.signals = signals

    def run(self):
        start_time = time.time()
        try:
            rows, cols = self.model.rowCount(), self.model.columnCount()
            headers = [self.model.headerData(c, Qt.Orientation.Horizontal) for c in range(cols)]
            data = []
            for r in range(rows):
                row_data = []
                for c in range(cols):
                    index = self.model.index(r, c)
                    row_data.append(self.model.data(index))
                data.append(row_data)
            df = pd.DataFrame(data, columns=headers)

            file_path = self.export_options['filename']
            file_format = os.path.splitext(file_path)[1].lower()

            if file_format == ".xlsx":
                df.to_excel(file_path, index=False, header=self.export_options['header'])
            else:
                df.to_csv(
                    file_path,
                    index=False,
                    header=self.export_options['header'],
                    sep=self.export_options['delimiter'],
                    encoding=self.export_options['encoding'],
                    quotechar=self.export_options['quote']
                )

            time_taken = time.time() - start_time
            msg = f"Exported {len(df)} rows to {os.path.basename(file_path)}"
            self.signals.finished.emit(self.process_id, msg, time_taken)
        except Exception as e:
            self.signals.error.emit(self.process_id, str(e))


class QuerySignals(QObject):
    finished = pyqtSignal(dict, str, list, list, int, float, bool)  
    # conn_data, query, results, columns, row_count, elapsed_time, is_select_query

    error = pyqtSignal(dict, str, int, float, str)  
    # conn_data, query, row_count, elapsed_time, error_message



# --- Worker now inherits from QRunnable for use with QThreadPool ---
class RunnableQuery(QRunnable):
    def __init__(self, conn_data, query, signals):
        super().__init__()
        self.conn_data = conn_data
        self.query = query
        self.signals = signals
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        conn = None
        try:
            start_time = time.time()
            if not self.conn_data:
                raise ConnectionError("Incomplete connection information.")

            if "db_path" in self.conn_data and self.conn_data["db_path"]:
                conn = db.create_sqlite_connection(self.conn_data["db_path"])
            else:
                conn = db.create_postgres_connection(
                    host=self.conn_data["host"], database=self.conn_data["database"],
                    user=self.conn_data["user"], password=self.conn_data["password"],
                    port=int(self.conn_data["port"])
                )
            
            if not conn:
                raise ConnectionError("Failed to establish database connection.")

            cursor = conn.cursor()
            cursor.execute(self.query)

            if self._is_cancelled:
                conn.close()
                return

            row_count = 0
            is_select_query = self.query.lower().strip().startswith("select")
            results = []
            columns = []

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
            # if not self._is_cancelled:
            #     self.signals.error.emit(str(e))
            if not self._is_cancelled:
                elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                self.signals.error.emit(self.conn_data, self.query, 0, elapsed_time, str(e) )
        finally:
            if conn:
                conn.close()



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


class MainWindow(QMainWindow):
    QUERY_TIMEOUT = 60000
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal SQL Client")
        self.setGeometry(100, 100, 1200, 800)

        self.thread_pool = QThreadPool.globalInstance()
        self.tab_timers = {}
        self.running_queries = {}
        self._initialize_processes_model() # <<< MODIFIED >>> Initialize shared model

        self._create_actions()
        self._create_menu()
        self._create_centered_toolbar()

        # main_splitter কে self attribute হিসেবে রাখা হলো
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
        # Connect the doubleClicked signal
        self.tree.doubleClicked.connect(self.item_double_clicked)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        
        # Disable editing
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Object Explorer'])
        self.tree.setModel(self.model)

        # vertical_splitter কে self attribute হিসেবে রাখা হলো
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

        self.left_vertical_splitter.setSizes([240, 360])
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
        self.thread_monitor_timer.timeout.connect(self.update_thread_pool_status)
        self.thread_monitor_timer.start(1000)

        self.load_data()
        self.add_tab()
        self.main_splitter.setSizes([280, 920])
        self.notification_manager = NotificationManager(self)
        self._apply_styles()

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

    # --- New Handler Methods for Menu Actions ---

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
         active = self.thread_pool.activeThreadCount()
         max_threads = self.thread_pool.maxThreadCount()
         self.status.showMessage(f"ThreadPool: {active} active of {max_threads}", 3000)

    

    def _apply_styles(self):
        primary_color, header_color, selection_color = "#D3D3D3", "#A9A9A9", "#A9A9A9"
        text_color_on_primary, alternate_row_color, border_color = "#000000", "#f0f0f0", "#A9A9A9"
        self.setStyleSheet(f"""QMainWindow, QToolBar, QStatusBar {{ background-color: {primary_color}; color: {text_color_on_primary}; }} QTreeView {{ background-color: white; alternate-background-color: {alternate_row_color}; border: 1px solid {border_color}; }} QTableView {{ alternate-background-color: {alternate_row_color}; background-color: white; gridline-color: #a9a9a9; border: 1px solid {border_color}; font-family: Arial, sans-serif; font-size: 9pt;}} QTableView::item {{ padding: 4px; }} QTableView::item:selected {{ background-color: {selection_color}; color: white; }} QHeaderView::section {{ background-color: {header_color}; color: white; padding: 4px; border: none; border-right: 1px solid #d3d3d3; border-bottom: 1px solid {border_color}; font-weight: bold; font-size: 9pt;  }} QTableView QTableCornerButton::section {{ background-color: {header_color}; border: 1px solid {border_color}; }} #resultsHeader QPushButton, #editorHeader QPushButton {{ background-color: #ffffff; border: 1px solid {border_color}; padding: 5px 15px; font-size: 9pt; }} #resultsHeader QPushButton:hover, #editorHeader QPushButton:hover {{ background-color: {primary_color}; }} #resultsHeader QPushButton:checked, #editorHeader QPushButton:checked {{ background-color: {selection_color}; border-bottom: 1px solid {selection_color}; font-weight: bold; color: white; }} #resultsHeader, #editorHeader {{ background-color: {alternate_row_color}; padding-bottom: -1px; }} #messageView, #history_details_view, QTextEdit {{ font-family: Consolas, monospace; font-size: 10pt; background-color: white; border: 1px solid {border_color}; }} #tab_status_label {{ padding: 3px 5px; background-color: {alternate_row_color}; border-top: 1px solid {border_color}; }} QGroupBox {{ font-size: 9pt; font-weight: bold; color: {text_color_on_primary}; }} QTabWidget::pane {{ border-top: 1px solid {border_color}; }} QTabBar::tab {{ background: #E0E0E0; border: 1px solid {border_color}; padding: 5px 10px; border-bottom: none; }} QTabBar::tab:selected {{ background: {selection_color}; color: white; }} QComboBox {{ border: 1px solid {border_color}; padding: 2px; background-color: white; }}""")
    

    
    def add_tab(self):
        tab_content = QWidget(self.tab_widget)
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

        # ----------------- Editor Container -----------------
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        editor_header = QWidget()
        editor_header.setObjectName("editorHeader")
        editor_header_layout = QHBoxLayout(editor_header)
        editor_header_layout.setContentsMargins(5, 2, 5, 0)
        editor_header_layout.setSpacing(2)

        query_view_btn = QPushButton("Query")
        history_view_btn = QPushButton("Query History")

        query_view_btn.setMinimumWidth(100)
        history_view_btn.setMinimumWidth(150)

        query_view_btn.setCheckable(True)
        history_view_btn.setCheckable(True)
        query_view_btn.setChecked(True)

        editor_header_layout.addWidget(query_view_btn)
        editor_header_layout.addWidget(history_view_btn)
        editor_header_layout.addStretch()
        editor_layout.addWidget(editor_header)

        # --- Editor toggle button group ---
        editor_button_group = QButtonGroup(self)
        editor_button_group.setExclusive(True)
        editor_button_group.addButton(query_view_btn, 0)
        editor_button_group.addButton(history_view_btn, 1)

        editor_stack = QStackedWidget()
        editor_stack.setObjectName("editor_stack")

        text_edit = CodeEditor()
        text_edit.setPlaceholderText("Write your SQL query here...")
        text_edit.setObjectName("query_editor")
        editor_stack.addWidget(text_edit)

        history_widget = QSplitter(Qt.Orientation.Horizontal)
        history_list_view = QTreeView()
        history_list_view.setObjectName("history_list_view")
        history_list_view.setHeaderHidden(True)
        history_list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        history_details_group = QGroupBox("Query Details")
        history_details_layout = QVBoxLayout(history_details_group)
        history_details_view = QTextEdit()
        history_details_view.setObjectName("history_details_view")
        history_details_view.setReadOnly(True)
        history_details_layout.addWidget(history_details_view)

        history_button_layout = QHBoxLayout()
        copy_history_btn = QPushButton("Copy")
        copy_to_edit_btn = QPushButton("Copy to Edit Query")
        remove_history_btn = QPushButton("Remove")
        remove_all_history_btn = QPushButton("Remove All")
    
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

        # --- Editor switching logic ---
        def switch_editor_view(index):
            editor_stack.setCurrentIndex(index)
            if index == 1:
              self.load_connection_history(tab_content)

        query_view_btn.clicked.connect(lambda: switch_editor_view(0))
        history_view_btn.clicked.connect(lambda: switch_editor_view(1))

        db_combo_box.currentIndexChanged.connect(
          lambda: editor_stack.currentIndex() == 1 and self.load_connection_history(tab_content)
        )
        history_list_view.clicked.connect(lambda index: self.display_history_details(index, tab_content))
    
        copy_history_btn.clicked.connect(lambda: self.copy_history_query(tab_content))
        copy_to_edit_btn.clicked.connect(lambda: self.copy_history_to_editor(tab_content))
        remove_history_btn.clicked.connect(lambda: self.remove_selected_history(tab_content))
        remove_all_history_btn.clicked.connect(lambda: self.remove_all_history_for_connection(tab_content))

        # ----------------- Results Container -----------------
        results_container = QWidget()
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 5, 0, 0)
        results_layout.setSpacing(0)

        results_header = QWidget()
        results_header.setObjectName("resultsHeader")
        header_layout = QHBoxLayout(results_header)
        header_layout.setContentsMargins(5, 2, 5, 0)
        header_layout.setSpacing(2)

        output_btn = QPushButton("Output")
        message_btn = QPushButton("Messages")
        notification_btn = QPushButton("Notifications")
        process_btn = QPushButton("Processes")

        output_btn.setMinimumWidth(100)
        message_btn.setMinimumWidth(100)
        notification_btn.setMinimumWidth(130)
        process_btn.setMinimumWidth(100)

        for btn in [output_btn, message_btn, notification_btn, process_btn]:
            btn.setCheckable(True)

        output_btn.setChecked(True)

        header_layout.addWidget(output_btn)
        header_layout.addWidget(message_btn)
        header_layout.addWidget(notification_btn)
        header_layout.addWidget(process_btn)
        header_layout.addStretch()
        results_layout.addWidget(results_header)

        # --- Results toggle button group ---
        results_button_group = QButtonGroup(self)
        results_button_group.setExclusive(True)
        results_button_group.addButton(output_btn, 0)
        results_button_group.addButton(message_btn, 1)
        results_button_group.addButton(notification_btn, 2)
        results_button_group.addButton(process_btn, 3)

        results_stack = QStackedWidget()
        results_stack.setObjectName("results_stacked_widget")

        table_view = QTableView()
        table_view.setObjectName("result_table")
        table_view.setAlternatingRowColors(True)
        table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table_view.customContextMenuRequested.connect(self.show_results_context_menu)
        results_stack.addWidget(table_view)

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
        processes_view.setColumnWidth(3, 220)
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
            loading_text_label = QLabel("Waiting for query to complete...")

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

        # --- Results switching logic ---
        def switch_results_view(index):
           results_stack.setCurrentIndex(index)


        output_btn.clicked.connect(lambda: switch_results_view(0))
        message_btn.clicked.connect(lambda: switch_results_view(1))
        notification_btn.clicked.connect(lambda: switch_results_view(2))
        process_btn.clicked.connect(lambda: switch_results_view(3))

        main_vertical_splitter.addWidget(results_container)
        main_vertical_splitter.setSizes([300, 300])

        tab_content.setLayout(layout)
        index = self.tab_widget.addTab(
            tab_content, f"Worksheet {self.tab_widget.count() + 1}"
        )
        self.tab_widget.setCurrentIndex(index)
        self.renumber_tabs()
        return tab_content



    def close_tab(self, index):
        tab = self.tab_widget.widget(index)
        if tab in self.running_queries:
            self.running_queries[tab].cancel()
            del self.running_queries[tab]
            if not self.running_queries:
                self.cancel_action.setEnabled(False)
        if tab in self.tab_timers:
            self.tab_timers[tab]["timer"].stop()
            if "timeout_timer" in self.tab_timers[tab]:
                self.tab_timers[tab]["timeout_timer"].stop()
            del self.tab_timers[tab]
        if self.tab_widget.count() > 1:
            self.tab_widget.removeTab(index)
            self.renumber_tabs()
        else:
            self.status.showMessage("Must keep at least one tab", 3000)

    def renumber_tabs(self):
        for i in range(self.tab_widget.count()):
            self.tab_widget.setTabText(i, f"Worksheet {i + 1}")

    def load_data(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Object Explorer"])
        hierarchical_data = db.get_hierarchy_data()
        for cat_data in hierarchical_data:
            cat_item = QStandardItem(cat_data['name'])
            cat_item.setData(cat_data['id'], Qt.ItemDataRole.UserRole + 1)
            for subcat_data in cat_data['subcategories']:
                subcat_item = QStandardItem(subcat_data['name'])
                subcat_item.setData(subcat_data['id'], Qt.ItemDataRole.UserRole + 1)
                for item_data in subcat_data['items']:
                    item_item = QStandardItem(item_data['name'])
                    item_item.setData(item_data, Qt.ItemDataRole.UserRole)
                    subcat_item.appendRow(item_item)
                cat_item.appendRow(subcat_item)
            self.model.appendRow(cat_item)

    # def item_clicked(self, index):
    #     item = self.model.itemFromIndex(index)
    #     depth = self.get_item_depth(item)
    #     self.schema_model.clear()
    #     self.schema_model.setHorizontalHeaderLabels(["Database Schema"])
    #     if depth == 3:
    #         conn_data = item.data(Qt.ItemDataRole.UserRole)
    #         if conn_data:
    #             if conn_data.get("host"):
    #                 self.status.showMessage(f"Loading schema for {conn_data.get('name')}...", 3000)
    #                 self.load_postgres_schema(conn_data)
    #             elif conn_data.get("db_path"):
    #                 self.status.showMessage(f"Loading schema for {conn_data.get('name')}...", 3000)
    #                 self.load_sqlite_schema(conn_data)


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


    def item_double_clicked(self, index: QModelIndex):
        #item_text = index.data(Qt.ItemDataRole.DisplayRole)
        item = self.model.itemFromIndex(index)
        depth = self.get_item_depth(item)
        
        if depth == 3:
            print(f"Double-clicked on: {item.text()}")
            # Place your custom logic here

    def get_item_depth(self, item):
        depth = 0
        parent = item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        return depth + 1

    def show_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid(): return
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
                    add_pg_action = QAction("Add New PostgreSQL Connection", self)
                    add_pg_action.triggered.connect(lambda: self.add_postgres_connection(item))
                    menu.addAction(add_pg_action)
                elif "sqlite" in category_name.lower():
                    add_sqlite_action = QAction("Add New SQLite Connection", self)
                    add_sqlite_action.triggered.connect(lambda: self.add_sqlite_connection(item))
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
                    edit_action.triggered.connect(lambda: self.edit_pg_item(item))
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
              f"<b>Short Name:</b> {conn_data.get('short_name', 'N/A')}<br>"
              f"<b>Type:</b> PostgreSQL<br>"
              f"<b>Host:</b> {conn_data.get('host', 'N/A')}<br>"
              f"<b>Port:</b> {conn_data.get('port', 'N/A')}<br>"
              f"<b>Database:</b> {conn_data.get('database', 'N/A')}<br>"
              f"<b>User:</b> {conn_data.get('user', 'N/A')}"
          )
      elif conn_data.get("db_path"):
          details_text = (
              f"<b>Name:</b> {conn_data.get('name', 'N/A')}<br>"
              f"<b>Short Name:</b> {conn_data.get('short_name', 'N/A')}<br>"
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
            parent_id = parent_item.data(Qt.ItemDataRole.UserRole+1)
            db.add_subcategory(name, parent_id)
            self.load_data()

    def add_postgres_connection(self, parent_item):
        subcat_id = parent_item.data(Qt.ItemDataRole.UserRole + 1)
        dialog = PostgresConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                db.add_item(data, subcat_id)
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save PostgreSQL connection:\n{e}")

    def add_sqlite_connection(self, parent_item):
        subcat_id = parent_item.data(Qt.ItemDataRole.UserRole + 1)
        dialog = SQLiteConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                db.add_item(data, subcat_id)
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save SQLite connection:\n{e}")

    def edit_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        if conn_data and conn_data.get("db_path"):
            dialog = SQLiteConnectionDialog(self, conn_data=conn_data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_data()
                try:
                    db.update_item(new_data)
                    self.load_data()
                    self.refresh_all_comboboxes()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to update SQLite connection:\n{e}")

    def edit_pg_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        if not conn_data: return
        dialog = PostgresConnectionDialog(self, is_editing=True)
        dialog.name_input.setText(conn_data.get("name", ""))
        dialog.short_name_input.setText(conn_data.get("short_name", ""))
        dialog.host_input.setText(conn_data.get("host", ""))
        dialog.port_input.setText(str(conn_data.get("port", "")))
        dialog.db_input.setText(conn_data.get("database", ""))
        dialog.user_input.setText(conn_data.get("user", ""))
        dialog.password_input.setText(conn_data.get("password", ""))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            new_data["id"] = conn_data.get("id") # Make sure to pass the ID for update
            try:
                db.update_item(new_data)
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update PostgreSQL connection:\n{e}")

    def delete_item(self, item):
        conn_data = item.data(Qt.ItemDataRole.UserRole)
        item_id = conn_data.get("id")
        reply = QMessageBox.question(self, "Delete Connection", "Are you sure you want to delete this connection?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db.delete_item(item_id)
                self.load_data()
                self.refresh_all_comboboxes()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete item:\n{e}")

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
            all_items = db.get_all_connections_from_db()
            for item in all_items:
                # The data for the combobox is now the full connection dictionary
                conn_data = {key: item[key] for key in item if key != 'display_name'}
                combo_box.addItem(item["display_name"], conn_data)

            if current_data:
                for i in range(combo_box.count()):
                    if combo_box.itemData(i) and combo_box.itemData(i)['id'] == current_data['id']:
                        combo_box.setCurrentIndex(i)
                        break
        except Exception as e:
            self.status.showMessage(f"Error loading connections: {e}", 4000)

    def show_info(self, message: str):
       QMessageBox.information(self, "Info", message)

    def execute_query(self):
      current_tab = self.tab_widget.currentWidget()
      if not current_tab:
        return

      # Get query editor and DB info
      query_editor = current_tab.findChild(QPlainTextEdit, "query_editor")
      db_combo_box = current_tab.findChild(QComboBox, "db_combo_box")
      index = db_combo_box.currentIndex()
      conn_data = db_combo_box.itemData(index)

      # Extract query under cursor
      cursor = query_editor.textCursor()
      cursor_pos = cursor.position()
      full_text = query_editor.toPlainText()
      queries = full_text.split(";")

      selected_query = ""
      start = 0
      for q in queries:
          end = start + len(q)
          if start <= cursor_pos <= end:
              selected_query = q.strip()
              break
          start = end + 1  # for semicolon

      print("Selected query:", selected_query)

      if not selected_query or not selected_query.upper().startswith("SELECT "):
          self.show_info("Please enter a valid SELECT query.")
          return
      
      # Show results stack page with spinner
      results_stack = current_tab.findChild(QStackedWidget, "results_stacked_widget")
      spinner_label = results_stack.findChild(QLabel, "spinner_label")
      results_stack.setCurrentIndex(4)
      if spinner_label and spinner_label.movie():
            spinner_label.movie().start()
            spinner_label.show()
      # Set up timers for elapsed time display
      tab_status_label = current_tab.findChild(QLabel, "tab_status_label")
      progress_timer = QTimer(self)
      start_time = time.time()
      timeout_timer = QTimer(self)
      timeout_timer.setSingleShot(True)
      self.tab_timers[current_tab] = {
          "timer": progress_timer,
          "start_time": start_time,
          "timeout_timer": timeout_timer
      }
      progress_timer.timeout.connect(partial(self.update_timer_label, tab_status_label, current_tab))
      progress_timer.start(100)

      # Run query asynchronously
      signals = QuerySignals()
      runnable = RunnableQuery(conn_data, selected_query, signals)
      signals.finished.connect(partial(self.handle_query_result, current_tab))
      signals.error.connect(partial(self.handle_query_error, current_tab))
      timeout_timer.timeout.connect(partial(self.handle_query_timeout, current_tab, runnable))
      self.running_queries[current_tab] = runnable
      self.cancel_action.setEnabled(True)
      self.thread_pool.start(runnable)
      timeout_timer.start(self.QUERY_TIMEOUT)

      self.status_message_label.setText("Executing query...")


    def update_timer_label(self, label, tab):
        if not label or tab not in self.tab_timers: return
        elapsed = time.time() - self.tab_timers[tab]["start_time"]
        label.setText(f"Running... {elapsed:.1f} sec")

    # def handle_query_result(self, target_tab, conn_data, query, results, columns, row_count, elapsed_time, is_select_query):
    #   # Stop timers
    #   if target_tab in self.tab_timers:
    #      self.tab_timers[target_tab]["timer"].stop()
    #      self.tab_timers[target_tab]["timeout_timer"].stop()
    #      del self.tab_timers[target_tab]

    #   self.save_query_to_history(
    #         conn_data, query, "Success", row_count, elapsed_time)

    #   # Update table and message view
    #   table_view = target_tab.findChild(QTableView, "result_table")
    #   message_view = target_tab.findChild(QTextEdit, "message_view")
    #   tab_status_label = target_tab.findChild(QLabel, "tab_status_label")

    #   if is_select_query:
    #       model = QStandardItemModel()
    #       model.setHorizontalHeaderLabels(columns)
    #       for row in results:
    #           model.appendRow([QStandardItem(str(cell)) for cell in row])
    #       table_view.setModel(model)
    #       msg = f"Query executed successfully.\n\nTotal rows: {row_count}\nTime: {elapsed_time:.2f} sec"
    #       status = f"Query executed successfully | Total rows: {row_count} | Time: {elapsed_time:.2f} sec"
    #   else:
    #       table_view.setModel(QStandardItemModel())
    #       msg = f"Command executed successfully.\n\nRows affected: {row_count}\nTime: {elapsed_time:.2f} sec"
    #       status = f"Command executed successfully | Rows affected: {row_count} | Time: {elapsed_time:.2f} sec"

    # #   if message_view:
    # #       message_view.setText(msg)

    #   if message_view:
    #     # Append new message with a separator
    #     # message_view.toPlainText() gets the current text.
    #     # append() adds new text at the end instead of replacing it.
    #     # "-"*50 adds a visual separator between queries (optional but useful).
    #     previous_text = message_view.toPlainText()
    #     if previous_text:
    #        message_view.append("\n" + "-"*50 + "\n")  # Optional separator
    #     message_view.append(msg)

    #   if tab_status_label:
    #       tab_status_label.setText(status)

    #   self.status_message_label.setText("Ready")

    #   # Stop spinner
    #   spinner_label = target_tab.findChild(QLabel, "spinner_label")
    #   if spinner_label and spinner_label.movie():
    #       spinner_label.movie().stop()
    #       spinner_label.hide()


    #   # Show output results view (index 0)
    #   results_stack = target_tab.findChild(QStackedWidget, "results_stacked_widget")
    #   if results_stack:
    #      results_stack.setCurrentIndex(0)

    #   # Cleanup running queries
    #   if target_tab in self.running_queries:
    #       del self.running_queries[target_tab]
    #   if not self.running_queries:
    #       self.cancel_action.setEnabled(False)


    def handle_query_result(self, target_tab, conn_data, query, results, columns, row_count, elapsed_time, is_select_query):
      # Stop timers
      if target_tab in self.tab_timers:
        self.tab_timers[target_tab]["timer"].stop()
        self.tab_timers[target_tab]["timeout_timer"].stop()
        del self.tab_timers[target_tab]

      self.save_query_to_history(
        conn_data, query, "Success", row_count, elapsed_time
     )

      # Get widgets
      table_view = target_tab.findChild(QTableView, "result_table")
      message_view = target_tab.findChild(QTextEdit, "message_view")
      tab_status_label = target_tab.findChild(QLabel, "tab_status_label")

      if is_select_query:
        model = QStandardItemModel()
        model.setColumnCount(len(columns))
        model.setRowCount(len(results))

        # --- Try to detect table name and get metadata ---
        import re
        match = re.search(r"FROM\s+([\w\.]+)", query, re.IGNORECASE)
        meta_columns = None
        if match:
            table_name = match.group(1).split('.')[-1]  # handle schema.table
            meta_columns = self.get_table_column_metadata(conn_data, table_name)  # may return str or tuple/list

        # Process meta_columns safely
        headers = []
        if meta_columns and len(meta_columns) == len(columns):
            for col in meta_columns:
                if isinstance(col, str):
                    parts = col.split(maxsplit=1)  # "id integer" -> ["id", "integer"]
                    col_name = parts[0]
                    data_type = parts[1] if len(parts) > 1 else ""
                elif isinstance(col, (list, tuple)):
                    col_name = col[0]
                    data_type = col[1] if len(col) > 1 else ""
                else:
                    col_name = str(col)
                    data_type = ""
                headers.append(f"{col_name}\n{data_type}")  # line break in header
        else:
            # fallback: just use column names
            headers = [f"{col}\n" for col in columns]

        # Set horizontal headers
        for col_idx, header_text in enumerate(headers):
            model.setHeaderData(col_idx, Qt.Orientation.Horizontal, header_text)

        # Center-align headers
        header = table_view.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        # Fill table data
        for row_idx, row in enumerate(results):
            for col_idx, cell in enumerate(row):
                model.setItem(row_idx, col_idx, QStandardItem(str(cell)))

        table_view.setModel(model)

        msg = f"Query executed successfully.\n\nTotal rows: {row_count}\nTime: {elapsed_time:.2f} sec"
        status = f"Query executed successfully | Total rows: {row_count} | Time: {elapsed_time:.2f} sec"

      else:
        # Non-SELECT queries
        table_view.setModel(QStandardItemModel())
        msg = f"Command executed successfully.\n\nRows affected: {row_count}\nTime: {elapsed_time:.2f} sec"
        status = f"Command executed successfully | Rows affected: {row_count} | Time: {elapsed_time:.2f} sec"

      # Update message view
      if message_view:
        previous_text = message_view.toPlainText()
        if previous_text:
            message_view.append("\n" + "-"*50 + "\n")  # separator
        message_view.append(msg)

      # Update tab status
      if tab_status_label:
        tab_status_label.setText(status)

      self.status_message_label.setText("Ready")

      # Stop spinner
      spinner_label = target_tab.findChild(QLabel, "spinner_label")
      if spinner_label and spinner_label.movie():
        spinner_label.movie().stop()
        spinner_label.hide()

      # Show output results view
      results_stack = target_tab.findChild(QStackedWidget, "results_stacked_widget")
      if results_stack:
        results_stack.setCurrentIndex(0)

      # Cleanup running queries
      if target_tab in self.running_queries:
        del self.running_queries[target_tab]
      if not self.running_queries:
        self.cancel_action.setEnabled(False)



    def get_table_column_metadata(self, conn_data, table_name):
      """
        Returns a list of column headers with pgAdmin-style info like:
        emp_id [PK] integer, emp_name character varying(100)
        Uses create_postgres_connection() for consistent DB connection handling.
      """
      headers = []
      conn = None
      try:
        # ✅ Use your reusable connection function
        conn = db.create_postgres_connection(
            host=conn_data["host"],
            port=conn_data["port"],
            database=conn_data["database"],
            user=conn_data["user"],
            password=conn_data["password"]
        )
        if not conn:
            print("Failed to establish connection for metadata fetch.")
            return []

        cur = conn.cursor()
        cur.execute("""
            SELECT
                a.attname AS column_name,
                format_type(a.atttypid, a.atttypmod) AS data_type,
                CASE WHEN ct.contype = 'p' THEN '[PK]'
                     WHEN ct.contype = 'f' THEN '[FK]'
                     ELSE ''
                END AS constraint_type
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_constraint ct 
              ON ct.conrelid = c.oid 
             AND a.attnum = ANY(ct.conkey)
            WHERE c.relname = %s 
              AND a.attnum > 0 
              AND NOT a.attisdropped
            ORDER BY a.attnum;
        """, (table_name,))
        rows = cur.fetchall()
        for col, dtype, constraint in rows:
            headers.append(f"{col} {constraint} {dtype}".strip())
      except Exception as e:
        print(f"Metadata fetch error for table '{table_name}': {e}")
      finally:
        if conn:
            conn.close()
      return headers

    

    # def handle_query_error(self, target_tab, error_message):
    #     if target_tab in self.tab_timers:
    #         self.tab_timers[target_tab]["timer"].stop()
    #         self.tab_timers[target_tab]["timeout_timer"].stop()
    #         del self.tab_timers[target_tab]
    #     message_view = target_tab.findChild(QTextEdit, "message_view")
    #     tab_status_label = target_tab.findChild(QLabel, "tab_status_label")
    #     error_text = f"Error: {error_message}"
    #     message_view.setText(f"Error:\n\n{error_message}")
    #     tab_status_label.setText(error_text)
    #     self.status_message_label.setText("Error occurred")
    #     self.stop_spinner(target_tab, success=False)
    #     if target_tab in self.running_queries:
    #         del self.running_queries[target_tab]
    #     if not self.running_queries:
    #         self.cancel_action.setEnabled(False)

    def show_error_popup(self, error_text, parent=None):
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle("Query Error")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("Query execution failed")
        msg_box.setInformativeText(error_text)  # detailed error
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()


    def handle_query_error(self, current_tab, conn_data, query, row_count, elapsed_time, error_message):
        if current_tab in self.tab_timers:
            self.tab_timers[current_tab]["timer"].stop()
            self.tab_timers[current_tab]["timeout_timer"].stop()
            del self.tab_timers[current_tab]

        self.save_query_to_history(
            conn_data, query, "Failure", row_count, elapsed_time)
        
        message_view = current_tab.findChild(QTextEdit, "message_view")
        tab_status_label = current_tab.findChild(QLabel, "tab_status_label")

        #message_view.setText(f"Error:\n\n{error_message}")
        if message_view:
            previous_text = message_view.toPlainText()
            if previous_text:
              message_view.append("\n" + "-"*50 + "\n")  # Optional separator
            message_view.append(f"Error:\n\n{error_message}")
            message_view.verticalScrollBar().setValue(message_view.verticalScrollBar().maximum())


        #tab_status_label.setText(f"Error: {error_message}")
        self.status_message_label.setText("Error occurred")
        self.stop_spinner(current_tab, success=False)

        # --- Show popup ---
        self.show_error_popup(error_message, parent=current_tab)

        if current_tab in self.running_queries:
            del self.running_queries[current_tab]
        if not self.running_queries:
            self.cancel_action.setEnabled(False)


    def stop_spinner(self, target_tab, success=True):
        if not target_tab: return
        stacked_widget = target_tab.findChild(QStackedWidget, "results_stacked_widget")
        if stacked_widget:
            spinner_label = stacked_widget.findChild(QLabel, "spinner_label")
            if spinner_label and spinner_label.movie():
                spinner_label.movie().stop()
            header = target_tab.findChild(QWidget, "resultsHeader")
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
    


    def handle_query_timeout(self, tab, runnable):
        if self.running_queries.get(tab) is runnable:
            runnable.cancel()
            error_message = f"Error: Query Timed Out after {self.QUERY_TIMEOUT / 1000} seconds."
            tab.findChild(QTextEdit, "message_view").setText(error_message)
            tab.findChild(QLabel, "tab_status_label").setText(error_message)
            self.stop_spinner(tab, success=False)
            if tab in self.tab_timers:
                self.tab_timers[tab]["timer"].stop()
                del self.tab_timers[tab]
            if tab in self.running_queries:
                del self.running_queries[tab]
            if not self.running_queries:
                self.cancel_action.setEnabled(False)
            self.status_message_label.setText("Error occurred")
            QMessageBox.warning(self, "Query Timeout", f"The query was stopped as it exceeded {self.QUERY_TIMEOUT / 1000}s.")

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
            current_tab.findChild(QTextEdit, "message_view").setText(cancel_message)
            current_tab.findChild(QLabel, "tab_status_label").setText(cancel_message)
            self.stop_spinner(current_tab, success=False)
            self.status_message_label.setText("Query Cancelled")
            if current_tab in self.running_queries:
                del self.running_queries[current_tab]
            if not self.running_queries:
                self.cancel_action.setEnabled(False)


    def save_query_to_history(self, conn_data, query, status, rows, duration):
        conn_id = conn_data.get("id")
        if not conn_id: return
        try:
            db.save_query_history(conn_id, query, status, rows, duration)
        except Exception as e:
            self.status.showMessage(f"Could not save query to history: {e}", 4000)

    def load_connection_history(self, target_tab):
        history_list_view = target_tab.findChild(QTreeView, "history_list_view")
        history_details_view = target_tab.findChild(QTextEdit, "history_details_view")
        db_combo_box = target_tab.findChild(QComboBox, "db_combo_box")
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(['Connection History'])
        history_list_view.setModel(model)
        history_details_view.clear()
        conn_data = db_combo_box.currentData()
        if not conn_data: return
        conn_id = conn_data.get("id")
        try:
            history = db.get_query_history(conn_id)
            for row in history:
                history_id, query, ts, status, rows, duration = row
                short_query = ' '.join(query.split())[:70] + ('...' if len(query) > 70 else '')
                dt = datetime.datetime.fromisoformat(ts)
                display_text = f"{short_query}\n{dt.strftime('%Y-%m-%d %H:%M:%S')}"
                item = QStandardItem(display_text)
                item.setData({"id": history_id, "query": query, "timestamp": dt.strftime('%Y-%m-%d %H:%M:%S'), "status": status, "rows": rows, "duration": f"{duration:.3f} sec"}, Qt.ItemDataRole.UserRole)
                model.appendRow(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load query history:\n{e}")

    def display_history_details(self, index, target_tab):
        history_details_view = target_tab.findChild(QTextEdit, "history_details_view")
        if not index.isValid() or not history_details_view: return
        data = index.model().itemFromIndex(index).data(Qt.ItemDataRole.UserRole)
        details_text = f"Timestamp: {data['timestamp']}\nStatus: {data['status']}\nDuration: {data['duration']}\nRows: {data['rows']}\n\n-- Query --\n{data['query']}"
        history_details_view.setText(details_text)

    def _get_selected_history_item(self, target_tab):
        """Helper to get the selected item's data from the history list."""
        history_list_view = target_tab.findChild(QTreeView, "history_list_view")
        selected_indexes = history_list_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "No Selection", "Please select a history item first.")
            return None
        item = selected_indexes[0].model().itemFromIndex(selected_indexes[0])
        return item.data(Qt.ItemDataRole.UserRole)

    def copy_history_query(self, target_tab):
        history_data = self._get_selected_history_item(target_tab)
        if history_data:
            clipboard = QApplication.clipboard()
            clipboard.setText(history_data['query'])
            self.status_message_label.setText("Query copied to clipboard.")

    def copy_history_to_editor(self, target_tab):
        history_data = self._get_selected_history_item(target_tab)
        if history_data:
            editor_stack = target_tab.findChild(QStackedWidget, "editor_stack")
            query_editor = target_tab.findChild(CodeEditor, "query_editor")
            query_editor.setPlainText(history_data['query'])
            
            # Switch back to the query editor view
            editor_stack.setCurrentIndex(0)
            query_view_btn = target_tab.findChild(QPushButton, "Query")
            history_view_btn = target_tab.findChild(QPushButton, "Query History")
            if query_view_btn: query_view_btn.setChecked(True)
            if history_view_btn: history_view_btn.setChecked(False)
            
            self.status_message_label.setText("Query copied to editor.")

    def remove_selected_history(self, target_tab):
        history_data = self._get_selected_history_item(target_tab)
        if not history_data: return
        
        history_id = history_data['id']
        reply = QMessageBox.question(self, "Remove History", "Are you sure you want to remove the selected query history?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db.delete_history_item(history_id)
                self.load_connection_history(target_tab) # Refresh the view
                target_tab.findChild(QTextEdit, "history_details_view").clear()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove history item:\n{e}")


    def remove_all_history_for_connection(self, target_tab):
        db_combo_box = target_tab.findChild(QComboBox, "db_combo_box")
        conn_data = db_combo_box.currentData()
        if not conn_data:
            QMessageBox.warning(self, "No Connection", "Please select a connection first.")
            return
        conn_id = conn_data.get("id")
        conn_name = db_combo_box.currentText()
        reply = QMessageBox.question(self, "Remove All History", f"Are you sure you want to remove all history for the connection:\n'{conn_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db.delete_all_history_for_connection(conn_id)
                self.load_connection_history(target_tab)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear history for this connection:\n{e}")



    
    

    # --- Schema Loading Methods ---
    def load_sqlite_schema(self, conn_data):
        self.schema_model.clear()
        self.schema_model.setHorizontalHeaderLabels(["Tables & Views"])
        db_path = conn_data.get("db_path")
        if not db_path or not os.path.exists(db_path):
            self.status.showMessage(f"Error: SQLite DB path not found: {db_path}", 5000)
            return
        try:
            conn = sqlite.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name;")
            tables = cursor.fetchall()
            conn.close()
            for name, type in tables:
                icon = QIcon("assets/table_icon.png") if type == 'table' else QIcon("assets/view_icon.png")
                item = QStandardItem(icon, name)
                item.setEditable(False)
                item.setData({'db_type': 'sqlite', 'conn_data': conn_data}, Qt.ItemDataRole.UserRole)
                self.schema_model.appendRow(item)
            if hasattr(self, '_expanded_connection'):
                try: self.schema_tree.expanded.disconnect(self._expanded_connection)
                except TypeError: pass
        except Exception as e:
            self.status.showMessage(f"Error loading SQLite schema: {e}", 5000)

    
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

    # def show_schema_context_menu(self, position):
    #     index = self.schema_tree.indexAt(position)
    #     if not index.isValid():
    #         return

    #     item = self.schema_model.itemFromIndex(index)
    #     item_data = item.data(Qt.ItemDataRole.UserRole)

    #     is_sqlite_table = item_data and item_data.get('db_type') == 'sqlite'
    #     is_postgres_table = item_data and item.parent(
    #     ) and item_data.get('db_type') == 'postgres'

    #     if not (is_sqlite_table or is_postgres_table):
    #         return

    #     table_name = item.text()
    #     menu = QMenu()

    #     view_menu = menu.addMenu("View/Edit Data")

    #     query_all_action = QAction("Query all rows from Table", self)
    #     query_all_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=None, execute_now=True))
    #     view_menu.addAction(query_all_action)

    #     preview_100_action = QAction("Preview first 100 rows", self)
    #     preview_100_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=100, execute_now=True))
    #     view_menu.addAction(preview_100_action)

    #     last_100_action = QAction("Show last 100 rows", self)
    #     last_100_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=100, order='desc', execute_now=True))
    #     view_menu.addAction(last_100_action)

    #     query_tool_action = QAction("Query Tool", self)
    #     query_tool_action.triggered.connect(
    #         lambda: self.open_query_tool_for_table(item_data, table_name))
    #     menu.addAction(query_tool_action)

    #     export_rows_action = QAction("Export Rows", self)
    #     export_rows_action.triggered.connect(
    #         lambda: self.export_schema_table_rows(item_data, table_name))
    #     menu.addAction(export_rows_action)

    #     menu.exec(self.schema_tree.viewport().mapToGlobal(position))

    # def show_schema_context_menu(self, position):
    #     index = self.schema_tree.indexAt(position)
    #     if not index.isValid():
    #         return
 
    #     item = self.schema_model.itemFromIndex(index)
    #     item_data = item.data(Qt.ItemDataRole.UserRole)

    #     if not item_data:
    #         return

    #     db_type = item_data.get("db_type")
    #     if db_type not in ("sqlite", "postgres"):
    #         return

    #     table_name = item.text()
    #     menu = QMenu()

    #     view_menu = menu.addMenu("View/Edit Data")

    #     query_all_action = QAction("Query all rows from Table", self)
    #     query_all_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=None, execute_now=True))
    #     view_menu.addAction(query_all_action)

    #     preview_100_action = QAction("Preview first 100 rows", self)
    #     preview_100_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=100, execute_now=True))
    #     view_menu.addAction(preview_100_action)

    #     last_100_action = QAction("Show last 100 rows", self)
    #     last_100_action.triggered.connect(
    #         lambda: self.query_table_rows(item_data, table_name, limit=100, order='desc', execute_now=True))
    #     view_menu.addAction(last_100_action)
  
    #     query_tool_action = QAction("Query Tool", self)
    #     query_tool_action.triggered.connect(
    #         lambda: self.open_query_tool_for_table(item_data, table_name))
    #     menu.addAction(query_tool_action)

    #     export_rows_action = QAction("Export Rows", self)
    #     export_rows_action.triggered.connect(
    #         lambda: self.export_schema_table_rows(item_data, table_name))
    #     menu.addAction(export_rows_action)

    #     properties_action = QAction("Properties", self)
    #     properties_action.triggered.connect(
    #         lambda: self.show_table_properties(item_data, table_name))
    #     menu.addAction(properties_action)

    #     menu.exec(self.schema_tree.viewport().mapToGlobal(position))


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
        


    def show_results_context_menu(self, position):
        results_table = self.sender()
        if not results_table or not results_table.model():
          return

        menu = QMenu()
        export_action = QAction("Export Rows", self)
        export_action.triggered.connect(lambda: self.export_result_rows(results_table))
        menu.addAction(export_action)

        menu.exec(results_table.viewport().mapToGlobal(position))

    
    
    def export_result_rows(self, table_view):
        model = table_view.model()
        if not model:
          QMessageBox.warning(self, "No Data", "No results available to export.")
          return

        dialog = ExportDialog(self, "query_results.csv")
        if dialog.exec() != QDialog.DialogCode.Accepted:
          return

        options = dialog.get_options()
        if not options['filename']:
          QMessageBox.warning(self, "No Filename", "Export cancelled. No filename specified.")
          return

        # --- Find connection name dynamically ---
        # get parent tab
        current_tab = self.tab_widget.currentWidget()
        db_combo_box = current_tab.findChild(QComboBox, "db_combo_box")
        conn_name = "Unknown"
        if db_combo_box:
          index = db_combo_box.currentIndex()
          if index >= 0:
              # Option 1: show text
              #conn_name = db_combo_box.itemText(index)
              # Option 2: if you stored dict in itemData(index), use something like:
              conn_data = db_combo_box.itemData(index)
              conn_name = conn_data.get("short_name", "Unknown")

        # --- Create Process info ---
        process_id = str(uuid.uuid4())
        initial_data = {
           "pid": process_id[:8],
           "type": "Export Data",
           "status": "Running",
           "server": conn_name,   # dynamically set
           "object": "Query Results",
           "time_taken": "...",
           "start_time": datetime.datetime.now().strftime("%Y-%m-%d, %I:%M:%S %p"),
           "details": f"Exporting to {os.path.basename(options['filename'])}"
        }

        signals = ProcessSignals()
        signals.started.connect(self.handle_process_started)
        signals.finished.connect(self.handle_process_finished)
        signals.error.connect(self.handle_process_error)
        signals.started.emit(process_id, initial_data)

        self.thread_pool.start(
          RunnableExportFromModel(process_id, model, options, signals)
        )

        

    def _initialize_processes_model(self):
        self.processes_model = QStandardItemModel()
        self.processes_model.setHorizontalHeaderLabels(
            ["PID", "Type", "Status", "Server", "Object", "Time Taken (sec)", "Start Time", "Details"])

        
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


    # def open_query_tool_for_table(self, item_data, table_name):
    #     self.query_table_rows(item_data, table_name, execute_now=False)


    def open_query_tool_for_table(self, item_data, table_name):
      if not item_data:
        return

      conn_data = item_data.get("conn_data")
      new_tab = self.add_tab()

      # Find the editor and connection dropdown
      query_editor = new_tab.findChild(QPlainTextEdit, "query_editor")
      db_combo_box = new_tab.findChild(QComboBox, "db_combo_box")

      # Select the correct connection in combo box
      for i in range(db_combo_box.count()):
        data = db_combo_box.itemData(i)
        if data and data.get('id') == conn_data.get('id'):
            db_combo_box.setCurrentIndex(i)
            break

      # Keep the editor empty for a fresh Query Tool
      query_editor.clear()

      # Set focus so the user can start typing immediately
      query_editor.setFocus()

      # Make sure the new tab becomes the active one
      self.tab_widget.setCurrentWidget(new_tab)


    def query_table_rows(self, item_data, table_name, limit=None, execute_now=True, order=None):
        if not item_data: return
        conn_data = item_data.get('conn_data')
        new_tab = self.add_tab()
        query_editor = new_tab.findChild(QPlainTextEdit, "query_editor")
        db_combo_box = new_tab.findChild(QComboBox, "db_combo_box")
        for i in range(db_combo_box.count()):
            data = db_combo_box.itemData(i)
            if data and data.get('id') == conn_data.get('id'):
                db_combo_box.setCurrentIndex(i)
                break
        if item_data.get('db_type') == 'postgres':
            query = f'SELECT * FROM "{item_data.get("schema_name")}"."{table_name}"'
        else:
            query = f'SELECT * FROM "{table_name}"'

        # This part for order is simplified; assumes a primary key exists for reliable ordering
        if order:
             query += f" ORDER BY 1 {order.upper()}"

        if limit:
            query += f" LIMIT {limit}"
        query_editor.setPlainText(query)
        if execute_now:
            # Must set current tab to the new tab before executing
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
            cursor.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_type, table_name;", (schema_name,))
            tables = cursor.fetchall()
            for (table_name, table_type) in tables:
                icon_path = "assets/table_icon.png" if "TABLE" in table_type else "assets/view_icon.png"
                table_item = QStandardItem(QIcon(icon_path), table_name)
                table_item.setEditable(False)
                table_item.setData(item_data, Qt.ItemDataRole.UserRole)
                item.appendRow(table_item)
        except Exception as e:
            self.status.showMessage(f"Error expanding schema: {e}", 5000)