from utils.qt import QtCore

class SpacesModel(QtCore.QAbstractListModel):
    """
    Model for storing Matrix Spaces (m.space).
    """
    SpaceIdRole = QtCore.Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._space_ids = []
        self._spaces = {} # id -> name

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        
        # Virtual item at the end for Rooms & DMs
        if row == len(self._space_ids):
            if role == QtCore.Qt.DisplayRole:
                return "Rooms & DMs"
            elif role == self.SpaceIdRole:
                return "v.spaceless"
            return None

        if row >= len(self._space_ids):
            return None
        
        space_id = self._space_ids[row]
        
        if role == QtCore.Qt.DisplayRole:
            return self._spaces.get(space_id, space_id)
            
        elif role == self.SpaceIdRole:
            return space_id
            
        return None

    def rowCount(self, parent=QtCore.QModelIndex()):
        # Actual spaces + 1 virtual entry for spaceless rooms
        return len(self._space_ids) + 1

    def add_or_update_space(self, space_id: str, display_name: str):
        if space_id in self._spaces:
            # Update existing
            self._spaces[space_id] = display_name
            row = self._space_ids.index(space_id)
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole])
        else:
            # Add new
            self.beginInsertRows(QtCore.QModelIndex(), len(self._space_ids), len(self._space_ids))
            self._space_ids.append(space_id)
            self._spaces[space_id] = display_name
            self.endInsertRows()
    
    def remove_space(self, space_id: str):
        if space_id in self._spaces:
            row = self._space_ids.index(space_id)
            self.beginRemoveRows(QtCore.QModelIndex(), row, row)
            self._space_ids.pop(row)
            del self._spaces[space_id]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._space_ids.clear()
        self._spaces.clear()
        self.endResetModel()
