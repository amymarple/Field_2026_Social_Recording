import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from .board import identify, make_board, detect
from .io import digest, safe_input, write_json
from .models import Mesh, fit_candidate, combined_map, validate_regions
from .session import template, validate_session, board_world, transform_image
from .pipeline import select, evaluate, GroundCalibration, bev, metrics

ROOT = Path(__file__).resolve().parents[1]


def synthetic(board):
    s = template(board)
    s.update(session_id="synthetic-only", physical_board_verified=True,
             five_squares_measured_cm=[30, 30], geometry_revision="synthetic-test")
    for c in s["cameras"].values():
        c.update(image_size=[200, 200], geometry_reviewed=True, stitching_settings={"fixed": True},
                 valid_from="2026-09-09T00:00:00-04:00",
                 pixel_transform=dict(decoded_size=[200, 200], rotate_cw=0, crop_xywh=None, output_size=[200, 200]),
                 regions=[dict(id="ground", polygon_px=[[0,0],[199,0],[199,199],[0,199]], exclude_px=[], threshold="core")])
    s["placements"] = []; rows = []
    pairs = [("train", x, y) for x in (10,90,180) for y in (10,90,180)]
    pairs += [("validation", x, y) for x,y in ((40,40),(110,40),(110,110))]
    pairs += [("test", x, y) for x in (30,70,110,150) for y in (30,70,130)]
    for i,(split,x,y) in enumerate(pairs):
        pid = f"P{i}"
        s["placements"].append(dict(position_id=pid, split=split, measured_origin_cm=[x+200,y+100],
            x_axis_reference_cm=[x+272,y+100], plane_height_cm=0, plane_verified=True,
            measurement_uncertainty_cm=.5, regions={"CH01":"ground","CH02":"ground"}, zone="core", depth="mid"))
        for j,(dx,dy) in enumerate(((0,0),(3,0),(0,3))):
            rows.append(dict(channel="CH01",position_id=pid,split=split,region="ground",zone="core",depth="mid",
                corner_id=j,pixel=[x+dx,y+dy],world_cm=[x+dx+200,y+dy+100],
                method="manual_ground",local_cm=[dx,dy],frame_count=3,spread_px=0))
    return dict(schema_version=1, units="cm", session=s, session_hash=digest(s), rows=rows, observations=[])


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = identify(ROOT/"calibration.png")

    def test_board_all_ids_and_corners(self):
        self.assertEqual(self.board["dictionary"], "DICT_5X5_100")
        self.assertEqual(self.board["ids"], list(range(54)))
        self.assertEqual(self.board["reconstruction_difference_fraction"], 0)
        image = make_board(self.board).generateImage((2400,1800))
        ids, _, _ = detect(image, self.board)
        self.assertEqual(len(ids), 88)

    def test_board_tampering_fails(self):
        b = copy.deepcopy(self.board); b["square_cm"] = 60
        with self.assertRaises(ValueError):
            detect(np.zeros((100,100),np.uint8), b)

    def test_pending_session_fails(self):
        s = template(self.board)
        self.assertEqual(len(s["placements"]), 59)
        self.assertEqual(sum(p["split"] == "test" for p in s["placements"]), 12)
        with self.assertRaises(ValueError): validate_session(s)

    def test_frame_transform(self):
        img = np.arange(24,dtype=np.uint8).reshape(4,6)
        spec = dict(decoded_size=[6,4],rotate_cw=90,crop_xywh=None,output_size=[4,6])
        np.testing.assert_array_equal(transform_image(img,spec), np.rot90(img,-1))
        spec["decoded_size"]=[4,6]
        with self.assertRaises(ValueError): transform_image(img,spec)

    def test_world_direction(self):
        p=dict(measured_origin_cm=[100,100],x_axis_reference_cm=[100,172])
        np.testing.assert_allclose(board_world(p,[[6,12]]),[[88,106]])

    def test_live_and_remote_inputs_rejected(self):
        for name in ("rtsp://camera/video", "\\\\server\\file.mp4", "D:/Wiser/data/live.sqlite", "CH01_2026.mp4"):
            with self.assertRaises(ValueError): safe_input(name,video=True)

    def test_triangle_inverse_and_invalid(self):
        m=Mesh([[0,0],[10,0],[0,10]],[[100,100],[120,100],[100,130]],[[0,1,2]])
        q=np.array([[2,3],[8,8],[np.nan,0]])
        ground,valid=m.map(q)
        np.testing.assert_array_equal(valid,[True,False,False])
        back,_=m.map(ground[:1],True)
        np.testing.assert_allclose(back,q[:1])
        _,valid=combined_map([m],[[-1,100]],inverse=True)
        self.assertFalse(valid[0])

    def test_folds_and_overlaps_rejected(self):
        p=[[0,0],[10,0],[10,10],[0,10]]
        with self.assertRaises(ValueError): Mesh(p,[[100,100],[110,100],[110,110],[115,105]],[[0,1,2],[0,2,3]])
        with self.assertRaises(ValueError): Mesh(p,[[100,100],[110,100],[110,110],[100,110]],[[0,1,2],[0,1,2]])

    def test_seam_hole_not_bridged(self):
        p=np.array([[x,y] for x in (0,4,6,10) for y in (0,5,10)],float)
        r=dict(id="r", polygon_px=[[0,0],[10,0],[10,10],[0,10]],
               exclude_px=[[[4.1,-1],[5.9,-1],[5.9,11],[4.1,11]]])
        m=fit_candidate(p,p+100,np.arange(len(p)),r,[10,10],"affine_mesh")
        _,valid=m.map([[5,5],[2,2],[8,8]])
        np.testing.assert_array_equal(valid,[False,True,True])

    def test_degenerate_poly_rejected(self):
        p=np.array([[i,i] for i in range(9)])
        with self.assertRaises(ValueError):
            fit_candidate(p,p,np.arange(9),dict(id="r",polygon_px=[[0,0],[10,0],[10,10],[0,10]]),[10,10],"poly")

    def test_non_linear_tessellation_inverse(self):
        p=np.array([[x,y] for x in (10,40,70,90) for y in (10,40,70,90)],float)
        world=np.column_stack([100+p[:,0]+.002*p[:,1]**2,100+p[:,1]])
        region=dict(id="r",polygon_px=[[0,0],[100,0],[100,100],[0,100]])
        for kind in ("poly","tps"):
            m=fit_candidate(p,world,np.arange(len(p)),region,[100,100],kind,1e-4,12)
            q=np.array([[20,20],[55,55],[80,80]])
            w,ok=m.map(q); back,bok=m.map(w,True)
            self.assertTrue(ok.all() and bok.all())
            np.testing.assert_allclose(back,q,atol=1e-8)

    def test_duplicate_split_and_height_rejected(self):
        s=synthetic(self.board)["session"]
        s["placements"][10]["measured_origin_cm"]=s["placements"][0]["measured_origin_cm"]
        with self.assertRaises(ValueError): validate_session(s)
        s=synthetic(self.board)["session"]; s["placements"][0]["plane_height_cm"]=5
        with self.assertRaises(ValueError): validate_session(s)

    def test_full_select_evaluate_and_scaling(self):
        d=synthetic(self.board)
        model=select(d,"CH01")
        self.assertEqual(model["meshes"][0]["metadata"]["kind"],"affine_mesh")
        report=evaluate(d,model)
        self.assertEqual(report["status"],"accepted")
        self.assertLess(report["rmse_cm"],1e-8)
        # Selection ignores final-test target values.
        altered=copy.deepcopy(d)
        for r in altered["rows"]:
            if r["split"]=="test": r["pixel"][0]+=40
        failed_model=select(altered,"CH01")
        self.assertEqual(failed_model["meshes"],model["meshes"])
        self.assertEqual(evaluate(altered,failed_model)["status"],"failed")
        model["status"]="accepted"; model.pop("artifact_hash")
        model["artifact_hash"]=digest(model)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"CH01_calib.json"; write_json(path,model)
            c=GroundCalibration(path)
            ts="2026-09-09T12:00:00-04:00"
            p=np.array([[50.,50.]])
            a=c.to_field(p,timestamp=ts,pixel_transform=model["pixel_transform"])
            b=c.to_field((p+.5)/2-.5,src_size=[100,100],timestamp=ts,pixel_transform=model["pixel_transform"])
            np.testing.assert_allclose(a,b)
            with self.assertRaises(ValueError): c.to_field(p,timestamp="2026-06-01T00:00:00-04:00",pixel_transform=model["pixel_transform"])
            with self.assertRaises(ValueError): c.to_field(p,timestamp=ts,pixel_transform={})
            output,score=bev(model,np.zeros((200,200,3),np.uint8),10)
            self.assertEqual(output.shape,(61,122,4))
            self.assertTrue((output[:,:,3]==0).any())

    def test_analysis_adapter_preserves_legacy(self):
        source_path=ROOT.parent/"Field_2026_Social"/"preprocessing"/"computer_vision"/"field_coords.py"
        if not source_path.exists():
            self.skipTest("Optional neighbouring analysis checkout not present")
        from .install_analysis_adapter import adapt
        text=source_path.read_text(encoding="utf-8-sig")
        if "ground_mesh_v1 adapter" not in text:
            text=adapt(text)
        namespace={"__file__":str(source_path),"__name__":"adapter_test"}
        exec(compile(text,str(source_path),"exec"),namespace)
        old=dict(channel="CH03",type="homography",forward=np.eye(3),inverse=np.eye(3),image_size=None)
        q=np.array([[5.,6.]])
        np.testing.assert_allclose(namespace["to_field"]("CH03",q,calib=old),q)
        np.testing.assert_allclose(namespace["to_pixel"]("CH03",q,calib=old),q)
        class Fake:
            def to_field(self,p,**kw):
                if kw["timestamp"]!="2026": raise ValueError("epoch")
                return np.array(p)+1
            def to_pixel(self,p,**kw): return np.array(p)-1
        new=dict(channel="CH01",type="ground_mesh_v1",ground=Fake())
        np.testing.assert_allclose(namespace["to_field"]("CH01",q,calib=new,timestamp="2026"),q+1)
        with self.assertRaises(ValueError): namespace["to_field"]("CH01",q,calib=new)

    def test_assemble_manual_and_split_guards(self):
        from .session import assemble
        s=synthetic(self.board)["session"]
        obs=dict(channel="CH01",position_id="P0",method="manual_ground",reviewed=True,
            board_hash=self.board["board_hash"],pixel_transform=s["cameras"]["CH01"]["pixel_transform"],
            source=dict(sha256="synthetic-frame",frame_pts_s=1),
            points=[dict(id="cross",pixel=[20,20],local_cm=[0,0])])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"obs.json"; write_json(path,obs)
            d=assemble(s,[path]); self.assertEqual(len(d["rows"]),1)
            np.testing.assert_allclose(d["rows"][0]["world_cm"],[210,110])
            with self.assertRaises(ValueError): assemble(s,[path,path])
            obs["reviewed"]=False; other=Path(tmp)/"unreviewed.json"; write_json(other,obs)
            with self.assertRaises(ValueError): assemble(s,[other])


if __name__ == "__main__":
    unittest.main()
