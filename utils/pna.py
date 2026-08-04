# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 thiliapr <thiliapr@tutanota.com>
# SPDX-Package: thiliapr/adv_to_renpy
# SPDX-PackageHomePage: https://github.com/thiliapr/adv_to_renpy

# 本文件是 thiliapr/adv_to_renpy 的一部分
# thiliapr/adv_to_renpy 是自由软件，你可以依照由自由软件基金会发布的 GNU Affero 通用公共许可证分发或修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 thiliapr/adv_to_renpy 是希望它能有用，但是并无保障，甚至连可销售和符合某个特定的目的都不保证。请参看 GNU Affero 通用公共许可证以了解详情。
# 你应该随程序获得一份 GNU Affero 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/agpl.html>。

from construct import Array, Bytes, Const, Struct, Int32sl, Int32ul, this


# 结构参考: https://github.com/regomne/chinesize/blob/master/AdvPlayer/pnaUtil/pnaUtil.go
PNAHeader = Struct(
    "signature" / Const(b"PNAP"),
    Int32ul,
    "width" / Int32ul,
    "height" / Int32ul,
    "image_count" / Int32ul
)
PNALayerMetadata = Struct(
    Int32ul,
    "frame_index" / Int32sl,
    "offset_x" / Int32sl,
    "offset_y" / Int32sl,
    "width" / Int32ul,
    "height" / Int32ul,
    Array(3, Int32ul),
    "raw_size" / Int32ul,
)
PNAFile = Struct(
    "header" / PNAHeader,
    "metadata" / Array(this.header.image_count, PNALayerMetadata),
    "images" / Array(this.header.image_count, Bytes(lambda ctx: ctx.metadata[ctx._index].raw_size))
)

