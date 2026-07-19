#!/bin/bash
set -e

# Set Docker container indicator
export DOCKER_CONTAINER=true

# Create data directory if it doesn't exist
mkdir -p /data

# Persist .env in /data so JWT_SECRET survives container recreate/update.
# Keep /app/.env as a symlink because web/auth.py and generate_jwt_secret.py
# both resolve the env file relative to /app.
if [ ! -f /data/.env ]; then
    if [ -f /app/.env.example ]; then
        echo "Creating persistent /data/.env from .env.example"
        cp /app/.env.example /data/.env
    else
        echo "Creating persistent /data/.env"
        printf 'PORT=%s\nTZ=%s\nJWT_SECRET=\n' "${PORT:-8080}" "${TZ:-UTC}" > /data/.env
    fi
fi
rm -f /app/.env
ln -sf /data/.env /app/.env

# Check if settings.json exists in /data, if not create with default values
if [ ! -f /data/settings.json ]; then
    echo "Creating default settings.json in /data directory"
    cat > /data/settings.json << 'EOL'
{
    "autostart_tray": false,
    "connection_quality": 1,
    "exclude": {
        "__type": "set",
        "data": []
    },
    "gui_enabled": false,
    "language": "",
    "priority": [],
    "priority_mode": {
        "__type": "PriorityMode",
        "data": 1
    },
    "proxy": {
        "__type": "URL",
        "data": ""
    },
    "tray_notifications": true
}
EOL
fi

# Create empty cookies.jar if it doesn't exist
if [ ! -f /data/cookies.jar ]; then
    echo "Creating empty cookies.jar in /data directory"
    touch /data/cookies.jar
fi

# Create empty credentials.json if it doesn't exist (for authentication)
if [ ! -f /data/credentials.json ]; then
    echo "Creating empty credentials.json in /data directory"
    echo '{"users": [], "setup_complete": false}' > /data/credentials.json
fi

# Create empty blacklist.json if it doesn't exist (for authentication)
if [ ! -f /data/blacklist.json ]; then
    echo "Creating empty blacklist.json in /data directory"
    echo '{"blacklisted_tokens": {}, "last_cleanup": 0}' > /data/blacklist.json
fi

# Remove existing files if they exist to avoid symbolic link errors
rm -f /app/settings.json /app/cookies.jar /app/credentials.json /app/blacklist.json

# Ensure proper permissions on the data files
chmod 644 /data/settings.json
chmod 600 /data/.env /data/cookies.jar /data/credentials.json /data/blacklist.json

# Create symbolic links
ln -sf /data/settings.json /app/settings.json
ln -sf /data/cookies.jar /app/cookies.jar
ln -sf /data/credentials.json /app/credentials.json
ln -sf /data/blacklist.json /app/blacklist.json

# Debug permissions without printing file contents/secrets
echo "Current user: $(whoami)"
echo "Data directory initialized: /data"

# Import smoke checks that fail fast if the image is broken
echo "Verifying Python imports..."
python -c "import yarl; print(f\"yarl version: {yarl.__version__}\")"
python -c "import aiohttp; print(f\"aiohttp version: {aiohttp.__version__}\")"

# Check if JWT_SECRET is empty in .env file
if grep -q "JWT_SECRET=$" /app/.env 2>/dev/null || ! grep -q "JWT_SECRET=" /app/.env 2>/dev/null; then
    echo "Generating persistent JWT secret..."
    python /app/generate_jwt_secret.py
fi

# Make sure generated secret remains private after generate_jwt_secret.py writes it
chmod 600 /data/.env

echo "Starting TwitchDropsMiner..."
exec python docker_main.py
