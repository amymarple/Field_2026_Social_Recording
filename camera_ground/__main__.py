"""python -m camera_ground --help"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import cv2
import numpy as np
from . import board
from .io import read_json, write_json, new_dir, safe_input, digest
from .session import template, assemble, observe_image, transform_image
from .pipeline import select, evaluate, load_artifact, bev, residual_svg, audit_legacy, GroundCalibration


def field_sheet(s, out):
    text = ["# CH01/CH02 现场记录表", "", "状态：待现场采集；以下坐标仅用于放样，不是实测值。", "",
            "棋盘长边72 cm沿+x，短边54 cm沿+y；原点为原图左上角。", "",
            "记录实测原点与长边第二参考点、板面高度、测量误差、起止时间；每点停稳8–10秒。",
            "锥桶仅标位置；近、中、远及接缝需补充独立测试点。", "",
            "| ID | 集合 | 计划x,y cm | 实测原点 | +x参考点 | 板面高度cm | 时间窗口/备注 |",
            "|---|---|---|---|---|---|---|"]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-55 -70 1330 740">',
           '<rect x="0" y="0" width="1219.2" height="609.6" fill="white" stroke="black"/>',
           '<text x="0" y="-35" font-size="20">PROPOSED positions: green=train, blue=validation, red=test</text>']
    for p in s["placements"]:
        x, y = p["proposed_origin_cm"]
        text.append(f'| {p["position_id"]} | {p["split"]} | {x}, {y} | | | | |')
        color = {"train": "#087f5b", "validation": "#185adb", "test": "#d22"}[p["split"]]
        svg.append(f'<rect x="{x}" y="{y}" width="72" height="54" fill="{color}" fill-opacity=".15" stroke="{color}"/>')
        svg.append(f'<text x="{x+3}" y="{y+20}" font-size="13">{p["position_id"]}</text>')
    svg.append('</svg>')
    (out/"field_sheet.md").write_text("\n".join(text)+"\n", encoding="utf-8")
    (out/"proposed_positions.svg").write_text("\n".join(svg), encoding="utf-8")


def extract(args):
    source = safe_input(args.src, video=True)
    if not 0 <= args.start or not 0 < args.window <= 30 or not 1 <= args.count <= 5:
        raise ValueError("Extraction limit: nonnegative start, <=30 seconds, <=5 frames")
    out = new_dir(args.out)
    capture = cv2.VideoCapture(str(source))
    records = []
    try:
        if not capture.isOpened():
            raise ValueError("Cannot open closed video")
        for i, offset in enumerate(np.linspace(args.start, args.start+args.window, args.count)):
            capture.set(cv2.CAP_PROP_POS_MSEC, float(offset*1000))
            ok, img = capture.read()
            pts = capture.get(cv2.CAP_PROP_POS_MSEC)/1000
            if not ok or abs(pts-offset) > 1:
                raise ValueError("Frame seek/PTS could not be verified")
            name = f"frame_{i:02d}.png"
            if not cv2.imwrite(str(out/name), img):
                raise ValueError("Image write failed")
            records.append(dict(image=name, requested_offset_s=float(offset), frame_pts_s=pts))
    finally:
        capture.release()
    write_json(out/"extraction.json", dict(source=str(source), closed_segment=True,
               source_size_bytes=source.stat().st_size, frames=records,
               note="No full-video hash/read. PTS relative to source; wall-clock requires explicit source epoch."))


def main():
    cv2.setNumThreads(1)
    parser = argparse.ArgumentParser(description="Offline CH01/CH02 calibration; no camera control")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("identify", help="Verify all markers and corners in board image")
    p.add_argument("--image", required=True); p.add_argument("--out", required=True)
    p.add_argument("--square-cm", type=float, default=6); p.add_argument("--marker-cm", type=float, default=4.5)
    p = commands.add_parser("init", help="Create pending session, 59-position sheet and map")
    p.add_argument("--board", required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("extract", help="Explicit closed local MP4: <=30s window, <=5 frames")
    p.add_argument("--src", required=True); p.add_argument("--out", required=True)
    p.add_argument("--start", type=float, required=True); p.add_argument("--window", type=float, default=8)
    p.add_argument("--count", type=int, default=5)
    p = commands.add_parser("observe", help="Detect corners and produce overlay for human review")
    p.add_argument("--session", required=True); p.add_argument("--image", required=True)
    p.add_argument("--channel", choices=["CH01", "CH02"], required=True)
    p.add_argument("--position", required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("manual", help="Create reviewed-later observation from canonical flat-marker clicks")
    p.add_argument("--session", required=True); p.add_argument("--image", required=True)
    p.add_argument("--channel", choices=["CH01", "CH02"], required=True)
    p.add_argument("--position", required=True); p.add_argument("--points", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("assemble", help="Build measured, reviewed dataset")
    p.add_argument("--session", required=True); p.add_argument("--observations", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("fit", help="Train and choose models using validation only")
    p.add_argument("--dataset", required=True); p.add_argument("--channel", choices=["CH01", "CH02"], required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("evaluate", help="Consume independent test once and publish accepted/failed artifact")
    p.add_argument("--dataset", required=True); p.add_argument("--model", required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("bev", help="Render inverse-consistent BEV (requires explicit epoch)")
    p.add_argument("--model", required=True); p.add_argument("--image", required=True)
    p.add_argument("--timestamp", required=True); p.add_argument("--out", required=True)
    p.add_argument("--cm-per-pixel", type=float, default=1)
    p.add_argument("--preview", action="store_true", help="Allow provisional model; label output as preview")
    p = commands.add_parser("combine", help="Combine accepted BEVs using local validation scores")
    p.add_argument("--inputs", nargs=2, required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("audit-legacy", help="Report old polynomial training residuals only")
    p.add_argument("--config-dir", required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("compare", help="Post-acceptance CH01/CH02 agreement on shared measured test targets")
    p.add_argument("--dataset", required=True); p.add_argument("--models", nargs=2, required=True)
    p.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "identify":
        spec = board.identify(args.image, args.square_cm, args.marker_cm)
        write_json(args.out, spec)
        print(f"Verified {spec['marker_count']} markers, {spec['corner_count']} corners; {spec['dictionary']}")
    elif args.command == "init":
        spec = read_json(args.board); board.verify_spec(spec)
        s = template(spec); out = new_dir(args.out)
        write_json(out/"session.json", s); field_sheet(s, out)
        print("Pending field capture: 35 train + 12 validation + 12 test positions")
    elif args.command == "extract":
        extract(args)
    elif args.command in ("observe", "manual"):
        s = read_json(args.session)
        if args.position not in {p["position_id"] for p in s["placements"]}:
            raise ValueError("Unknown placement")
        if args.command == "observe":
            obs, image = observe_image(args.image, s, args.channel, args.position)
        else:
            from .io import file_digest
            raw = cv2.imread(str(safe_input(args.image)))
            if raw is None:
                raise ValueError("Cannot decode image")
            transform = s["cameras"][args.channel]["pixel_transform"]
            image = transform_image(raw, transform)
            manual = read_json(args.points)
            if manual.get("units") != "cm" or manual.get("pixel_space") != "canonical":
                raise ValueError("Manual input must declare units=cm, pixel_space=canonical")
            obs = dict(channel=args.channel, position_id=args.position, method="manual_ground", reviewed=False,
                board_hash=s["board"]["board_hash"], pixel_transform=transform,
                source=dict(path=str(safe_input(args.image)), sha256=file_digest(args.image), frame_pts_s=None),
                points=manual["points"])
            for point in obs["points"]:
                at = tuple(np.rint(point["pixel"]).astype(int))
                cv2.circle(image, at, 5, (0,255,0), 2)
                cv2.putText(image,str(point["id"]),at,cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
        extraction = Path(args.image).parent/"extraction.json"
        if extraction.exists():
            info = read_json(extraction)
            record = next((f for f in info["frames"] if f["image"] == Path(args.image).name), None)
            if record:
                obs["source"].update(extraction=info, frame_pts_s=record["frame_pts_s"])
        out = new_dir(args.out); write_json(out/"observation.json", obs)
        cv2.imwrite(str(out/"corners.png"), image)
        print("Inspect corners.png, then set reviewed=true in observation.json")
    elif args.command == "assemble":
        data = assemble(read_json(args.session), args.observations)
        write_json(args.out, data)
    elif args.command == "fit":
        dataset_path = safe_input(args.dataset)
        lock = dataset_path.parent/f"test_usage_{args.channel}.json"
        if lock.exists():
            raise ValueError("Test already consumed in this session. New measured test positions/session required")
        data = read_json(dataset_path)
        model = select(data, args.channel)
        out = new_dir(args.out)
        write_json(out/f"{args.channel}_calib.json", model)
        write_json(out/"dataset_snapshot.json", data)
        residual_svg(dict(positions=model["validation_positions"]), out/"validation_residuals.svg")
        print("Model frozen; status provisional, test not used")
    elif args.command == "evaluate":
        dataset_path = safe_input(args.dataset)
        data = read_json(dataset_path); model, _ = load_artifact(args.model)
        if digest(data) != model["dataset_hash"]:
            raise ValueError("Dataset changed after model selection")
        lock = dataset_path.parent/f"test_usage_{model['channel']}.json"
        # Exclusive create protects repeated evaluations in the same session.
        write_json(lock, dict(artifact_hash=model["artifact_hash"], dataset_hash=digest(data),
                             consumed_at=datetime.now().astimezone().isoformat()))
        report = evaluate(data, model)
        out = new_dir(args.out)
        write_json(out/"test_report.json", report)
        residual_svg(report, out/"test_residuals.svg")
        model["status"] = report["status"]
        model["selection_artifact_hash"] = model.pop("artifact_hash")
        model["acceptance"] = report
        model["artifact_hash"] = digest(model)
        write_json(out/f"{model['channel']}_calib.json", model)
        print(report["status"], report["issues"])
        return 0 if report["status"] == "accepted" else 2
    elif args.command == "bev":
        c = GroundCalibration(args.model, allow_provisional=args.preview); c._epoch(args.timestamp)
        raw = cv2.imread(str(safe_input(args.image)))
        if raw is None:
            raise ValueError("Cannot decode source image")
        image = transform_image(raw, c.artifact["pixel_transform"])
        rendered, score = bev(c.artifact, image, args.cm_per_pixel)
        out = new_dir(args.out)
        cv2.imwrite(str(out/"bev.png"), rendered)
        np.savez_compressed(out/"local_score.npz", score=score)
        write_json(out/"bev.json", dict(channel=c.artifact["channel"], status=c.artifact["status"],
            artifact_hash=c.artifact["artifact_hash"], cm_per_pixel=args.cm_per_pixel,
            field_size_cm=c.artifact["field_size_cm"], timestamp=args.timestamp,
            preview=args.preview, pixel_origin="cell centres (0.5,0.5)*cm_per_pixel; x right, y down",
            score_definition="maximum RMSE of 3 nearest validation placements; ranking heuristic, not uncertainty"))
    elif args.command == "combine":
        dirs = [Path(p) for p in args.inputs]
        meta = [read_json(p/"bev.json") for p in dirs]
        if {m["channel"] for m in meta} != {"CH01", "CH02"}:
            raise ValueError("Need one CH01 and one CH02 BEV")
        if any(m["status"] != "accepted" or m["preview"] for m in meta):
            raise ValueError("Only accepted, non-preview BEVs can be combined")
        if any(meta[0][k] != meta[1][k] for k in ("cm_per_pixel", "timestamp", "field_size_cm")):
            raise ValueError("BEV scale/epoch mismatch; verify actual camera time synchronization separately")
        imgs = [cv2.imread(str(safe_input(p/"bev.png")), cv2.IMREAD_UNCHANGED) for p in dirs]
        scores = [np.load(safe_input(p/"local_score.npz"), allow_pickle=False)["score"] for p in dirs]
        if imgs[0].shape != imgs[1].shape:
            raise ValueError("BEV shape mismatch")
        out = new_dir(args.out); merged = np.zeros_like(imgs[0]); source = np.zeros(imgs[0].shape[:2], np.uint8)
        winner = np.argmin(np.stack(scores), axis=0)
        for i, img in enumerate(imgs):
            take = (winner == i) & (img[:, :, 3] > 0) & np.isfinite(scores[i])
            merged[take] = img[take]; source[take] = int(meta[i]["channel"][-2:])
        cv2.imwrite(str(out/"combined.png"), merged); cv2.imwrite(str(out/"source_channel.png"), source)
        write_json(out/"combined.json", dict(inputs=meta, source_labels={"0": "invalid", "1": "CH01", "2": "CH02"}))
    elif args.command == "audit-legacy":
        report = audit_legacy(args.config_dir, args.out)
        print({ch: r["training_rmse_cm"] for ch, r in report.items()})
    elif args.command == "compare":
        from .models import combined_map
        data = read_json(args.dataset)
        artifacts = [load_artifact(p) for p in args.models]
        if {a["channel"] for a,_ in artifacts} != {"CH01","CH02"}:
            raise ValueError("Need one accepted model for each channel")
        estimates = {}
        for a, meshes in artifacts:
            if a["status"] != "accepted" or a["dataset_hash"] != digest(data):
                raise ValueError("Models must be accepted and use this shared dataset")
            rows = [r for r in data["rows"] if r["channel"]==a["channel"] and r["split"]=="test"]
            prediction, good = combined_map(meshes,[r["pixel"] for r in rows])
            estimates[a["channel"]] = {(r["position_id"],r["corner_id"]):(pred,np.array(r["world_cm"]))
                for r,pred,ok in zip(rows,prediction,good) if ok}
        a,b=estimates["CH01"],estimates["CH02"]
        positions=[]
        common=a.keys() & b.keys()
        for pid in sorted({key[0] for key in common}):
            keys=[key for key in common if key[0]==pid]
            delta=[np.linalg.norm(a[k][0]-b[k][0]) for k in keys]
            positions.append(dict(position_id=pid,n_corners=len(keys),
                agreement_rmse_cm=float(np.sqrt(np.mean(np.square(delta)))),
                CH01_ground_rmse_cm=float(np.sqrt(np.mean([np.sum((a[k][0]-a[k][1])**2) for k in keys]))),
                CH02_ground_rmse_cm=float(np.sqrt(np.mean([np.sum((b[k][0]-b[k][1])**2) for k in keys])))))
        if not positions:
            raise ValueError("No common independent test targets")
        out=new_dir(args.out); write_json(out/"camera_agreement.json",dict(positions=positions,
            note="Camera agreement is not ground truth; per-camera measured errors are included"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileExistsError, FileNotFoundError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
