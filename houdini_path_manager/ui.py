import hou
import os
import re
import glob
import subprocess
import platform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QLineEdit, QLabel, QCheckBox, QMessageBox, QComboBox
)
from PySide6.QtGui import QColor, QBrush
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
        self.row_colors = []  # stores 'green', 'yellow', 'red' per row
        
        self.init_ui()
        self.refresh_list()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        top_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh List")
        self.refresh_btn.setFixedWidth(30)
        self.refresh_btn.clicked.connect(self.refresh_list)
        
        self.ext_filter_cb = QCheckBox("Images & Caches Only")
        self.ext_filter_cb.setChecked(True)
        self.ext_filter_cb.stateChanged.connect(self.refresh_list)
        
        self.exclude_chs_cb = QCheckBox("Exclude chs()")
        self.exclude_chs_cb.setChecked(True)
        self.exclude_chs_cb.stateChanged.connect(self.refresh_list)
        
        self.filter_mode = QComboBox()
        self.filter_mode.addItem("Node Path", 0)   # column index 0
        self.filter_mode.addItem("File Path", 2)   # column index 2
        self.filter_mode.currentIndexChanged.connect(self._on_filter_mode_changed)

        self.filter_le = QLineEdit()
        self.filter_le.setPlaceholderText("Filter by node path...")
        self.filter_le.textChanged.connect(self.filter_table)

        # Color status toggle buttons
        toggle_style = "QPushButton {{ background-color: {bg}; color: {fg}; border: 2px solid transparent; border-radius: 4px; padding: 3px 8px; font-weight: bold; }} QPushButton:checked {{ border: 2px solid white; }}"
        self.btn_green = QPushButton("●")
        self.btn_green.setToolTip("Show only existing paths")
        self.btn_green.setCheckable(True)
        self.btn_green.setStyleSheet(toggle_style.format(bg="#3a7a3a", fg="white"))
        self.btn_green.toggled.connect(self.filter_table)

        self.btn_yellow = QPushButton("●")
        self.btn_yellow.setToolTip("Show only partial/sequence paths")
        self.btn_yellow.setCheckable(True)
        self.btn_yellow.setStyleSheet(toggle_style.format(bg="#7a7a20", fg="white"))
        self.btn_yellow.toggled.connect(self.filter_table)

        self.btn_red = QPushButton("●")
        self.btn_red.setToolTip("Show only missing paths")
        self.btn_red.setCheckable(True)
        self.btn_red.setStyleSheet(toggle_style.format(bg="#7a2020", fg="white"))
        self.btn_red.toggled.connect(self.filter_table)

        top_layout.addWidget(self.refresh_btn)
        top_layout.addWidget(self.ext_filter_cb)
        top_layout.addWidget(self.exclude_chs_cb)
        top_layout.addWidget(QLabel("Filter:"))
        top_layout.addWidget(self.filter_mode)
        top_layout.addWidget(self.filter_le)
        top_layout.addWidget(self.btn_green)
        top_layout.addWidget(self.btn_yellow)
        top_layout.addWidget(self.btn_red)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Node Path", "Parameter", "File Path (Unexpanded)"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        # Allow single-click editing for column 2 only
        self.table.setEditTriggers(QTableWidget.SelectedClicked | QTableWidget.AnyKeyPressed)
        
        # Geometry Spreadsheet style: alternating rows, vertical black lines only
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("QTableWidget::item { border-right: 1px solid black; }")
        
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.itemChanged.connect(self.on_path_item_changed)
        
        layout.addWidget(self.table)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("Search:"))
        self.search_le = QLineEdit()
        bottom_layout.addWidget(self.search_le)
        
        bottom_layout.addWidget(QLabel("Replace:"))
        self.replace_le = QLineEdit()
        bottom_layout.addWidget(self.replace_le)
        
        self.apply_btn = QPushButton("Apply Replace")
        self.apply_btn.setToolTip("Apply replace to selected rows, or to all visible rows if nothing is selected.")
        self.apply_btn.clicked.connect(self.apply_replace)
        bottom_layout.addWidget(self.apply_btn)
        
        layout.addLayout(bottom_layout)
        
    def refresh_list(self):
        self.table.setRowCount(0)
        self.parm_list.clear()
        self.row_colors.clear()
        
        try:
            refs = list(hou.fileReferences())
        except AttributeError:
            QMessageBox.critical(self, "Error", "hou.fileReferences is not available. Please run inside Houdini.")
            return

        # Manually scan for filecache nodes in the scene to include them
        try:
            for node in hou.node("/").allSubChildren():
                if "filecache" in node.type().name().lower():
                    for parm_name in ("file", "sopoutput"):
                        parm = node.parm(parm_name)
                        if parm:
                            refs.append((parm, parm.evalAsString()))
        except Exception as e:
            print(f"Error scanning for filecache nodes: {e}")

        seen_parms = set()
        
        CACHE_IMAGE_EXTS = (
            '.bgeo', '.sc', '.gz', '.lzma',
            '.vdb', '.abc', '.fbx', '.obj', '.usd', '.usda', '.usdc', '.usdz',
            '.ass', '.rs', '.ifd',
            '.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.hdr', '.pic', '.rat', 
            '.tga', '.tex', '.tx', '.bmp'
        )
        only_caches = self.ext_filter_cb.isChecked()
        exclude_chs = self.exclude_chs_cb.isChecked()
        
        row = 0
        for parm, ref_path in refs:
            if parm is None:
                continue
                
            if only_caches and ref_path:
                if not ref_path.lower().endswith(CACHE_IMAGE_EXTS):
                    continue
                    
            unexpanded_val = self.get_parm_string(parm)
            if exclude_chs and "chs(" in unexpanded_val:
                continue
                    
            if parm in seen_parms:
                continue
            seen_parms.add(parm)
            
            node = parm.node()
            
            self.table.insertRow(row)
            
            node_item = QTableWidgetItem(node.path())
            node_item.setFlags(node_item.flags() & ~Qt.ItemIsEditable)
            node_item.setToolTip(node.path())
            try:
                if hasattr(hou, "qt"):
                    icon = hou.qt.Icon(node.type().icon())
                    node_item.setIcon(icon)
            except Exception:
                pass
            self.table.setItem(row, 0, node_item)
            
            parm_item = QTableWidgetItem(parm.name())
            parm_item.setFlags(parm_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, parm_item)
            
            unexpanded_val = self.get_parm_string(parm)
            # Also show the expanded (evaluated) path in the tooltip
            evaluated_val = parm.evalAsString()
            path_item = QTableWidgetItem(unexpanded_val)
            path_color = self.get_path_color(parm, unexpanded_val)
            path_item.setForeground(QBrush(path_color))
            path_item.setToolTip(f"Unexpanded: {unexpanded_val}\nExpanded:   {evaluated_val}")
            self.table.setItem(row, 2, path_item)
            
            self.parm_list.append(parm)
            
            # Store color status for this row
            # Yellow: (255,255,120) - both R and G are high
            # Green:  (120,255,120) - only G is high
            # Red:    (255,120,120) - only R is high
            r, g, b = path_color.red(), path_color.green(), path_color.blue()
            if r > 200 and g > 200:
                self.row_colors.append('yellow')
            elif g > 200:
                self.row_colors.append('green')
            else:
                self.row_colors.append('red')
            
            row += 1
            
        current_filter = self.filter_le.text()
        if current_filter:
            self.filter_table(current_filter)

    def on_path_item_changed(self, item):
        if item.column() != 2:
            return
        row = item.row()
        if row >= len(self.parm_list):
            return
        parm = self.parm_list[row]
        new_val = item.text()
        try:
            with hou.undos.group("Edit External Path"):
                parm.set(new_val)
            # Update color without full refresh
            path_color = self.get_path_color(parm, new_val)
            self.table.blockSignals(True)
            item.setForeground(QBrush(path_color))
            self.table.blockSignals(False)
            # Update stored color
            r, g, b = path_color.red(), path_color.green(), path_color.blue()
            if r > 200 and g > 200:
                self.row_colors[row] = 'yellow'
            elif g > 200:
                self.row_colors[row] = 'green'
            else:
                self.row_colors[row] = 'red'
        except Exception as e:
            print(f"Failed to set parameter {parm.path()}: {e}")

    def on_item_double_clicked(self, item):
        col = item.column()
        row = item.row()
        parm = self.parm_list[row]
        
        if col == 0: # Node Path
            node = parm.node()
            if node:
                node.setSelected(True, clear_all_selected=True)
                pane_tab = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
                if pane_tab:
                    pane_tab.setPwd(node.parent())
        elif col == 2: # File Path
            evaluated = parm.evalAsString()
            
            if os.path.isfile(evaluated):
                target_dir = os.path.dirname(evaluated)
            else:
                target_dir = evaluated if os.path.isdir(evaluated) else os.path.dirname(evaluated)
                
            # Traverse up until an existing directory is found
            while target_dir and not os.path.exists(target_dir):
                parent_dir = os.path.dirname(target_dir)
                if parent_dir == target_dir: # Reached root
                    break
                target_dir = parent_dir
                
            if target_dir and os.path.exists(target_dir):
                system = platform.system()
                try:
                    if system == "Windows":
                        os.startfile(target_dir)
                    elif system == "Darwin":
                        subprocess.Popen(["open", target_dir])
                    else:
                        subprocess.Popen(["xdg-open", target_dir])
                except Exception as e:
                    print(f"Failed to open directory: {e}")

    def get_parm_string(self, parm):
        try:
            return parm.unexpandedString()
        except hou.OperationFailed:
            try:
                return parm.rawValue()
            except:
                return parm.evalAsString()

    def get_path_color(self, parm, unexpanded_val):
        evaluated = parm.evalAsString()
        
        # Seq variables: $F, $F2.., $SF, $N, $T, <UDIM>, %(UDIM)d
        # Use negative lookahead (?![a-zA-Z_]) to prevent matching $T inside $TEX
        seq_pattern = r'(\$[S]*F\d*(?![a-zA-Z_])|\$T(?![a-zA-Z_])|\$N(?![a-zA-Z_])|<UDIM>|%\(UDIM\)d)'
        
        if re.search(seq_pattern, unexpanded_val):
            # evaluated path expands Houdini variables and evaluates the current frame.
            # But we want to check if ANY frame/UDIM exists, so we glob the basename.
            eval_dir = os.path.dirname(evaluated)
            unexp_base = os.path.basename(unexpanded_val)
            
            # Escape the directory in case it contains '[' or ']' characters which break glob
            try:
                eval_dir_escaped = glob.escape(eval_dir)
            except AttributeError:
                eval_dir_escaped = eval_dir # fallback for very old python
                
            glob_base = re.sub(seq_pattern, '*', unexp_base)
            glob_path = os.path.join(eval_dir_escaped, glob_base)
            
            if glob.glob(glob_path):
                return QColor(255, 255, 120) # Yellow (sequence exists)
            else:
                return QColor(255, 120, 120) # Red (missing)
        else:
            if os.path.exists(evaluated):
                return QColor(120, 255, 120) # Green (exists)
            else:
                return QColor(255, 120, 120) # Red (missing)

    def _on_filter_mode_changed(self):
        col = self.filter_mode.currentData()
        if col == 0:
            self.filter_le.setPlaceholderText("Filter by node path...")
        else:
            self.filter_le.setPlaceholderText("Filter by file path...")
        self.filter_table(self.filter_le.text())

    def filter_table(self, *args):
        search_text = self.filter_le.text().lower()
        col = self.filter_mode.currentData()
        
        active_colors = set()
        if self.btn_green.isChecked():
            active_colors.add('green')
        if self.btn_yellow.isChecked():
            active_colors.add('yellow')
        if self.btn_red.isChecked():
            active_colors.add('red')
        
        for row in range(self.table.rowCount()):
            # Text filter
            item = self.table.item(row, col)
            text_match = (not search_text) or (item and search_text in item.text().lower())
            
            # Color filter (applied after text filter)
            if active_colors:
                row_color = self.row_colors[row] if row < len(self.row_colors) else 'red'
                color_match = row_color in active_colors
            else:
                color_match = True
            self.table.setRowHidden(row, not (text_match and color_match))


 
    def apply_replace(self):
        search_str = self.search_le.text()
        replace_str = self.replace_le.text()
        
        if not search_str:
            QMessageBox.warning(self, "Warning", "Search string cannot be empty.")
            return
            
        # Determine target rows:
        # If there is an active selection in the table, target those rows.
        # Otherwise, target all visible (non-hidden) rows.
        selected_indexes = self.table.selectionModel().selectedRows()
        selected_rows = {index.row() for index in selected_indexes}
        
        target_rows = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            if selected_rows:
                if row in selected_rows:
                    target_rows.append(row)
            else:
                target_rows.append(row)
                
        if not target_rows:
            QMessageBox.warning(self, "Warning", "No rows selected or visible to apply replacement.")
            return
            
        count = 0
        with hou.undos.group("Batch Replace External Paths"):
            for row in target_rows:
                parm = self.parm_list[row]
                current_val = self.get_parm_string(parm)
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
