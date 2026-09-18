"""End-to-end CLI exercise with SYNTHETIC input only, in a temporary folder."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from .board import identify
from .io import write_json, read_json
from .test_calibration import synthetic, ROOT


class CLITests(unittest.TestCase):
    def test_offline_pipeline(self):
        def run(*args, code=0):
            result=subprocess.run([sys.executable,"-m","camera_ground",*map(str,args)],
                                   cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,code,result.stdout+result.stderr)
        with tempfile.TemporaryDirectory(prefix="ground_synthetic_") as directory:
            out=Path(directory)
            data=synthetic(identify(ROOT/"calibration.png"))
            more=copy.deepcopy(data["rows"])
            for row in more: row["channel"]="CH02"
            data["rows"].extend(more)
            dataset=out/"dataset.json"; write_json(dataset,data)
            image=out/"reference.png"
            cv2.imwrite(str(image),np.full((200,200,3),(70,110,150),np.uint8))
            for ch in ("CH01","CH02"):
                run("fit","--dataset",dataset,"--channel",ch,"--out",out/f"{ch}_fit")
                model=out/f"{ch}_fit"/f"{ch}_calib.json"
                run("bev","--model",model,"--image",image,"--timestamp","2026-09-09T12:00:00-04:00",
                    "--out",out/f"{ch}_rejected_bev",code=2)
                run("evaluate","--dataset",dataset,"--model",model,"--out",out/f"{ch}_test")
                self.assertEqual(read_json(out/f"{ch}_test"/"test_report.json")["status"],"accepted")
                run("evaluate","--dataset",dataset,"--model",model,"--out",out/f"{ch}_repeat",code=2)
                run("fit","--dataset",dataset,"--channel",ch,"--out",out/f"{ch}_refit",code=2)
                run("bev","--model",out/f"{ch}_test"/f"{ch}_calib.json","--image",image,
                    "--timestamp","2026-09-09T12:00:00-04:00","--cm-per-pixel",10,"--out",out/f"{ch}_bev")
            run("combine","--inputs",out/"CH01_bev",out/"CH02_bev","--out",out/"combined")
            labels=cv2.imread(str(out/"combined"/"source_channel.png"),cv2.IMREAD_GRAYSCALE)
            self.assertEqual(set(np.unique(labels)),{0,1})
            run("compare","--dataset",dataset,"--models",out/"CH01_test"/"CH01_calib.json",
                out/"CH02_test"/"CH02_calib.json","--out",out/"agreement")
            self.assertEqual(len(read_json(out/"agreement"/"camera_agreement.json")["positions"]),12)
            # Exercise bounded video extraction, including PTS, on a generated closed segment.
            video=out/"CH01_2026-09-09_12-00-00_to_12-00-05.mp4"
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"mp4v"),10,(64,64))
            self.assertTrue(writer.isOpened())
            for i in range(50): writer.write(np.full((64,64,3),i*4,np.uint8))
            writer.release()
            run("extract","--src",video,"--start",1,"--window",.4,"--count",3,"--out",out/"frames")
            self.assertEqual(len(read_json(out/"frames"/"extraction.json")["frames"]),3)


if __name__ == "__main__":
    unittest.main()
