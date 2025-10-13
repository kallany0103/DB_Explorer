# main.py
import sys
from PyQt6.QtWidgets import QApplication
from db import initialize_database
from main_window import MainWindow

if __name__ == "__main__":
    initialize_database()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    