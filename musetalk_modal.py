"""Photorealistic teacher video with MuseTalk, run on a Modal GPU.

MuseTalk (MIT, Tencent) re-draws the mouth of a short teacher video so it speaks a given audio clip. A teacher
is "prepared" once (face boxes, masks and VAE latents of every frame, cached on a Modal Volume); after that each
narration clip renders at faster than real time on an L4.

Weights, all permissive: MuseTalk v1.5 (MIT), sd-vae-ft-mse (MIT), whisper-tiny (Apache-2.0),
DWPose (Apache-2.0), face-parse-bisent (WTFPL mirror), s3fd face detector (BSD-3, downloaded by face_alignment).

Called from talking_video.py (`python main.py video ...`); it can also be deployed with `modal deploy musetalk_modal.py`.
"""

import os

import modal

GPU = os.getenv("MUSETALK_GPU", "L4")  # Modal GPU type; T4 is slower but cheaper
MUSETALK_COMMIT = "0a89dec45a0192b824e3cf4daf96c239440c5ed8"  # pinned: the inference script is driven by its CLI
REPO = "/root/MuseTalk"
VOL = "/vol"

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.0.1", "torchvision==0.15.2", "torchaudio==2.0.2",
                 index_url="https://download.pytorch.org/whl/cu118")
    .pip_install("diffusers==0.30.2", "accelerate==0.28.0", "numpy==1.23.5", "opencv-python==4.9.0.80",
                 "soundfile==0.12.1", "transformers==4.39.2", "huggingface_hub==0.30.2", "librosa==0.11.0",
                 "einops==0.8.1", "omegaconf", "ffmpeg-python", "tqdm", "pyyaml")
    # OpenMMLab stack for DWPose. mmcv comes as a prebuilt CUDA 11.8 wheel; mmpose skips its optional deps
    # (chumpy fails to build on current pip and is only used for body models MuseTalk does not touch).
    .pip_install("mmengine", "mmcv==2.0.1", find_links="https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html")
    .pip_install("mmdet==3.1.0")
    .pip_install("json_tricks", "munkres", "xtcocotools", "scipy", "matplotlib")
    .run_commands("pip install --no-deps mmpose==1.1.0")
    .run_commands(
        f"git clone https://github.com/TMElyralab/MuseTalk.git {REPO}",
        f"cd {REPO} && git checkout {MUSETALK_COMMIT}",
        # Models and prepared avatars live on the Volume, so they survive between runs.
        f"ln -s {VOL}/models {REPO}/models",
        f"ln -s {VOL}/results {REPO}/results",
    )
    .env({"TORCH_HOME": f"{VOL}/torch", "HF_HUB_DISABLE_TELEMETRY": "1"})
)

app = modal.App("eris-musetalk", image=image)
volume = modal.Volume.from_name("eris-musetalk", create_if_missing=True)

WEIGHTS = [  # (repo, file in repo, folder under models/)
    ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", ""),
    ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", ""),
    ("stabilityai/sd-vae-ft-mse", "config.json", "sd-vae"),
    ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin", "sd-vae"),
    ("openai/whisper-tiny", "config.json", "whisper"),
    ("openai/whisper-tiny", "pytorch_model.bin", "whisper"),
    ("openai/whisper-tiny", "preprocessor_config.json", "whisper"),
    ("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "dwpose"),
    ("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth", "face-parse-bisent"),
    ("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth", "face-parse-bisent"),
]


def _ensure_weights():
    """Download any missing weights into the Volume (about 1.5 GB, once)."""
    import os

    from huggingface_hub import hf_hub_download

    missing = [w for w in WEIGHTS if not os.path.exists(os.path.join(VOL, "models", w[2], w[1]))]
    for repo, filename, folder in missing:
        print(f"[musetalk] downloading {repo}/{filename}")
        hf_hub_download(repo, filename, local_dir=os.path.join(VOL, "models", folder))
    os.makedirs(f"{VOL}/results", exist_ok=True)
    if missing:
        volume.commit()


@app.function(gpu=GPU, volumes={VOL: volume}, timeout=3600)
def render(avatar_id: str, clips: dict, teacher_video: bytes = None, fps: int = 25) -> dict:
    """Lip-sync the prepared teacher `avatar_id` to each clip. `clips` maps name -> WAV bytes; returns name -> MP4 bytes.

    The first call for an avatar must pass `teacher_video` (a short MP4 of the teacher, face visible, mouth mostly
    closed); it is prepared once and reused. MuseTalk loops that video forwards and backwards behind the speech.
    """
    import os
    import shutil
    import subprocess
    import tempfile

    import yaml

    _ensure_weights()
    avatar_dir = f"{VOL}/results/v15/avatars/{avatar_id}"
    prepared = os.path.exists(f"{avatar_dir}/latents.pt")
    if not prepared:
        if teacher_video is None:
            raise ValueError(f"Avatar '{avatar_id}' is not prepared yet; pass teacher_video")
        shutil.rmtree(avatar_dir, ignore_errors=True)  # a half-finished preparation would make the script prompt
        os.makedirs(f"{VOL}/teachers", exist_ok=True)
        video_path = f"{VOL}/teachers/{avatar_id}.mp4"
        with open(video_path, "wb") as f:
            f.write(teacher_video)
    else:
        video_path = f"{VOL}/teachers/{avatar_id}.mp4"

    work = tempfile.mkdtemp()
    audio = {}
    for name, wav in clips.items():
        path = f"{work}/{name}.wav"
        with open(path, "wb") as f:
            f.write(wav)
        audio[name] = path
    config_path = f"{work}/realtime.yaml"
    with open(config_path, "w") as f:
        yaml.safe_dump({avatar_id: {"preparation": not prepared, "bbox_shift": 0, "video_path": video_path,
                                    "audio_clips": audio}}, f)

    subprocess.run(
        ["python", "-m", "scripts.realtime_inference", "--version", "v15",
         "--unet_model_path", "models/musetalkV15/unet.pth", "--unet_config", "models/musetalkV15/musetalk.json",
         "--inference_config", config_path, "--fps", str(fps), "--batch_size", "20"],
        cwd=REPO, check=True)

    out = {}
    for name in clips:
        mp4 = f"{avatar_dir}/vid_output/{name}.mp4"
        if os.path.exists(mp4):
            with open(mp4, "rb") as f:
                out[name] = f.read()
            os.remove(mp4)
    volume.commit()  # keeps a newly prepared avatar
    shutil.rmtree(work, ignore_errors=True)
    return out
