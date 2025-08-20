from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyledItemDelegate


class IconDelegate(QStyledItemDelegate):
    """Custom delegate to properly display and center icons"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Custom paint method to center icons"""
        if index.column() == 0:  # Icon column
            # Store the original icon
            original_icon = index.data(Qt.ItemDataRole.DecorationRole)

            # Temporarily remove the icon to prevent default painting
            index.model().setData(index, QIcon(), Qt.ItemDataRole.DecorationRole)

            # Let the default delegate handle background painting only
            super().paint(painter, option, index)

            # Restore the original icon
            index.model().setData(index, original_icon, Qt.ItemDataRole.DecorationRole)

            # Now draw our custom centered icon
            if isinstance(original_icon, QIcon) and not original_icon.isNull():
                pixmap = original_icon.pixmap(64, 64)
                if not pixmap.isNull():
                    rect = option.rect
                    pixmap_rect = pixmap.rect()

                    x = rect.x() + (rect.width() - pixmap_rect.width()) // 2
                    y = rect.y() + (rect.height() - pixmap_rect.height()) // 2

                    painter.drawPixmap(x, y, pixmap)

            return

        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        """Return size hint for items"""
        if index.column() == 0:  # Icon column
            return QSize(80, 72)
        return super().sizeHint(option, index)
