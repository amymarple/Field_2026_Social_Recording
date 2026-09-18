"""Validated piecewise-linear deployment meshes, including tessellated poly/TPS.

All deployed forward and inverse operations use the SAME mesh. Nonlinear
candidates are explicitly tessellated, not advertised as exact smooth inverses.
"""
import numpy as np
from scipy.spatial import Delaunay
from scipy.interpolate import RBFInterpolator
from shapely import Polygon, MultiPoint, STRtree, points, union_all

FIELD_SIZE = np.array([1219.2, 609.6])


def features(p):
    x, y = np.asarray(p).T
    return np.column_stack([np.ones(len(x)), x, y, x*x, x*y, y*y])


def signed_area(p):
    a, b = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    return a[:, 0]*b[:, 1] - a[:, 1]*b[:, 0]


def valid_polygon(vertices):
    p = Polygon(vertices)
    if not p.is_valid or p.area <= 1e-9:
        raise ValueError("Invalid or degenerate region polygon")
    return p


class Mesh:
    def __init__(self, vertices_px, vertices_cm, triangles, metadata=None):
        self.px = np.asarray(vertices_px, float)
        self.cm = np.asarray(vertices_cm, float)
        self.tri = np.asarray(triangles, int)
        self.metadata = metadata or {}
        if (self.px.ndim != 2 or self.px.shape[1] != 2 or self.cm.shape != self.px.shape
                or not len(self.tri) or self.tri.ndim != 2 or self.tri.shape[1] != 3
                or not np.isfinite(self.px).all() or not np.isfinite(self.cm).all()):
            raise ValueError("Invalid mesh")
        if self.tri.min() < 0 or self.tri.max() >= len(self.px):
            raise ValueError("Triangle index out of bounds")
        source, dest = self.px[self.tri], self.cm[self.tri]
        a, b = signed_area(source), signed_area(dest)
        if np.any(abs(a) < 1e-9) or np.any(abs(b) < 1e-9) or len(np.unique(np.sign(a*b))) != 1:
            raise ValueError("Folded or degenerate mesh")
        self._src = np.array([Polygon(t) for t in source], dtype=object)
        self._dst = np.array([Polygon(t) for t in dest], dtype=object)
        self._trees = [STRtree(self._src), STRtree(self._dst)]
        # Exact triangle-overlap check, not merely a sampled Jacobian sign test.
        for polys, tree in zip((self._src, self._dst), self._trees):
            pairs = tree.query(polys, predicate="intersects")
            for i, j in pairs[:, pairs[0] < pairs[1]].T:
                if polys[i].intersection(polys[j]).area > 1e-7:
                    raise ValueError("Overlapping mesh triangles: ambiguous inverse")

    def map(self, query, inverse=False):
        q = np.asarray(query, float).reshape(-1, 2)
        out = np.full(q.shape, np.nan)
        good = np.flatnonzero(np.isfinite(q).all(axis=1))
        if not len(good):
            return out, np.zeros(len(q), bool)
        index = self._trees[int(inverse)].query(points(q[good]), predicate="intersects")
        if index.shape[1]:
            # Points on shared boundaries have the same mapping by construction.
            _, first = np.unique(index[0], return_index=True)
            qi, ti = good[index[0, first]], index[1, first]
            src, dst = (self.cm, self.px) if inverse else (self.px, self.cm)
            s, d = src[self.tri[ti]], dst[self.tri[ti]]
            A = np.stack([s[:, 1]-s[:, 0], s[:, 2]-s[:, 0]], axis=2)
            uv = np.linalg.solve(A, (q[qi]-s[:, 0])[..., None])[..., 0]
            out[qi] = d[:, 0] + uv[:, :1]*(d[:, 1]-d[:, 0]) + uv[:, 1:]*(d[:, 2]-d[:, 0])
        valid = np.isfinite(out).all(axis=1)
        if not inverse:
            valid &= ((out >= 0) & (out <= FIELD_SIZE)).all(axis=1)
            out[~valid] = np.nan
        return out, valid

    def as_dict(self):
        return dict(vertices_px=self.px.tolist(), vertices_cm=self.cm.tolist(),
                    triangles=self.tri.tolist(), metadata=self.metadata)

    @classmethod
    def from_dict(cls, spec):
        return cls(spec["vertices_px"], spec["vertices_cm"], spec["triangles"], spec.get("metadata"))


def evenly_select(p, count=16):
    """Deterministic farthest-point subset, used only for TPS kernel centres."""
    if len(p) <= count:
        return np.arange(len(p))
    chosen = [int(np.argmin(p[:, 0] + p[:, 1]))]
    distance = np.full(len(p), np.inf)
    while len(chosen) < count:
        distance = np.minimum(distance, ((p-p[chosen[-1]])**2).sum(axis=1))
        chosen.append(int(np.argmax(distance)))
    return np.array(chosen)


def fit_candidate(px, cm, groups, region, image_size, kind, smoothing=0.0, mesh_steps=45):
    px, cm, groups = np.asarray(px, float), np.asarray(cm, float), np.asarray(groups)
    size = np.asarray(image_size, float)
    u, v = px/size, cm/FIELD_SIZE
    if len(np.unique(u, axis=0)) != len(u):
        raise ValueError("Duplicate image control points; aggregate repeated captures first")
    if len(u) < 6 or np.linalg.matrix_rank(u-u.mean(axis=0)) < 2:
        raise ValueError("Insufficient/collinear training points")
    domain = valid_polygon(region["polygon_px"]).intersection(MultiPoint(px).convex_hull)
    for hole in region.get("exclude_px", []):
        domain = domain.difference(valid_polygon(hole))
    if domain.is_empty:
        raise ValueError("Empty valid domain")
    _, counts = np.unique(groups, return_counts=True)
    weights = np.array([1/np.sum(groups == g) for g in groups])
    if kind == "poly":
        F = features(u)
        if np.linalg.matrix_rank(F) < 6:
            raise ValueError("Rank-deficient polynomial design")
        coeff = np.linalg.lstsq(F*np.sqrt(weights[:, None]), v*np.sqrt(weights[:, None]), rcond=None)[0]
        evaluate = lambda z: features(z) @ coeff
    elif kind == "tps":
        # Equal placement contribution; limit kernel centres for bounded resources.
        subset = np.concatenate([np.flatnonzero(groups == g)[evenly_select(u[groups == g])]
                                 for g in np.unique(groups)])
        su, sv, sg = u[subset], v[subset], groups[subset]
        penalties = np.array([smoothing*np.sum(sg == g) for g in sg])
        rbf = RBFInterpolator(su, sv, kernel="thin_plate_spline", degree=1, smoothing=penalties)
        evaluate = rbf
    elif kind != "affine_mesh":
        raise ValueError("Unknown model")
    if kind == "affine_mesh":
        vertices, mapped = px, cm
    else:
        lo, hi = px.min(axis=0), px.max(axis=0)
        gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], mesh_steps),
                             np.linspace(lo[1], hi[1], mesh_steps))
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        grid = grid[np.array([domain.covers(p) for p in points(grid)])]
        vertices = np.unique(np.vstack([px, grid]), axis=0)
        mapped = evaluate(vertices/size)*FIELD_SIZE
    tri = Delaunay(vertices/size).simplices
    tri = np.array([t for t in tri if domain.covers(Polygon(vertices[t]))], int)
    if not len(tri):
        raise ValueError("No complete triangle inside domain")
    mesh = Mesh(vertices, mapped, tri, dict(kind=kind, smoothing=smoothing,
                mesh_steps=mesh_steps, representation="exact piecewise-affine deployment mesh",
                region=region["id"], training_positions=len(counts)))
    if kind != "affine_mesh":
        centers = vertices[tri].mean(axis=1)
        approximated, ok = mesh.map(centers)
        delta = np.linalg.norm(approximated-evaluate(centers/size)*FIELD_SIZE, axis=1)
        if not ok.all() or float(delta.max()) > .5:
            if mesh_steps < 90:
                return fit_candidate(px, cm, groups, region, image_size, kind, smoothing, 90)
            raise ValueError("Nonlinear tessellation error >0.5 cm or out-of-field mesh")
        mesh.metadata["sampled_tessellation_max_cm"] = float(delta.max())
    return mesh


def combined_map(meshes, query, inverse=False):
    query = np.asarray(query, float).reshape(-1, 2)
    result, hits = np.full(query.shape, np.nan), np.zeros(len(query), int)
    for mesh in meshes:
        mapped, valid = mesh.map(query, inverse)
        result[valid] = mapped[valid]
        hits += valid.astype(int)
    valid = hits == 1
    if inverse:
        valid &= ((query >= 0) & (query <= FIELD_SIZE)).all(axis=1)
    result[~valid] = np.nan
    return result, valid


def validate_regions(meshes):
    for i, a in enumerate(meshes):
        for b in meshes[i+1:]:
            for attr in ("_src", "_dst"):
                if union_all(getattr(a, attr)).intersection(union_all(getattr(b, attr))).area > 1e-7:
                    raise ValueError("Regions overlap in source or ground space; adjust masks")
