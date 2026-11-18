GREEN = "#4bb14e"

APP_STYLE = """
            QMainWindow, QWidget#background { background: #f9fafc; }
            QFrame#card { background: white; border-radius: 40px; }
            QLabel#keyTitle { color: #4bb14e; font: bold 19pt 'Arial'; background: transparent; }
            QPushButton#submit { color: white; background: #4bb14e; border: none;
                border-radius: 28px; font: bold 19pt 'Arial'; }
            QPushButton#submit:hover, QPushButton#expand:hover { background: #409a43; }
            QPushButton#submit:pressed, QPushButton#expand:pressed { background: #348138; }
            QPushButton#submit:disabled { background: #a2cfa4; }
            QPushButton#submit:focus, QPushButton#expand:focus { border: 2px solid #276d2a; }
            QLabel#consoleBadge { background: #a7adb1; color: white; border-radius: 17px;
                font: bold 10pt 'Arial'; }
            QPushButton#expand { background: #4bb14e; color: white; border-radius: 17px;
                border: none; font: bold 19pt 'Arial'; }
        """
