# Twitch Drops Miner Web

Docker-ready Twitch Drops miner with a browser dashboard, multi-instance support, and automatic container builds for Angelo's/Dutchevil's fork.

This fork is based on [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) and focuses on reliable headless Docker use with a web UI.

## What this fork adds

- Web dashboard for monitoring status, current channel/game/drop, campaigns, inventory, diagnostics, and progress health.
- Docker-first deployment using the published GHCR image.
- `PORT` environment variable support for Portainer/Dockhand stacks.
- Multi-instance support: run one container per Twitch account with a separate `/data` volume.
- Automatic inventory/campaign refresh after OAuth login and from the top-page Refresh button.
- Fixed Twitch watch-progress reporting via the Spade watch endpoint.
- Live dashboard polling, cache-busted assets, smart campaign/inventory filters, and real diagnostics instead of placeholders.
- GitHub Actions build/test pipeline for every push, with GHCR publish for branches/tags.
- Slim Python 3.13 Docker image without desktop GUI packages.
- Persistent `/data/.env` so web-login JWT sessions survive container updates/recreates.

## Published Docker image

The GitHub Actions workflow builds/tests on every push and publishes branch/SHA tags. Pushes to `master` also update:

```text
ghcr.io/dutchevil/twitchdropsminer-web:latest
```

Additional tags are also published:

```text
ghcr.io/dutchevil/twitchdropsminer-web:master
ghcr.io/dutchevil/twitchdropsminer-web:sha-xxxxxxx
```

Use `latest` for automatic Dockhand/Portainer update tracking, or pin a `sha-xxxxxxx` tag if you want reproducible deployments.

## Recommended Docker Compose stack

```yaml
services:
  twitch-drops-miner:
    image: ghcr.io/dutchevil/twitchdropsminer-web:latest
    container_name: twitchdropsminer-web
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - TZ=UTC
      - PORT=8080
      - DOCKER_CONTAINER=true
```

Open the dashboard at:

```text
http://SERVER-IP:8080
```

## Multi-instance example

Run one container per Twitch account. Each instance must have a unique container name, host port, internal `PORT`, and data directory.

```yaml
services:
  twitch-drops-miner:
    image: ghcr.io/dutchevil/twitchdropsminer-web:latest
    container_name: twitchdropsminer-web
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - TZ=UTC
      - PORT=8080
      - DOCKER_CONTAINER=true

  twitch-drops-miner-tom:
    image: ghcr.io/dutchevil/twitchdropsminer-web:latest
    container_name: twitchdropsminer-web-tom
    restart: unless-stopped
    ports:
      - "8181:8181"
    volumes:
      - ./data-tom:/data
    environment:
      - TZ=UTC
      - PORT=8181
      - DOCKER_CONTAINER=true
```

Dashboards:

```text
http://SERVER-IP:8080
http://SERVER-IP:8181
```

Important: do **not** share the same `/data` directory between instances. `/data` contains the Twitch login/session, settings, cookies, blacklist, and credentials for that account.

## Updating with Dockhand / Portainer

Point your stack at:

```yaml
image: ghcr.io/dutchevil/twitchdropsminer-web:latest
```

Then Dockhand/Portainer can watch the registry image and redeploy when `latest` changes.

The image is rebuilt automatically by GitHub Actions on every push to `master`, so the update flow is:

```text
git push to master -> GitHub Actions tests/builds -> GHCR latest updated -> Dockhand sees new image
```

## Login and linked game accounts

1. Start the container.
2. Open the dashboard.
3. Log in with Twitch through the web flow.
4. Link game accounts on Twitch Drops campaigns where required.
5. Click the dashboard **Refresh** button. It now triggers a real inventory/campaign refresh before updating the UI.

If a campaign still shows unlinked, Twitch may not have refreshed the linked state yet. Wait briefly and click Refresh again. A container restart should only be a fallback, not the normal path.

## Environment variables

| Variable | Default | Description |
|---|---:|---|
| `PORT` | `8080` | Web server port inside the container. Recommended for stacks. |
| `WEB_PORT` | `8080` | Backward-compatible older port variable. `PORT` takes precedence. |
| `TZ` | `UTC` | Container timezone. |
| `DOCKER_CONTAINER` | `true` | Marks the app as running in Docker mode. |
| `JWT_SECRET` | generated | Persisted in `/data/.env`; normally leave empty so the entrypoint generates it once. |

Port mapping must match the internal port you set:

```yaml
ports:
  - "8181:8181"
environment:
  - PORT=8181
```

Alternatively, you can keep every container internally on 8080 and only change the host port:

```yaml
ports:
  - "8181:8080"
environment:
  - PORT=8080
```

Both patterns work; using matching ports is often clearer in Dockhand/Portainer.

## Development checks

The CI workflow runs these checks:

- JavaScript syntax checks for dashboard files.
- Frontend inventory-card rendering regression test.
- Docker image build on Python 3.13 slim.
- Python compile checks inside the built image.
- Backend helper and Docker entrypoint config regression tests inside the built image.
- GHCR publish on push to `master` and version tags.

Local equivalent:

```bash
node --check web/static/js/main.js
node --check web/static/js/lazy-loader.js
node --check web/static/js/drop-progress.js
node --check web/static/js/advanced-mode.js
APP_ROOT="$PWD" node tests/test_inventory_card_rendering.js
python3 -m py_compile docker_main.py web/app.py channel.py twitch.py inventory.py constants.py utils.py web/auth.py
docker build -t twitchdropsminerweb:local-check .
docker run --rm --entrypoint python twitchdropsminerweb:local-check /app/tests/test_web_dashboard_helpers.py
docker run --rm --entrypoint python twitchdropsminerweb:local-check /app/tests/test_docker_entrypoint_config.py
```

## GitHub Actions

There is intentionally **one** workflow:

```text
.github/workflows/ci.yml
```

It runs on:

- every push to any branch
- version tags like `v1.2.3`
- pull requests targeting `master`
- manual `workflow_dispatch`

Pull requests build and test only. Pushes publish a branch/SHA image tag; pushes to `master` also update `latest` and `master`. Version tags also publish versioned tags.

## Safety notes

- Do not watch Twitch manually in the browser with the same Twitch account while the miner is mining; Twitch progress can become inconsistent.
- Keep `/data/cookies.jar` private. It contains login/session state.
- Campaigns that require game-account linking cannot be mined until Twitch reports them as linked for that Twitch account.
