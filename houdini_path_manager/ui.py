import hou
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QLineEdit, QLabel, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt

class ExternalPathManagerUI(QWidget):
    def __init__(self, parent=None):
        if parent is None:
            if hasattr(hou, "qt") and hasattr(hou.qt, "mainWindow"):
                parent = hou.qt.mainWindow()
        super().__init__(parent)
        
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setWindowTitle("External Path Manager")
        self.resize(800, 500)
        
        self.parm_list = []
        
        self.init_ui()
        self.refresh_list()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self.refresh_list)
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        
        top_layout.addWidget(self.refresh_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.select_all_btn)
        top_layout.addWidget(self.deselect_all_btn)
        
        layout.addLayout(top_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Select", "Node Path", "Parameter", "File Path (Unexpanded)"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("Search:"))
        self.search_le = QLineEdit()
        bottom_layout.addWidget(self.search_le)
        
        bottom_layout.addWidget(QLabel("Replace:"))
        self.replace_le = QLineEdit()
        bottom_layout.addWidget(self.replace_le)
        
        self.apply_btn = QPushButton("Apply Replace to Selected")
        self.apply_btn.clicked.connect(self.apply_replace)
        bottom_layout.addWidget(self.apply_btn)
        
        layout.addLayout(bottom_layout)
        
    def refresh_list(self):
        self.table.setRowCount(0)
        self.parm_list.clear()
        
        try:
            refs = hou.fileReferences()
        except AttributeError:
            QMessageBox.critical(self, "Error", "hou.fileReferences is not available. Please run inside Houdini.")
            return

        seen_parms = set()
        row = 0
        for parm, ref_path in refs:
            if parm is None:
                continue
            if parm in seen_parms:
                continue
            seen_parms.add(parm)
            
            node = parm.node()
            
            self.table.insertRow(row)
            
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(checkbox)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0,0,0,0)
            
            self.table.setCellWidget(row, 0, cb_widget)
            
            self.table.setItem(row, 1, QTableWidgetItem(node.path()))
            self.table.setItem(row, 2, QTableWidgetItem(parm.name()))
            
            unexpanded_val = parm.unexpandedString()
            self.table.setItem(row, 3, QTableWidgetItem(unexpanded_val))
            
            self.parm_list.append((parm, checkbox))
            row += 1

    def select_all(self):
        for _, checkbox in self.parm_list:
            checkbox.setChecked(True)
            
    def deselect_all(self):
        for _, checkbox in self.parm_list:
            checkbox.setChecked(False)

    def apply_replace(self):
        search_str = self.search_le.text()
        replace_str = self.replace_le.text()
        
        if not search_str:
            QMessageBox.warning(self, "Warning", "Search string cannot be empty.")
            return
            
        count = 0
        with hou.undogroup("Batch Replace External Paths"):
            for row in range(self.table.rowCount()):
                parm, checkbox = self.parm_list[row]
                if checkbox.isChecked():
                    current_val = parm.unexpandedString()
                    if search_str in current_val:
                        new_val = current_val.replace(search_str, replace_str)
                        try:
                            parm.set(new_val)
                            count += 1
                        except Exception as e:
                            print(f"Failed to set parameter {parm.path()}: {e}")
        
        QMessageBox.information(self, "Success", f"Replaced paths in {count} parameters.")
        self.refresh_list()

def show_ui():
    if not hasattr(hou.session, 'external_path_manager'):
        hou.session.external_path_manager = ExternalPathManagerUI()
    
    hou.session.external_path_manager.refresh_list()
    hou.session.external_path_manager.show()
    hou.session.external_path_manager.raise_()
    hou.session.external_path_manager.activateWindow()

if __name__ == "__main__":
    show_ui()
