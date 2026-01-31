from utils.qt import QtCore
from typing import Dict, List

class RoomListModel(QtCore.QAbstractListModel):
    """
    Model for displaying the list of Matrix rooms.
    """
    
    # Custom Roles
    RoomIdRole = QtCore.Qt.UserRole + 1
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rooms: Dict[str, str] = {}  # {room_id: display_name}
        self._room_ids: List[str] = []    # Ordered list of room IDs
        self._filtered_room_ids: List[str] = []  # Filtered view
        self._filter_active = True  # Start with filter active (hide all rooms initially)
    
    def rowCount(self, parent=QtCore.QModelIndex()):
        if self._filter_active:
            return len(self._filtered_room_ids)
        return len(self._room_ids)
    
    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        if self._filter_active:
            if row >= len(self._filtered_room_ids):
                return None
            room_id = self._filtered_room_ids[row]
        else:
            if row >= len(self._room_ids):
                return None
            room_id = self._room_ids[row]
        
        if role == QtCore.Qt.DisplayRole:
            name = self._rooms.get(room_id)
            return name if name else room_id
        elif role == self.RoomIdRole:
            return room_id
        
        return None
    
    def add_or_update_room(self, room_id: str, display_name: str):
        if room_id in self._rooms:
            # Update existing
            self._rooms[room_id] = display_name
            # Find row in current view
            if self._filter_active:
                if room_id in self._filtered_room_ids:
                    row = self._filtered_room_ids.index(room_id)
                    idx = self.index(row)
                    self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole])
            else:
                row = self._room_ids.index(room_id)
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole])
        else:
            # Add new
            self._rooms[room_id] = display_name
            if not self._filter_active:
                self.beginInsertRows(QtCore.QModelIndex(), len(self._room_ids), len(self._room_ids))
                self._room_ids.append(room_id)
                self.endInsertRows()
            else:
                # Just add to master list, don't show if filter is active
                self._room_ids.append(room_id)
    
    def filter_by_space(self, child_room_ids: List[str]):
        """Filter rooms to show only those in the given list."""
        print(f"DEBUG: RoomListModel filtering to {len(child_room_ids)} rooms. Total rooms in model: {len(self._rooms)}")
        self.beginResetModel()
        self._filter_active = True
        self._filtered_room_ids = []
        for rid in child_room_ids:
            if rid in self._rooms:
                self._filtered_room_ids.append(rid)
            else:
                # This happens if we have a hierarchy but haven't synced/joined the room yet
                pass
        
        print(f"DEBUG: After filtering, showing {len(self._filtered_room_ids)} out of {len(child_room_ids)} requested.")
        self.endResetModel()
    
    def clear_filter(self):
        """Remove filter and show all rooms."""
        self.beginResetModel()
        self._filter_active = False
        self._filtered_room_ids = []
        self.endResetModel()
    
    def remove_room(self, room_id: str):
        if room_id in self._rooms:
            # Find row in master list
            row = self._room_ids.index(room_id)
            
            # If active in filtered view, remove from there too
            if self._filter_active and room_id in self._filtered_room_ids:
                f_row = self._filtered_room_ids.index(room_id)
                self.beginRemoveRows(QtCore.QModelIndex(), f_row, f_row)
                self._filtered_room_ids.pop(f_row)
                self.endRemoveRows()
            elif not self._filter_active:
                self.beginRemoveRows(QtCore.QModelIndex(), row, row)
                # No need to remove from _filtered_room_ids since not active
                self.endRemoveRows()
            
            # Always remove from master lists
            self._room_ids.pop(row)
            del self._rooms[room_id]

    def clear(self):
        self.beginResetModel()
        self._room_ids.clear()
        self._rooms.clear()
        self.endResetModel()
