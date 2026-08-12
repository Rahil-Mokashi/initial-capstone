from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Petrol Pump ERP")
        self.setMinimumSize(640, 480)

        message = QLabel("Welcome to Petrol Pump ERP\nUI MVP is running.")
        message.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(message)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)


def launch_app() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
