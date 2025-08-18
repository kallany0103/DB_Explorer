# db_explorer/dialogs/oracle_dialog.py

import oracledb
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QFormLayout, QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox, QTextEdit
)

class OracleConnectionDialog(QDialog):
    def __init__(self, parent=None, is_editing=False):
        super().__init__(parent)
        self.setWindowTitle("Edit Oracle Connection" if is_editing else "New Oracle Connection")

        self.name_input = QLineEdit()
        self.user_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        # DSN (Data Source Name) is typically host:port/service_name
        self.dsn_input = QLineEdit()
        self.dsn_input.setPlaceholderText("e.g., localhost:1521/XEPDB1")

        form = QFormLayout()
        form.addRow("Connection Name:", self.name_input)
        form.addRow("User:", self.user_input)
        form.addRow("Password:", self.password_input)
        form.addRow("DSN (Host/Port/Service):", self.dsn_input)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)

        self.save_btn = QPushButton("Update" if is_editing else "Save")
        self.save_btn.clicked.connect(self.save_connection)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.test_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def test_connection(self):
        user = self.user_input.text()
        pwd = self.password_input.text()
        dsn = self.dsn_input.text()

        if not all([user, pwd, dsn]):
            QMessageBox.warning(self, "Missing Info", "User, Password, and DSN are required.")
            return
            
        try:
            conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
            conn.close()
            QMessageBox.information(self, "Success", "Connection successful!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to connect:\n{e}")

    def save_connection(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Missing Info", "Connection name is required.")
            return
        if not all([self.user_input.text(), self.password_input.text(), self.dsn_input.text()]):
            QMessageBox.warning(self, "Missing Info", "User, Password, and DSN are required.")
            return
        self.accept()

    def get_data(self):
        return {
            "name": self.name_input.text(),
            "user": self.user_input.text(),
            "password": self.password_input.text(),
            "dsn": self.dsn_input.text()
        }