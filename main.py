import sys
from PyQt6.QtWidgets import QApplication
# db.py now  inside of dialogs
from dialogs.db import initialize_database
from main_window import MainWindow

if __name__ == "__main__":
    # database and necessary table  create
    initialize_database()

    # main application start
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

    # Added main.py
