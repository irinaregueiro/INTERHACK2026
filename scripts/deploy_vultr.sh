#!/bin/bash
# Manual deployment script for Vultr VPS

# Usage: ./deploy_vultr.sh <vultr_ip> <username>
# Example: ./deploy_vultr.sh 203.0.113.5 root

set -e

HOST=$1
USER=${2:-root}
APP_DIR="/opt/customer-twin"

if [ -z "$HOST" ]; then
    echo "Usage: $0 <vultr_ip> [username]"
    echo "Example: $0 192.168.1.5 root"
    exit 1
fi

echo "🚀 Deploying Customer Twin to $USER@$HOST..."

ssh "$USER@$HOST" << 'EOF'
set -e

APP_DIR="/opt/customer-twin"

echo "📂 Checking installation directory..."
if [ ! -d "$APP_DIR/.git" ]; then
    echo "📦 Cloning repository..."
    sudo mkdir -p "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR"
    git clone https://github.com/irinaregueiro/INTERHACK2026.git "$APP_DIR"
else
    echo "🔄 Pulling latest changes from main..."
    cd "$APP_DIR"
    git fetch origin
    git reset --hard origin/main
fi

cd "$APP_DIR/customer-twin"

echo "🐳 Rebuilding and starting Docker containers..."
docker-compose down
docker-compose up -d --build

echo "🧹 Cleaning up dangling images..."
docker image prune -f

echo "✅ Deployment complete! Your API is running."
EOF
