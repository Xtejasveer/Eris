# Eris: the website and everything it runs (python main.py serve). See docs/deploy.md.
#
# The app lives at /srv/eris, and docker-compose.yml mounts the data folders (data/, workspace/, chroma_db/) at the
# same path on the server. The code sandbox starts its throwaway containers through the server's Docker, which
# mounts a program's folder by its path: that path must be the same inside and outside this container.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# LibreOffice draws the slides as pictures (material/slide_images.py). Noto covers Hindi, Tamil, Telugu, Bengali and
# the other scripts; Carlito and Caladea stand in for Calibri and Cambria at the same widths, so slides don't reflow.
# PortAudio is loaded by the voice module at start. Node checks the interactive graphs while a script is generated.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress libreoffice-core \
        fonts-noto-core fonts-noto-ui-core fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
        libportaudio2 nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The Docker command line (not the engine): the sandbox runs programs in containers on the server's Docker.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /srv/eris
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
