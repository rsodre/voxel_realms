from struct import pack


class VoxWriter(object):

    def __init__(self, filename, vox):
        self.filename = filename
        self.vox = vox

    def _chunk(self, id, content, chunks=[]):

        res = b''
        for c in chunks:
            res += self._chunk(*c)

        return pack('4sii', id, len(content), len(res)) + content + res

    def write(self):

        res = pack('4si', b'VOX ', 150)

        chunks = []

        # print([k for k in self.vox.__dict__])
        # print(self.vox.default_palette)

        if len(self.vox.models):
            # print(f"writing {len(self.vox.models)} models")
            chunks.append((b'PACK', pack('i', len(self.vox.models))))

        for m in self.vox.models:
            chunks.append((b'SIZE', pack('iii', *m.size)))
            chunks.append((b'XYZI', pack('i', len(m.voxels)) + b''.join(pack('BBBB', *v) for v in m.voxels)))

        if not self.vox.default_palette:
            chunks.append((b'RGBA', b''.join(pack('BBBB', *c) for c in self.vox.palette)))

        for m in self.vox.materials:
            chunks.append((b'MATL', b''.join([m.bid, m.btype, m.content])))

        for r in self.vox.remnants:
            chunks.append((r.id, r.content))

        res += self._chunk(b'MAIN', b'', chunks)

        with open(self.filename, 'wb') as f:
            f.write(res)
