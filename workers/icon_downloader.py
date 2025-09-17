import base64
import ctypes
import struct
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple, cast

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from xbe import StructurePrintMixin, Xbe  # type: ignore

from utils.system_utils import SystemUtils
from utils.xboxunity import XboxUnity

if TYPE_CHECKING:
    RGBA = Tuple[float, float, float, float]


class IconDownloader(QThread):
    """Thread to download game icons"""

    icon_downloaded = pyqtSignal(str, QPixmap)  # title_id, pixmap
    download_failed = pyqtSignal(str)  # title_id

    def __init__(
        self,
        title_ids: List[str],
        platform: str = "xbox360",
        current_directory: str = None,
    ):
        super().__init__()
        self.title_ids = title_ids
        self.platform = platform
        self.current_directory = Path(current_directory) if current_directory else None
        self.cache_dir = Path("cache/icons")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.system_utils = SystemUtils()
        self.xbox_unity = XboxUnity()

    def run(self):
        for title_id, folder_name in self.title_ids:
            try:
                pixmap = self._get_or_download_icon(title_id, folder_name)
                if pixmap:
                    self.icon_downloaded.emit(title_id, pixmap)
                else:
                    self.download_failed.emit(title_id)
            except Exception:
                self.download_failed.emit(title_id)

    def _get_or_download_icon(self, title_id: str, folder_name: str) -> QPixmap:
        """Get icon from cache or download it"""
        cache_file = self.cache_dir / f"{title_id}.png"

        # Check if cached version exists
        if cache_file.exists():
            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap

        # Check if this is an extracted ISO game (default.xex), GoD game, or Xbox game (default.xbe)
        if self.current_directory and self.current_directory.exists():
            # Look for the game in the current directory
            game_dir = self.current_directory / folder_name
            xex_path = game_dir / "default.xex"
            if self.platform == "xbox360":
                god_header_path = game_dir / "00007000"
            elif self.platform == "xbla":
                god_header_path = game_dir / "000D0000"
            xbe_path = game_dir / "default.xbe"

            # Try XEX extraction first (Xbox 360 extracted ISO games)
            if self.platform == "xbox360" and xex_path.exists():
                icon_pixmap = self._extract_icon_from_xex(xex_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

            # Try GoD extraction (Xbox 360 Games on Demand)
            elif (
                self.platform in ["xbox360", "xbla"]
                and god_header_path.exists()
                and god_header_path.is_dir()
            ):
                icon_pixmap = self._extract_icon_from_god(god_header_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

            # Try XBE extraction (Original Xbox games)
            elif self.platform == "xbox" and xbe_path.exists():
                icon_pixmap = self._extract_icon_from_xbe(xbe_path, title_id)
                if not icon_pixmap.isNull():
                    return icon_pixmap

        # Download from Xbox Unity or MobCat
        try:
            if self.platform in ["xbox360", "xbla"]:
                # url = f"https://xboxunity.net/Resources/Lib/Icon.php?tid={title_id}&custom=1"
                url = f"https://raw.githubusercontent.com/UncreativeXenon/XboxUnity-Scraper/refs/heads/master/Icons/{title_id}.png"
            else:
                url = f"https://raw.githubusercontent.com/MobCat/MobCats-original-xbox-game-list/main/icon/{title_id[:4]}/{title_id}.png"

            if not url:
                return QPixmap()  # No URL available for this platform

            print(f"Downloading icon from {url}")

            urllib.request.urlretrieve(url, str(cache_file))

            pixmap = QPixmap(str(cache_file))
            if not pixmap.isNull():
                return pixmap
        except (urllib.error.URLError, urllib.error.HTTPError, Exception):
            pass

        return QPixmap()  # Return empty pixmap on failure

    def _extract_icon_from_xex(self, xex_path: Path, expected_title_id: str) -> QPixmap:
        """Extract icon from XEX file using xextool"""
        try:
            xex_info = self.system_utils.extract_xex_info(str(xex_path))
            if not xex_info:
                return QPixmap()

            # Verify this XEX belongs to the title we're looking for
            extracted_title_id = xex_info.get("title_id")
            if extracted_title_id != expected_title_id:
                return QPixmap()

            # Get the icon data
            icon_base64 = xex_info.get("icon_base64")
            if not icon_base64:
                return QPixmap()

            # Decode base64 and create pixmap
            icon_data = base64.b64decode(icon_base64)
            pixmap = QPixmap()
            pixmap.loadFromData(icon_data)

            # Cache the icon for future use
            if not pixmap.isNull():
                cache_file = self.cache_dir / f"{expected_title_id}.png"
                pixmap.save(str(cache_file), "PNG")

            return pixmap

        except Exception:
            return QPixmap()

    def _extract_icon_from_god(
        self, god_header_path: Path, expected_title_id: str
    ) -> QPixmap:
        """Extract icon from GoD file using XboxUnity"""
        try:
            # Find the first header file in the 00007000 directory
            header_files = list(god_header_path.glob("*"))
            if not header_files:
                return QPixmap()

            # Use the first header file found
            header_file_path = str(header_files[0])

            # Extract GoD information including icon
            god_info = self.xbox_unity.get_god_info(header_file_path)
            if not god_info:
                return QPixmap()

            # Verify this GoD file belongs to the title we're looking for
            extracted_title_id = god_info.get("title_id")
            if extracted_title_id and extracted_title_id != expected_title_id:
                # Title ID doesn't match, but still try to use the icon
                # (in case the folder was renamed)
                pass

            # Get the icon data
            icon_base64 = god_info.get("icon_base64")
            if not icon_base64:
                return QPixmap()

            # Decode base64 and create pixmap
            icon_data = base64.b64decode(icon_base64)
            pixmap = QPixmap()
            pixmap.loadFromData(icon_data)

            # Cache the icon for future use (use the expected title ID for consistent caching)
            if not pixmap.isNull():
                cache_file = self.cache_dir / f"{expected_title_id}.png"
                pixmap.save(str(cache_file), "PNG")

            return pixmap

        except Exception:
            return QPixmap()

    def _encode_bmp(self, w: int, h: int, pixels: List["RGBA"]) -> bytes:
        """
        Encode a standard Windows BMP Image File
        """
        enc = b""
        for y in range(h):
            y = h - y - 1  # Bitmap encodes the image "bottom-up"
            for x in range(w):
                r, g, b, a = pixels[y * w + x]
                enc += struct.pack(
                    "<BBBB", int(255 * b), int(255 * g), int(255 * r), int(255 * a)
                )

        # Encode BITMAPV5HEADER
        # https://docs.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapv5header
        hdr = b"BM" + struct.pack(
            "<3I 3I2H11I48x I12x",
            # Bitmap File Header
            14 + 124 + len(enc),  # Total size
            0,  # Reserved
            14 + 124,  # Offset to pixel array
            # DIB Header
            124,  # sizeof(BITMAPV5INFOHEADER)
            w,
            h,  # Image dimensions
            1,  # No. color planes
            32,  # BPP
            3,  # BI_BITFIELDS
            len(enc),  # Image size
            2835,
            2835,  # Horizontal, Vertical Resolution (72DPI)
            0,  # Colors in palette (0=2^n)
            0,  # Important colors (0=all colors)
            0x00FF0000,  # Red channel bitmask
            0x0000FF00,  # Green channel bitmask
            0x000000FF,  # Blue channel bitmask
            0xFF000000,  # Alpha channel bitmask
            0x73524742,  # sRGB color space
            4,  # LCS_GM_IMAGES
        )

        return hdr + enc

    def _mix(self, x: "RGBA", y: "RGBA", a: float) -> "RGBA":
        """
        Linearly interpolate between x and y, returning x*(1-a) + y*a for all elements
        """
        assert len(x) == len(y)
        return cast("RGBA", tuple(x[i] * (1 - a) + y[i] * (a) for i in range(len(x))))

    def _unpack_r5g6b5(self, value: int) -> "RGBA":
        """
        Unpack a 16-bit (565) RGB as a real-value color tuple in the range of [0,1]
        """
        r = self._get_bits(value, 15, 11)
        g = self._get_bits(value, 10, 5)
        b = self._get_bits(value, 4, 0)
        return (r / 31, g / 63, b / 31, 1)

    def _get_bits(self, value: int, hi: int, lo: int) -> int:
        """
        Extract a bitrange from an integer
        """
        return (value & ((1 << (hi + 1)) - 1)) >> lo

    def _decode_bc1(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """
        Decode a BC1 (aka DXT1) compressed image to a list of pixel real-value color
        tuples

        More information about BC1 can be found at: https://docs.microsoft.com/en-us/windows/win32/direct3d10/d3d10-graphics-programming-guide-resources-block-compression#bc1
        """  # noqa: E501, pylint:disable=line-too-long
        assert w % 4 == 0
        assert h % 4 == 0
        blocks_per_row = w // 4
        blocks_per_col = h // 4
        num_blocks = blocks_per_row * blocks_per_col
        num_bytes = num_blocks * 8
        assert len(data) >= num_bytes
        pixels: List[RGBA] = [(0.0, 0.0, 0.0, 0.0) for _ in range(w * h)]

        # Decode blocks
        for block_idx in range(num_blocks):
            block_y = (block_idx // blocks_per_row) * 4
            block_x = (block_idx % blocks_per_row) * 4
            block_data = data[(block_idx * 8) : (block_idx * 8 + 8)]

            c0_raw, c1_raw, indices = struct.unpack("<HHI", block_data[0:8])
            alpha_enabled = c0_raw <= c1_raw
            c0, c1 = self._unpack_r5g6b5(c0_raw), self._unpack_r5g6b5(c1_raw)

            if alpha_enabled:
                mixed = self._mix(c0, c1, 1 / 2)
                mixed2 = (0.0, 0.0, 0.0, 0.0)
            else:
                mixed = self._mix(c0, c1, 1 / 3)
                mixed2 = self._mix(c0, c1, 2 / 3)
            colors = (c0, c1, mixed, mixed2)

            for y in range(4):
                for x in range(4):
                    bit_off = y * 8 + x * 2
                    color_idx = self._get_bits(indices, bit_off + 1, bit_off)
                    addr = (block_y + y) * w + (block_x + x)
                    pixels[addr] = colors[color_idx]

        return pixels

    def _xbx_to_bmp(self, xbx_data: bytes) -> bytes:
        """Convert XBX image data to BMP format"""
        try:
            # Check if it's XPR or DDS format
            if len(xbx_data) >= 4:
                magic = struct.unpack("<I", xbx_data[0:4])[0]
                if magic == 0x30525058:  # XPR0
                    w, h, pixels = self._decode_xpr_image(xbx_data)
                elif magic == 0x20534444:  # DDS
                    w, h, pixels = self._decode_dds_image(xbx_data)
                else:
                    print(f"Unknown image format magic: 0x{magic:08X}")
                    raise ValueError(f"Unsupported image format: 0x{magic:08X}")
            else:
                raise ValueError("Image data too small")
        except Exception as e:
            print(f"Error decoding image: {e}")
            raise
        try:
            bmp_data = self._encode_bmp(w, h, pixels)
        except Exception as e:
            print(f"Error encoding BMP image: {e}")
            return bytes()
        return bmp_data

    def _extract_icon_from_xbe(self, xbe_path: Path, expected_title_id: str) -> QPixmap:
        """Extract icon from XBE file using pyxbe Python API directly"""
        try:
            xbe = Xbe.from_file(str(xbe_path))
            # Try to get the title image section
            xtimage_section = xbe.sections.get("$$XTIMAGE")
            if not xtimage_section:
                print("[WARNING] XBE file does not contain $$XTIMAGE section")
                return QPixmap()
            # The section's data is the raw BMP image
            image_data = xtimage_section.data
            if not image_data:
                print("[WARNING] No image data found in $$XTIMAGE section")
                return QPixmap()
            # Convert XBX to BMP
            try:
                image_data = self._xbx_to_bmp(image_data)
            except Exception as e:
                print(f"Error converting XBX to BMP: {e}")
                return QPixmap()
            # Load BMP data into QPixmap
            pixmap = QPixmap()
            if pixmap.loadFromData(image_data, "BMP"):
                # Optionally cache as PNG
                if not pixmap.isNull():
                    cache_file = self.cache_dir / f"{expected_title_id}.png"
                    pixmap.save(str(cache_file), "PNG")
                return pixmap
            else:
                return QPixmap()
        except Exception as e:
            print(f"Exception in XBE icon extraction: {e}")
            return QPixmap()

    def _decode_xpr_image(self, data: bytes) -> Tuple[int, int, List["RGBA"]]:
        """
        Decode an XPR (Xbox Packed Resource) image
        """
        hdr = XprImageHeader.from_buffer_copy(data, 0)

        assert hdr.magic == 0x30525058, "Invalid header magic"

        # Some XPR files don't have the standard 0xFFFFFFFF end-of-header marker
        # Print a warning but continue processing
        if hdr.eoh != 0xFFFFFFFF:
            print(
                f"[WARNING] Non-standard end-of-header: 0x{hdr.eoh:08X} (expected 0xFFFFFFFF)"
            )

        # Some XPR files have size mismatches, so make this less strict
        if hdr.total_size != len(data):
            print(
                f"[WARNING] Size mismatch: header says {hdr.total_size}, actual {len(data)}"
            )

        format_id = self._get_bits(hdr.format, 15, 8)
        dimensionality = self._get_bits(hdr.format, 7, 4)

        assert dimensionality == 2, f"Dimensionality is not 2D (got {dimensionality})"

        w = 1 << self._get_bits(hdr.format, 23, 20)
        h = 1 << self._get_bits(hdr.format, 27, 24)

        image_data = data[hdr.header_size :]

        # Decode based on format
        if format_id == 0x0C:  # DXT1
            pixels = self._decode_bc1(w, h, image_data)
        elif format_id == 0x06:  # A8R8G8B8
            pixels = self._decode_a8r8g8b8(w, h, image_data)
        elif format_id == 0x07:  # X8R8G8B8
            pixels = self._decode_x8r8g8b8(w, h, image_data)
        elif format_id == 0x05:  # R5G6B5
            pixels = self._decode_r5g6b5(w, h, image_data)
        elif format_id == 0x02:  # A1R5G5B5
            pixels = self._decode_a1r5g5b5(w, h, image_data)
        elif format_id == 0x03:  # X1R5G5B5
            pixels = self._decode_x1r5g5b5(w, h, image_data)
        elif format_id == 0x04:  # A4R4G4B4
            pixels = self._decode_a4r4g4b4(w, h, image_data)
        elif format_id == 0x19:  # A8
            pixels = self._decode_a8(w, h, image_data)
        elif format_id == 0x3A:  # A8B8G8R8
            pixels = self._decode_a8b8g8r8(w, h, image_data)
        elif format_id == 0x0E:  # DXT3
            pixels = self._decode_bc2(w, h, image_data)
        elif format_id == 0x0F:  # DXT5
            pixels = self._decode_bc3(w, h, image_data)
        else:
            raise NotImplementedError(f"Unsupported texture format: 0x{format_id:02X}")

        return (w, h, pixels)

    def _decode_a8r8g8b8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode A8R8G8B8 format (32-bit ARGB)"""
        expected_size = w * h * 4
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        # First read the swizzled data into a temporary array
        swizzled_pixels = []
        for i in range(0, expected_size, 4):
            if i + 3 < len(data):
                b, g, r, a = struct.unpack("<BBBB", data[i : i + 4])
                swizzled_pixels.append((r / 255.0, g / 255.0, b / 255.0, a / 255.0))

        # Deswizzle to linear format
        return self._deswizzle_pixels(swizzled_pixels, w, h)

    def _decode_x8r8g8b8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode X8R8G8B8 format (32-bit RGB with unused alpha)"""
        expected_size = w * h * 4
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        # First read the swizzled data into a temporary array
        swizzled_pixels = []
        for i in range(0, expected_size, 4):
            if i + 3 < len(data):
                b, g, r, _ = struct.unpack("<BBBB", data[i : i + 4])
                swizzled_pixels.append((r / 255.0, g / 255.0, b / 255.0, 1.0))

        # Deswizzle to linear format
        return self._deswizzle_pixels(swizzled_pixels, w, h)

    def _decode_r5g6b5(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode R5G6B5 format (16-bit RGB)"""
        expected_size = w * h * 2
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        swizzled_pixels = []
        for i in range(0, expected_size, 2):
            if i + 1 < len(data):
                value = struct.unpack("<H", data[i : i + 2])[0]
                swizzled_pixels.append(self._unpack_r5g6b5(value))

        return self._deswizzle_pixels(swizzled_pixels, w, h)

    def _deswizzle_pixels(
        self, swizzled_pixels: List["RGBA"], width: int, height: int
    ) -> List["RGBA"]:
        """
        Convert Xbox swizzled texture format to linear format
        Xbox uses a recursive Z-order (Morton order) swizzling pattern
        """
        if not swizzled_pixels or len(swizzled_pixels) != width * height:
            return swizzled_pixels

        linear_pixels = [(0.0, 0.0, 0.0, 0.0)] * (width * height)

        def swizzle_2d(x: int, y: int, width: int, height: int) -> int:
            """Calculate swizzled index for given x,y coordinate"""
            # Find the size of the smallest power-of-2 square that contains the image
            max_dim = max(width, height)
            log_size = 0
            size = 1
            while size < max_dim:
                size <<= 1
                log_size += 1

            # Swizzle within that square
            swizzled_idx = 0
            for i in range(log_size):
                bit = 1 << i
                if x & bit:
                    swizzled_idx |= bit << i
                if y & bit:
                    swizzled_idx |= bit << (i + 1)

            return swizzled_idx

        # Convert from swizzled to linear
        for y in range(height):
            for x in range(width):
                swizzled_idx = swizzle_2d(x, y, width, height)
                linear_idx = y * width + x

                # Bounds check to prevent crashes
                if swizzled_idx < len(swizzled_pixels):
                    linear_pixels[linear_idx] = swizzled_pixels[swizzled_idx]

        return linear_pixels

    def _decode_a1r5g5b5(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode A1R5G5B5 format (16-bit ARGB with 1-bit alpha)"""
        pixels: List[RGBA] = []
        expected_size = w * h * 2
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                value = struct.unpack("<H", data[i : i + 2])[0]
                a = self._get_bits(value, 15, 15)
                r = self._get_bits(value, 14, 10)
                g = self._get_bits(value, 9, 5)
                b = self._get_bits(value, 4, 0)
                pixels.append((r / 31.0, g / 31.0, b / 31.0, float(a)))

        return pixels

    def _decode_dds_image(self, data: bytes) -> Tuple[int, int, List["RGBA"]]:
        """
        Decode a DDS (DirectDraw Surface) image
        """

        # DDS header is 128 bytes total (4 byte magic + 124 byte DDS_HEADER)
        if len(data) < 128:
            raise ValueError("DDS data too small for header")

        # Parse basic DDS header fields we need
        magic = struct.unpack("<I", data[0:4])[0]
        assert magic == 0x20534444, f"Invalid DDS magic: 0x{magic:08X}"

        # DDS_HEADER structure (starting at offset 4)
        # size = struct.unpack("<I", data[4:8])[0]  # Should be 124
        # flags = struct.unpack("<I", data[8:12])[0]
        height = struct.unpack("<I", data[12:16])[0]
        width = struct.unpack("<I", data[16:20])[0]
        # pitch_or_linear_size = struct.unpack("<I", data[20:24])[0]
        # depth = struct.unpack("<I", data[24:28])[0]
        # mip_map_count = struct.unpack("<I", data[28:32])[0]

        # Skip reserved fields (44 bytes from offset 32-75)

        # DDS_PIXELFORMAT structure (32 bytes starting at offset 76)
        # pf_size = struct.unpack("<I", data[76:80])[0]  # Should be 32
        # pf_flags = struct.unpack("<I", data[80:84])[0]
        pf_fourcc = struct.unpack("<I", data[84:88])[0]
        pf_rgb_bit_count = struct.unpack("<I", data[88:92])[0]
        pf_r_bit_mask = struct.unpack("<I", data[92:96])[0]
        pf_g_bit_mask = struct.unpack("<I", data[96:100])[0]
        pf_b_bit_mask = struct.unpack("<I", data[100:104])[0]
        pf_a_bit_mask = struct.unpack("<I", data[104:108])[0]

        # Skip caps and reserved fields (20 bytes from offset 108-127)

        # Image data starts after header
        image_data = data[128:]

        # Determine format and decode
        if pf_fourcc == 0x31545844:  # 'DXT1'
            pixels = self._decode_bc1(width, height, image_data)
        elif pf_fourcc == 0x33545844:  # 'DXT3'
            pixels = self._decode_bc2(width, height, image_data)
        elif pf_fourcc == 0x35545844:  # 'DXT5'
            pixels = self._decode_bc3(width, height, image_data)
        elif pf_fourcc == 0:  # Uncompressed format
            if pf_rgb_bit_count == 32:
                # Determine format based on bit masks
                if (
                    pf_r_bit_mask == 0x00FF0000
                    and pf_g_bit_mask == 0x0000FF00
                    and pf_b_bit_mask == 0x000000FF
                    and pf_a_bit_mask == 0xFF000000
                ):
                    # A8R8G8B8 format
                    pixels = self._decode_dds_a8r8g8b8(width, height, image_data)
                elif (
                    pf_r_bit_mask == 0x00FF0000
                    and pf_g_bit_mask == 0x0000FF00
                    and pf_b_bit_mask == 0x000000FF
                    and pf_a_bit_mask == 0x00000000
                ):
                    # X8R8G8B8 format
                    pixels = self._decode_dds_x8r8g8b8(width, height, image_data)
                else:
                    raise NotImplementedError(
                        f"Unsupported 32-bit DDS format with masks R=0x{pf_r_bit_mask:08X} G=0x{pf_g_bit_mask:08X} B=0x{pf_b_bit_mask:08X} A=0x{pf_a_bit_mask:08X}"
                    )
            elif pf_rgb_bit_count == 16:
                if (
                    pf_r_bit_mask == 0xF800
                    and pf_g_bit_mask == 0x07E0
                    and pf_b_bit_mask == 0x001F
                ):
                    # R5G6B5 format
                    pixels = self._decode_dds_r5g6b5(width, height, image_data)
                else:
                    raise NotImplementedError(
                        f"Unsupported 16-bit DDS format with masks R=0x{pf_r_bit_mask:08X} G=0x{pf_g_bit_mask:08X} B=0x{pf_b_bit_mask:08X}"
                    )
            else:
                raise NotImplementedError(
                    f"Unsupported DDS RGB bit count: {pf_rgb_bit_count}"
                )
        else:
            fourcc_str = struct.pack("<I", pf_fourcc).decode("ascii", errors="replace")
            raise NotImplementedError(
                f"Unsupported DDS fourcc: {fourcc_str} (0x{pf_fourcc:08X})"
            )

        return (width, height, pixels)

    def _decode_dds_a8r8g8b8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode DDS A8R8G8B8 format (32-bit ARGB) - linear format, no swizzling"""
        expected_size = w * h * 4
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        pixels = []
        for i in range(0, expected_size, 4):
            if i + 3 < len(data):
                b, g, r, a = struct.unpack("<BBBB", data[i : i + 4])
                pixels.append((r / 255.0, g / 255.0, b / 255.0, a / 255.0))

        return pixels

    def _decode_dds_x8r8g8b8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode DDS X8R8G8B8 format (32-bit RGB) - linear format, no swizzling"""
        expected_size = w * h * 4
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        pixels = []
        for i in range(0, expected_size, 4):
            if i + 3 < len(data):
                b, g, r, _ = struct.unpack("<BBBB", data[i : i + 4])
                pixels.append((r / 255.0, g / 255.0, b / 255.0, 1.0))

        return pixels

    def _decode_dds_r5g6b5(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode DDS R5G6B5 format (16-bit RGB) - linear format, no swizzling"""
        expected_size = w * h * 2
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        pixels = []
        for i in range(0, expected_size, 2):
            if i + 1 < len(data):
                value = struct.unpack("<H", data[i : i + 2])[0]
                pixels.append(self._unpack_r5g6b5(value))

        return pixels

    def _decode_x1r5g5b5(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode X1R5G5B5 format (16-bit RGB with unused bit)"""
        pixels: List[RGBA] = []
        expected_size = w * h * 2
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                value = struct.unpack("<H", data[i : i + 2])[0]
                r = self._get_bits(value, 14, 10)
                g = self._get_bits(value, 9, 5)
                b = self._get_bits(value, 4, 0)
                pixels.append((r / 31.0, g / 31.0, b / 31.0, 1.0))

        return pixels

    def _decode_a4r4g4b4(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode A4R4G4B4 format (16-bit ARGB with 4 bits per channel)"""
        pixels: List[RGBA] = []
        expected_size = w * h * 2
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                value = struct.unpack("<H", data[i : i + 2])[0]
                a = self._get_bits(value, 15, 12)
                r = self._get_bits(value, 11, 8)
                g = self._get_bits(value, 7, 4)
                b = self._get_bits(value, 3, 0)
                pixels.append((r / 15.0, g / 15.0, b / 15.0, a / 15.0))

        return pixels

    def _decode_a8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode A8 format (8-bit alpha only)"""
        pixels: List[RGBA] = []
        expected_size = w * h
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        for i in range(len(data)):
            a = data[i] / 255.0
            pixels.append((1.0, 1.0, 1.0, a))  # White with varying alpha

        return pixels

    def _decode_a8b8g8r8(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """Decode A8B8G8R8 format (32-bit ABGR)"""
        expected_size = w * h * 4
        assert (
            len(data) >= expected_size
        ), f"Not enough data: expected {expected_size}, got {len(data)}"

        swizzled_pixels = []
        for i in range(0, expected_size, 4):
            if i + 3 < len(data):
                r, g, b, a = struct.unpack("<BBBB", data[i : i + 4])
                swizzled_pixels.append((r / 255.0, g / 255.0, b / 255.0, a / 255.0))

        return self._deswizzle_pixels(swizzled_pixels, w, h)

    def _decode_bc2(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """
        Decode BC2 (DXT3) compressed image
        Similar to BC1 but with explicit 4-bit alpha
        """
        assert w % 4 == 0
        assert h % 4 == 0
        blocks_per_row = w // 4
        blocks_per_col = h // 4
        num_blocks = blocks_per_row * blocks_per_col
        num_bytes = num_blocks * 16  # 16 bytes per block for DXT3
        assert len(data) >= num_bytes
        pixels: List[RGBA] = [(0.0, 0.0, 0.0, 0.0) for _ in range(w * h)]

        for block_idx in range(num_blocks):
            block_y = (block_idx // blocks_per_row) * 4
            block_x = (block_idx % blocks_per_row) * 4
            block_data = data[(block_idx * 16) : (block_idx * 16 + 16)]

            # First 8 bytes: alpha data (4 bits per pixel)
            alpha_data = struct.unpack("<Q", block_data[0:8])[0]

            # Next 8 bytes: color data (same as DXT1)
            c0_raw, c1_raw, color_indices = struct.unpack("<HHI", block_data[8:16])
            c0, c1 = self._unpack_r5g6b5(c0_raw), self._unpack_r5g6b5(c1_raw)

            # Always use 4-color mode for DXT3
            mixed1 = self._mix(c0, c1, 1 / 3)
            mixed2 = self._mix(c0, c1, 2 / 3)
            colors = (c0, c1, mixed1, mixed2)

            for y in range(4):
                for x in range(4):
                    # Extract alpha (4 bits per pixel)
                    alpha_bit_off = (y * 4 + x) * 4
                    alpha = (
                        self._get_bits(alpha_data, alpha_bit_off + 3, alpha_bit_off)
                        / 15.0
                    )

                    # Extract color index (2 bits per pixel)
                    color_bit_off = y * 8 + x * 2
                    color_idx = self._get_bits(
                        color_indices, color_bit_off + 1, color_bit_off
                    )

                    r, g, b, _ = colors[color_idx]
                    addr = (block_y + y) * w + (block_x + x)
                    pixels[addr] = (r, g, b, alpha)

        return pixels

    def _decode_bc3(self, w: int, h: int, data: bytes) -> List["RGBA"]:
        """
        Decode BC3 (DXT5) compressed image
        Similar to BC1 but with interpolated alpha
        """
        assert w % 4 == 0
        assert h % 4 == 0
        blocks_per_row = w // 4
        blocks_per_col = h // 4
        num_blocks = blocks_per_row * blocks_per_col
        num_bytes = num_blocks * 16  # 16 bytes per block for DXT5
        assert len(data) >= num_bytes
        pixels: List[RGBA] = [(0.0, 0.0, 0.0, 0.0) for _ in range(w * h)]

        for block_idx in range(num_blocks):
            block_y = (block_idx // blocks_per_row) * 4
            block_x = (block_idx % blocks_per_row) * 4
            block_data = data[(block_idx * 16) : (block_idx * 16 + 16)]

            # First 8 bytes: alpha data
            a0, a1 = struct.unpack("<BB", block_data[0:2])
            alpha_indices = (
                struct.unpack("<Q", block_data[0:8])[0] >> 16
            )  # Skip first 2 bytes

            # Generate alpha palette
            if a0 > a1:
                alphas = [
                    a0 / 255,
                    a1 / 255,
                    (6 * a0 + 1 * a1) / 7 / 255,
                    (5 * a0 + 2 * a1) / 7 / 255,
                    (4 * a0 + 3 * a1) / 7 / 255,
                    (3 * a0 + 4 * a1) / 7 / 255,
                    (2 * a0 + 5 * a1) / 7 / 255,
                    (1 * a0 + 6 * a1) / 7 / 255,
                ]
            else:
                alphas = [
                    a0 / 255,
                    a1 / 255,
                    (4 * a0 + 1 * a1) / 5 / 255,
                    (3 * a0 + 2 * a1) / 5 / 255,
                    (2 * a0 + 3 * a1) / 5 / 255,
                    (1 * a0 + 4 * a1) / 5 / 255,
                    0.0,
                    1.0,
                ]

            # Next 8 bytes: color data (same as DXT1)
            c0_raw, c1_raw, color_indices = struct.unpack("<HHI", block_data[8:16])
            c0, c1 = self._unpack_r5g6b5(c0_raw), self._unpack_r5g6b5(c1_raw)

            # Always use 4-color mode for DXT5
            mixed1 = self._mix(c0, c1, 1 / 3)
            mixed2 = self._mix(c0, c1, 2 / 3)
            colors = (c0, c1, mixed1, mixed2)

            for y in range(4):
                for x in range(4):
                    # Extract alpha index (3 bits per pixel)
                    alpha_bit_off = (y * 4 + x) * 3
                    alpha_idx = self._get_bits(
                        alpha_indices, alpha_bit_off + 2, alpha_bit_off
                    )
                    alpha = alphas[alpha_idx]

                    # Extract color index (2 bits per pixel)
                    color_bit_off = y * 8 + x * 2
                    color_idx = self._get_bits(
                        color_indices, color_bit_off + 1, color_bit_off
                    )

                    r, g, b, _ = colors[color_idx]
                    addr = (block_y + y) * w + (block_x + x)
                    pixels[addr] = (r, g, b, alpha)

        return pixels


class XprImageHeader(ctypes.LittleEndianStructure, StructurePrintMixin):
    """
    XPR Image Header structure
    """

    _pack_ = 1
    _fields_ = [
        # XPR Header
        ("magic", ctypes.c_uint32),  # XPR0
        ("total_size", ctypes.c_uint32),
        ("header_size", ctypes.c_uint32),
        # D3D Texture
        ("common", ctypes.c_uint32),
        ("data", ctypes.c_uint32),
        ("lock", ctypes.c_uint32),
        ("format", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("eoh", ctypes.c_uint32),  # 0xffffffff
    ]
