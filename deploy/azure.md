# Deploying Eris on Azure for Students (Docker)

Azure for Students gives about $100 of credit for 12 months with no card. One Linux virtual machine runs Eris and
Caddy (HTTPS) with Docker, exactly as in `deploy/README.md`; only the server setup below is Azure-specific. A
Standard_B2s machine (2 vCPU, 4 GB) costs roughly $30–35 a month from the credit. When the credit runs out the
subscription simply stops: nothing is charged.

---

## 1. Get Azure for Students

1. Open <https://azure.microsoft.com/free/students> and click **Start free**.
2. Sign in with a Microsoft account (or create one), then verify you're a student with your **college email**
   (Azure sends a link) and your phone number.
3. When it's done, the Azure portal (<https://portal.azure.com>) shows a subscription called **Azure for Students**.
   Your credit balance is at <https://www.microsoftazuresponsorships.com/balance>.

## 2. Create the virtual machine (in the portal)

Portal → search **Virtual machines** → **Create** → **Azure virtual machine**. Fill in:

**Basics**
- Subscription: **Azure for Students**
- Resource group: **Create new** → `eris-rg` (everything for Eris goes in it, so it can be deleted in one go later)
- Virtual machine name: `eris`
- Region: **(Asia Pacific) Central India**. If it says the size or region isn't allowed for your subscription, try
  **South India** or **East US** (student subscriptions only allow some regions).
- Availability options: **No infrastructure redundancy required**
- Security type: **Standard**
- Image: **Ubuntu Server 24.04 LTS – x64 Gen2**
- Size: **Standard_B2s** (2 vCPU, 4 GiB). Click "See all sizes" if it isn't listed.
- Authentication type: **SSH public key**, username `azureuser`, key pair: **Generate new key pair**, name `eris_key`
- Inbound ports: **Allow selected ports**, tick **SSH (22)**, **HTTP (80)**, **HTTPS (443)**

**Disks**
- OS disk size: **64 GiB**, type **Standard SSD**

**Networking**
- Public IP: keep the new one it creates (Standard SKU, which is a fixed IP)

**Management**
- Auto-shutdown: **off** (or the site goes offline every evening)

Click **Review + create** → **Create** → **Download private key and create resource**. Keep the downloaded
`eris_key.pem` safe: it is the only way into the server.

When it's ready, open the VM and note its **Public IP address**.

## 3. A free web address with HTTPS (recommended)

Azure gives every public IP a free name, which Caddy can get an HTTPS certificate for:

VM → **Overview** → click the Public IP → **Configuration** → **DNS name label**: e.g. `eris-yourname` → **Save**.

Your address is then `eris-yourname.centralindia.cloudapp.azure.com` (the region is part of the name).

## 4. Connect and install Docker

On your Mac:

```bash
chmod 400 ~/Downloads/eris_key.pem
ssh -i ~/Downloads/eris_key.pem azureuser@<PUBLIC_IP>
```

On the server:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit
```

Connect again (same `ssh` command) so the `docker` group applies.

## 5. Copy the code to `/srv/eris`

On your Mac, in the project folder:

```bash
tar czf /tmp/eris-code.tgz --exclude=.venv --exclude=.git --exclude=data --exclude=workspace \
  --exclude=chroma_db --exclude=media --exclude=.env --exclude='__pycache__' .
scp -i ~/Downloads/eris_key.pem /tmp/eris-code.tgz azureuser@<PUBLIC_IP>:/tmp/
ssh -i ~/Downloads/eris_key.pem azureuser@<PUBLIC_IP> \
  'sudo mkdir -p /srv/eris && sudo chown $USER /srv/eris && tar xzf /tmp/eris-code.tgz -C /srv/eris'
```

The path matters: the code sandbox needs the data folders at `/srv/eris` inside and outside the container.

## 6. Copy your courses and lessons (recommended)

Keeps the lessons, audio and demo courses you already generated (and saves paying to regenerate them):

```bash
tar czf /tmp/eris-data.tgz data workspace chroma_db
scp -i ~/Downloads/eris_key.pem /tmp/eris-data.tgz azureuser@<PUBLIC_IP>:/tmp/
ssh -i ~/Downloads/eris_key.pem azureuser@<PUBLIC_IP> 'tar xzf /tmp/eris-data.tgz -C /srv/eris'
```

## 7. Settings: `/srv/eris/.env`

```bash
ssh -i ~/Downloads/eris_key.pem azureuser@<PUBLIC_IP>
cd /srv/eris && cp .env.example .env && nano .env
```

Fill in (copy the keys from your Mac's `.env`):

```bash
OPENROUTER_API_KEY=...
GNANI_API_KEY=...
ERIS_DOMAIN=eris-yourname.centralindia.cloudapp.azure.com
ERIS_SECURE_COOKIES=true
ERIS_DEMO_LOGINS=true          # one-click demo sign-in for judges; anyone visiting can use it
```

Without the DNS name from step 3: leave `ERIS_DOMAIN` out and keep `ERIS_SECURE_COOKIES=false`; the site is then at
`http://<PUBLIC_IP>`.

Save in nano: Ctrl+O, Enter, Ctrl+X.

## 8. Start Eris

On the server, in `/srv/eris`:

```bash
mkdir -p data workspace chroma_db
docker pull python:3.12-slim
docker compose up -d --build
docker compose logs -f eris
```

The first build takes 5–10 minutes. Ctrl+C stops watching the logs, not Eris.

## 9. Test

Open `https://eris-yourname.centralindia.cloudapp.azure.com` (or `http://<PUBLIC_IP>`):

1. Sign in with a demo account.
2. Your courses and lessons are there.
3. A lesson plays with real slide pictures.
4. A doubt gets an answer.
5. In Studio, a lesson with code runs its program (the sandbox).

## 10. Keep an eye on the credit

- Balance: <https://www.microsoftazuresponsorships.com/balance>
- Portal → **Cost Management** → **Budgets** → add a budget (e.g. $20) with an email alert.

## 11. Updating Eris

Copy the code again (step 5), then on the server:

```bash
cd /srv/eris && docker compose up -d --build
```

Do it when no teacher is generating a script: a restart ends a running generation.

## 12. After the hackathon

Back up first (on your Mac):

```bash
ssh -i ~/Downloads/eris_key.pem azureuser@<PUBLIC_IP> 'cd /srv/eris && tar czf - data workspace chroma_db' > eris-backup.tgz
```

Then delete everything at once: portal → **Resource groups** → `eris-rg` → **Delete resource group** (type its
name to confirm). That removes the VM, its disk, the IP and the firewall rules, so the credit stops being used.

---

## Security settings (a small pilot, not a public product)

- **Code runs only in the Docker sandbox.** If its image is missing, running code is switched off rather than run
  unprotected: `docker pull python:3.12-slim`. Programs get no network, no secrets and only their own folder.
- **Students never trigger code runs** (`ERIS_STUDENT_CODE_RUNS=false`): their doubt answers explain code in words.
- **Only students can sign up** (`ERIS_TEACHER_SIGNUP=false`); teachers are the seeded accounts.
- **Demo accounts** (one-click on the sign-in page, password visible to anyone) can look, teach and generate, but not
  delete or reset. Turn them off with `ERIS_DEMO_LOGINS=false` when the judging is over.
- **Keys stay on the server:** `chmod 600 /srv/eris/.env`. Set a monthly spending limit on your OpenRouter key
  (openrouter.ai → Keys → edit the key → credit limit), so a misuse can't run up a large bill.
- **SSH:** Azure → VM → Networking → the SSH rule → Source: **My IP address**.

After changing `.env`: `docker compose up -d` (in `/srv/eris`).

## If something is wrong

| What you see | Why, and the fix |
|---|---|
| "Size not available" or "disallowed by policy" when creating the VM | Student subscriptions allow only some regions and sizes. Try South India or East US, or Standard_B2ms. |
| `Permission denied (publickey)` on ssh | Use the downloaded key with `-i`, run `chmod 400` on it, and the username `azureuser`. |
| The site doesn't open | `docker compose ps` (both containers running?), and the VM's **Networking** tab allows ports 80 and 443. |
| HTTPS certificate errors | The DNS name label (step 3) must be saved before Caddy starts: `docker compose logs caddy`, then `docker compose restart caddy`. |
| Sign-in doesn't stick | `ERIS_SECURE_COOKIES=true` without HTTPS. Use the DNS name, or set it to `false`. |
| Slides show as text | `docker compose logs eris \| grep slides` (LibreOffice). |
| Code lessons can't run programs | `docker pull python:3.12-slim`, then `docker compose restart eris`. |
