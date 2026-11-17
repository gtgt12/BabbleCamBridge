import numpy as np
from collections import deque


class Deflicker:
    """Removes rolling-shutter bands from a strobing light whose pattern repeats every P frames.

    The bands act as a gain on the image. For each of the P phases a gain map is learned
    (full resolution along sensor rows, coarse along columns). Each frame is divided by the
    map of its phase, scaled by a per-frame strength fit, so there is no added delay."""

    def __init__(self, h, w, period=5, bx=8, beta=0.10, thr=0.08, warm=40, off=0.0):
        self.h, self.w, self.P, self.bx = h, w, period, bx
        self.off = np.float32(off)                       # camera black level
        self.cols = np.arange(0, w, w // bx)             # block starts along x
        self.beta, self.thr, self.warm = beta, thr, warm
        self.G = np.zeros((period, h, bx), np.float32)   # gain - 1 per phase
        self.hist = deque(maxlen=period)
        self.phase = 0
        self.n = 0
        self.slip = [0, 0]
        xc = (np.arange(bx) + 0.5) * (w / bx)
        x = np.arange(w) + 0.5
        M = np.zeros((bx, w), np.float32)
        for i in range(w):
            j = np.searchsorted(xc, x[i]) - 1
            if j < 0:
                M[0, i] = 1
            elif j >= bx - 1:
                M[bx - 1, i] = 1
            else:
                t = (x[i] - xc[j]) / (xc[j + 1] - xc[j])
                M[j, i] = 1 - t
                M[j + 1, i] = t
        self.M = M

    def process(self, f):
        return np.clip(self.process_f(f) + np.float32(0.5), 0, 255).astype(np.uint8)

    def process_f(self, f):
        """uint8 frame in, corrected float32 frame out."""
        ff = f.astype(np.float32)
        ff -= self.off
        rep = self.w // self.bx
        lr = np.add.reduceat(ff, self.cols, axis=1)      # (plain BLAS on the Pi is slow, so no matmul)
        lr *= np.float32(1.0 / rep)
        self.hist.append(lr)
        self.n += 1
        self.phase = (self.phase + 1) % self.P
        if len(self.hist) < self.P:
            ff += self.off
            return ff
        m5 = sum(self.hist) / self.P
        dev = lr / np.maximum(m5, 1.0) - 1.0
        if self.n > self.warm:
            # re-sync if a frame was dropped: the best matching phase wins after 3 agreeing frames
            sc = (self.G * dev[None]).sum(axis=(1, 2))
            best = int(np.argmax(sc))
            if best != self.phase and sc[best] > 1.5 * max(sc[self.phase], 0) + 1e-3:
                off = (best - self.phase) % self.P
                self.slip = [off, self.slip[1] + 1] if self.slip[0] == off else [off, 1]
                if self.slip[1] >= 3:
                    self.phase = best
                    self.slip = [0, 0]
            else:
                self.slip = [0, 0]
        T = self.G[self.phase]
        den = float((T * T).sum())
        a = float(np.clip((dev * T).sum() / den, 0.0, 2.0)) if den > 1e-4 else 0.0
        # 1/gain on the coarse grid, then linear upsampling along x (repeat + box filter)
        r = 1.0 / np.maximum(1.0 + a * T, 0.4)
        r = np.repeat(np.concatenate([r[:, :1], r, r[:, -1:]], axis=1), rep, axis=1)
        c = np.cumsum(r, axis=1, dtype=np.float32)
        s = rep // 2 - 1
        g = c[:, s + rep:s + rep + self.w] - c[:, s:s + self.w]
        g *= np.float32(1.0 / rep)
        ff *= g
        if self.n <= self.warm:
            T += 0.3 * (dev - T)
        else:
            ok = np.abs(dev - a * T) < self.thr
            T += self.beta * ok * (dev - T)
        ff += self.off
        return ff
