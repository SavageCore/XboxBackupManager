from PyQt6 import QtGui
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QStyledItemDelegate


class IconDelegate(QStyledItemDelegate):
    """Custom delegate for rendering icons properly in table cells"""

    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager

    def paint(self, painter, option, index):
        """Custom paint method for icon rendering"""
        if index.column() == 1:  # Icon column
            # Don't draw background - let the default item handle it
            # Just draw the icon and bottom border

            # Draw only bottom border (like other cells)
            # Use theme-appropriate border color
            if self.theme_manager and self.theme_manager.should_use_dark_mode():
                print("Dark mode active")
                border_color = QtGui.QColor("#222529")  # Dark theme
            else:
                border_color = QtGui.QColor("#e0e0e0")  # Light theme

            painter.setPen(QPen(border_color))
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

            # Get the icon from the item
            icon = index.data(Qt.ItemDataRole.DecorationRole)

            if icon and not icon.isNull():
                # Calculate center position for the icon with smaller size
                icon_size = 48  # Fixed size for icons
                rect = option.rect
                x = rect.x() + (rect.width() - icon_size) // 2
                y = rect.y() + (rect.height() - icon_size) // 2

                # Create target rect for the icon
                target_rect = QRect(x, y, icon_size, icon_size)

                # Draw the icon once
                icon.paint(painter, target_rect, Qt.AlignmentFlag.AlignCenter)

        else:
            # Use default painting for other columns
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        """Return size hint for items"""
        if index.column() == 1:  # Icon column
            return QSize(64, 64)  # Fixed size for icon column
        return super().sizeHint(option, index)
