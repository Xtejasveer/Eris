# Deploying Eris on Google Cloud (Docker)

One small virtual machine runs two containers: **eris** (the website, `python main.py serve`) and **caddy** (HTTPS in
front of it). Your courses, lessons, audio and the database stay on the machine's disk in `/srv/eris`, outside the
containers, so updating Eris never touches them.

What you pay for: the VM (about $25–35 a month for an e2-medium, covered by Google's free trial credit for new
accounts) and, as now, your OpenRouter and Gnani usage.

---

## 1. Before you start

- A Google Cloud account with billing set up (the free trial is fine).
- The `gcloud` command line on your laptop: <https://cloud.google.com/sdk/docs/install>, then `gcloud init`.
- Your API keys: `OPENROUTER_API_KEY` and `GNANI_API_KEY` (from your local `.env`).
- Optional: a domain (or subdomain) for HTTPS, e.g. `eris.yourname.dev`. Without one, Eris runs on the server's IP over
  plain HTTP, which is fine for a demo.

**Set a budget alert first:** Console → Billing → Budgets & alerts → Create budget (for example $10), so nothing
surprises you.

## 2. Create the server

Mumbai (`asia-south1`) is closest to Indian users. Run these on your laptop:

```bash
gcloud config set compute/region asia-south1
gcloud config set compute/zone asia-south1-a

# A fixed public IP, so the address (and your domain) never changes
gcloud compute addresses create eris-ip

# The VM: 2 vCPU, 4 GB RAM, 40 GB disk, Ubuntu 24.04
gcloud compute instances create eris \
  --machine-type=e2-medium \
  --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
  --boot-disk-size=40GB \
  --address=eris-ip \
  --tags=eris-web

# Let web traffic in (ports 80 and 443 only)
gcloud compute firewall-rules create eris-web --allow=tcp:80,tcp:443 --target-tags=eris-web

# The IP to open in the browser (and to point your domain at)
gcloud compute addresses describe eris-ip --format='value(address)'
```

## 3. Install Docker on the server

```bash
gcloud compute ssh eris
```

Then, on the server:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```

Log in again (`gcloud compute ssh eris`) so the `docker` group applies.

## 4. Put the code in `/srv/eris`

The path matters: the code sandbox needs the data folders at `/srv/eris` both inside and outside the container.

**If the code is on GitHub** (on the server):

```bash
sudo mkdir -p /srv/eris && sudo chown $USER /srv/eris
git clone https://github.com/<you>/<repo>.git /srv/eris
```

For a private repository, use a GitHub personal access token as the password, or a deploy key.

**Or copy it from your laptop** (no GitHub needed). On your laptop, in the project folder:

```bash
tar czf /tmp/eris-code.tgz --exclude=.venv --exclude=.git --exclude=data --exclude=workspace \
  --exclude=chroma_db --exclude=media --exclude=.env --exclude='__pycache__' .
gcloud compute scp /tmp/eris-code.tgz eris:/tmp/
gcloud compute ssh eris --command='sudo mkdir -p /srv/eris && sudo chown $USER /srv/eris && tar xzf /tmp/eris-code.tgz -C /srv/eris'
```

## 5. Bring your courses and lessons (optional)

To start with the lessons you already generated (audio, slides, courses, attendance), copy the three data folders
from your laptop. This also saves regenerating them, and the OpenRouter and Gnani cost that comes with it.

On your laptop, in the project folder:

```bash
tar czf /tmp/eris-data.tgz data workspace chroma_db
gcloud compute scp /tmp/eris-data.tgz eris:/tmp/
gcloud compute ssh eris --command='tar xzf /tmp/eris-data.tgz -C /srv/eris'
```

To start empty instead, skip this step. You can add the demo courses later with
`docker compose exec eris python main.py seed`.

## 6. Settings: `/srv/eris/.env`

On the server, create `/srv/eris/.env` from the example and fill it in:

```bash
cd /srv/eris
cp .env.example .env
nano .env
```

Set at least:

```bash
OPENROUTER_API_KEY=...
GNANI_API_KEY=...

# With a domain: Caddy gets the HTTPS certificate, and the sign-in cookie is sent over HTTPS only
ERIS_DOMAIN=eris.yourname.dev
ERIS_SECURE_COOKIES=true

# One-click demo sign-in buttons: handy for judges, but anyone can sign in as a demo user. Turn off for real users.
ERIS_DEMO_LOGINS=true
```

Without a domain, leave `ERIS_DOMAIN` out and keep `ERIS_SECURE_COOKIES=false`: the site runs on
`http://<server IP>`, and a secure cookie would never be sent over plain HTTP, so nobody could stay signed in.

If you use a domain, add a DNS **A record** pointing it to the IP from step 2 before starting.

## 7. Start Eris

```bash
cd /srv/eris
mkdir -p data workspace chroma_db
docker pull python:3.12-slim          # the image the code sandbox runs programs in
docker compose up -d --build          # first build takes a few minutes (LibreOffice is large)
docker compose logs -f eris           # watch it start; Ctrl+C stops watching, not Eris
```

Open `https://eris.yourname.dev` (or `http://<server IP>`). Both containers restart by themselves after a crash or a
reboot.

## 8. Updating Eris later

Wait until no teacher is generating a script: a restart ends a running generation.

```bash
cd /srv/eris
git pull                               # or copy the code again as in step 4
docker compose up -d --build
```

Page changes (`web/`) show on the next browser refresh; Python changes take effect when the container restarts.

## 9. Backups

Everything that matters is in `/srv/eris/data`, `/srv/eris/workspace` and `/srv/eris/chroma_db`.

- Quick copy to your laptop:
  `gcloud compute ssh eris --command='cd /srv/eris && tar czf - data workspace chroma_db' > eris-backup.tgz`
- Or a nightly disk snapshot: Console → Compute Engine → Snapshots → Create snapshot schedule, attached to the
  `eris` disk.

## 10. After the hackathon

Stopping the VM is not enough: the disk and the fixed IP keep costing money. Delete all three:

```bash
gcloud compute instances delete eris
gcloud compute addresses delete eris-ip
gcloud compute firewall-rules delete eris-web
```

(Take a backup first, as in step 9.)

---

## If something is wrong

| What you see | Why, and the fix |
|---|---|
| The site doesn't open | `docker compose ps`: both containers should be "running". Check the firewall rule (step 2) and, with a domain, that the A record points to the right IP. |
| HTTPS certificate errors | The domain must point to the server before Caddy starts: `docker compose logs caddy`. |
| Sign-in doesn't stick | `ERIS_SECURE_COOKIES=true` on plain HTTP. Set it to `false`, or use a domain. |
| Slides show as text, not pictures | LibreOffice couldn't draw them: `docker compose logs eris \| grep slides`. |
| "Code" lessons fail to run programs | The sandbox image is missing: `docker pull python:3.12-slim`, then `docker compose restart eris`. |
| Out of memory while generating | Use an e2-standard-2 (8 GB) instead of e2-medium. |

## How the pieces fit

- `Dockerfile`: Python 3.12 with LibreOffice (slide pictures), fonts for every Indian script, Node (checks the
  interactive graphs while generating) and the Docker command line (code sandbox).
- `docker-compose.yml`: the two containers, the data folders mounted from `/srv/eris`, and the server's Docker
  socket for the code sandbox. The socket gives the Eris container control of Docker on the server, so keep the
  server for Eris only.
- `deploy/Caddyfile`: HTTPS, compression and 30 MB uploads in front of Eris.
- One Eris process on purpose: running generations and doubt sessions live in its memory.
