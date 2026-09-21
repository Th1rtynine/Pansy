"""封面:认上传的文件、起名字、写到 `data/covers/` 下。

作品 `edition`、卷 `volume`、总标题 `work` 三种封面规矩一样,只有文件名分得出来(见 `KIND_*`)。
**先写文件再改数据库**(失败宁可多一个没人引用的文件)、**不覆盖旧文件**(换一张写 `edition-1.v2.jpg`)。
**删记录才删文件**:摘掉或更换只动那一列,按文件名 `edition-16.*` 认,只删程序自己写进 `data/covers/` 的。
"""

from dataclasses import dataclass
from pathlib import Path

from app.config import load_paths

#: 一张封面上限 8 MB(手机拍的照片也就两三兆)。
MAX_BYTES = 8 * 1024 * 1024

#: 靠文件头区分的三种;webp 没有固定前缀,在 `sniff()` 里单独判。
HEADERS = (
    ("jpg", (b"\xff\xd8\xff",)),
    ("png", (b"\x89PNG\r\n\x1a\n",)),
    ("gif", (b"GIF87a", b"GIF89a")),
)

#: JPEG 带尺寸的段 SOF0–SOF15,去掉不是 SOF 的 DHT(C4)、JPG(C8)、DAC(CC)。
JPEG_SIZE_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}

REFUSAL_TOO_BIG = "封面不能超过 8 MB。"
REFUSAL_NOT_IMAGE = "封面只收 JPEG、PNG、WebP 或 GIF 图片。"

#: 封面挂在哪一种记录上,同时是文件名的前缀(`edition-1.jpg`):闭集,多一种要一起想文件名与清理。
KIND_EDITION = "edition"
KIND_VOLUME = "volume"
#: 作品总标题自己的封面,文件名因此是 `work-3.jpg`。
KIND_WORK = "work"


class CoverRefused(Exception):
    """这张封面不收,理由就是这句话 —— 由接口原样交给调用方(400)。"""


@dataclass(frozen=True)
class SavedCover:
    """一张刚落盘的封面:存在哪(相对数据目录)、原图多大 —— 文件头被截断时尺寸是 None。"""

    path: str
    width: int | None
    height: int | None


def sniff(data: bytes) -> str | None:
    """这个文件是什么格式,按它开头那几个字节判断。认不出来就是 None。"""
    for extension, headers in HEADERS:
        if any(data.startswith(header) for header in headers):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def read_size(data: bytes) -> tuple[int, int] | None:
    """这张图多少像素,只读文件头,不解码像素。读不出来就是 None。"""
    extension = sniff(data)
    if extension == "png":
        return _png_size(data)
    if extension == "gif":
        return _gif_size(data)
    if extension == "jpg":
        return _jpeg_size(data)
    if extension == "webp":
        return _webp_size(data)
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    """IHDR 必须是最前面那个块:宽高各 4 字节,大端。"""
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _gif_size(data: bytes) -> tuple[int, int] | None:
    """逻辑屏幕描述符紧跟在 6 字节签名 + 3 字节版本后面,两个小端 16 位。"""
    if len(data) < 10:
        return None
    return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    """顺着段表走,遇到 SOF 就读尺寸 —— 每个段的长度写在段里,所以走得动。"""
    index = 2
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        # 没有长度字段的段:填充、RST、以及文件头的 SOI
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            index += 2
            continue
        if marker == 0xD9:  # EOI,图都走完了还没有 SOF
            return None
        length = int.from_bytes(data[index + 2:index + 4], "big")
        if length < 2:
            return None
        if marker in JPEG_SIZE_MARKERS:
            if index + 9 > len(data):
                return None
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return width, height
        index += 2 + length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    """WebP 三种开头:扩展(VP8X)、有损(VP8 )、无损(VP8L)。"""
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        # 24 位,存的是「减一」的值
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":  # 关键帧起始码,不在就不是我们认的那个布局
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L":
        if data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def covers_dir() -> Path:
    """封面放哪。目录不存在就建一个 —— 数据目录可能是刚搬过来的。"""
    directory = load_paths().covers_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def next_name(kind: str, row_id: int, extension: str) -> str:
    """这一条记录下一个可用的文件名:第一次 `edition-1.jpg`,换一张 `edition-1.v2.jpg`,
    **版本号从硬盘上现有的文件数出来,不存数据库**。
    """
    taken = {path.name for path in covers_dir().glob(f"{kind}-{row_id}.*")}
    plain = f"{kind}-{row_id}.{extension}"
    if plain not in taken:
        return plain
    version = 2
    while f"{kind}-{row_id}.v{version}.{extension}" in taken:
        version += 1
    return f"{kind}-{row_id}.v{version}.{extension}"


def save_cover(kind: str, row_id: int, data: bytes) -> SavedCover:
    """把一张封面写到硬盘上,连同尺寸一起交回去;路径是**相对数据目录**的,`kind` 只决定文件名。
    """
    if len(data) > MAX_BYTES:
        raise CoverRefused(REFUSAL_TOO_BIG)
    extension = sniff(data)
    if extension is None:
        raise CoverRefused(REFUSAL_NOT_IMAGE)

    name = next_name(kind, row_id, extension)
    (covers_dir() / name).write_bytes(data)
    size = read_size(data)
    return SavedCover(
        path=f"covers/{name}",
        width=size[0] if size else None,
        height=size[1] if size else None,
    )


def url_of(cover_path: str | None) -> str | None:
    """库里相对数据目录的那一列(`covers/edition-1.jpg`)变成 `/covers/...` —— **前缀与
    `app/main.py` 挂的那个是一对**,所以数据目录搬走时库里的值不用改。
    """
    if not cover_path:
        return None
    return "/" + cover_path.replace("\\", "/")


def remove_row_covers(kind: str, row_id: int) -> list[str]:
    """把这一条记录名下的封面文件全删掉,回它删掉的文件名。**按文件名认**(`edition-16.*`),不看数据库
    那一列:换封面留下的旧版本、摘掉封面后没人指着的那一张,照着那一列是找不到的。只有硬删记录会走到
    这里;**删不掉不算错**(文件不在或被占着)。"""
    if kind not in (KIND_EDITION, KIND_VOLUME):
        return []
    removed = []
    for path in sorted(covers_dir().glob(f"{kind}-{row_id}.*")):
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(path.name)
    return removed
