# MarkTrail — Production Deployment & Operator Guide

> Institutional Guide for Running a Production-Ready, Blockchain-Hardened Academic Marks Pilot

---

## 1. System Overview & Pilot Target

This guide covers the deployment of MarkTrail for a small, blockchain-enabled university pilot targeting:
- **Scope**: Single institution-approved VPS/VM for 1 course with ~30 enrolled students, plus the course lecturer, department reviewer, exam-office staff, portal operator, and system administrator.
- **Access Model**: Public web access is strictly HTTPS-only. The database, secrets, and local backend port (`127.0.0.1:8000`) are non-routable and never exposed directly to the internet.
- **Integrity Layer**: Merkle commitments and cryptographic state hashes are submitted to the `MarkTrailAudit` smart contract on each stage handoff, providing an immutable audit trail while keeping student personal data and actual numeric marks confidential.

---

## 2. Server Requirements & Pre-Requisites

### Recommended VPS Specifications
- **Operating System**: Ubuntu 22.04 / 24.04 LTS or Debian 12
- **Compute**: 2 vCPU, 2 GB RAM (or 4 GB if running local Foundry Anvil node on the same machine)
- **Disk**: 25 GB SSD (ext4 filesystem)
- **Network**: Static public IPv4, domain name pointing to the VPS (e.g., `marks.university.ac.ke`)

### Required Packages
Install Python 3.10+, Foundry toolchain, and Git:

```bash
# 1. Update OS and install prerequisites
sudo apt-get update && sudo apt-get install -y \
    curl git python3 python3-pip gzip ufw

# 2. Install Foundry (for EVM contract compilation, deployment, and cast CLI)
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc
foundryup

# 3. Verify toolchain versions
python3 --version
forge --version
cast --version
```

---

## 3. User & Filesystem Provisioning

To enforce least-privilege security, MarkTrail runs under a dedicated unprivileged system user with no login shell:

```bash
# 1. Create system group and user
sudo groupadd -r marktrail
sudo useradd -r -g marktrail -s /usr/sbin/nologin -d /opt/marktrail marktrail

# 2. Set up application directory layout
sudo mkdir -p /opt/marktrail
sudo mkdir -p /opt/marktrail/data
sudo mkdir -p /opt/marktrail/backups
sudo mkdir -p /etc/marktrail
sudo mkdir -p /var/log/caddy

# 3. Clone or copy codebase into /opt/marktrail
sudo git clone https://github.com/university/MarkTrail.git /opt/marktrail
# Or copy current deployment:
# sudo cp -r /path/to/MarkTrail/* /opt/marktrail/

# 4. Set directory permissions
sudo chown -R marktrail:marktrail /opt/marktrail
sudo chmod 750 /opt/marktrail
sudo chmod 700 /opt/marktrail/data
sudo chmod 700 /opt/marktrail/backups
sudo chmod 700 /etc/marktrail
```

---

## 4. Configuration & Production Environment

Copy `config.example.env` to `/etc/marktrail/marktrail.env` and restrict file permissions:

```bash
sudo cp /opt/marktrail/config.example.env /etc/marktrail/marktrail.env
sudo chown marktrail:marktrail /etc/marktrail/marktrail.env
sudo chmod 600 /etc/marktrail/marktrail.env
```

Edit `/etc/marktrail/marktrail.env` with production values:

```ini
# Server Binding (Localhost only — traffic must pass through reverse proxy)
MARKTRAIL_HOST=127.0.0.1
MARKTRAIL_PORT=8000

# Security: Set to 1 for HTTPS deployments to enforce Secure session cookies
MARKTRAIL_COOKIE_SECURE=1

# Session cookie secret (Generate with: openssl rand -hex 32)
MARKTRAIL_COOKIE_SECRET=replace_with_64_char_random_hex_string

# Database path (Stored in restricted permissions directory)
MARKTRAIL_DATABASE_PATH=/opt/marktrail/data/marktrail.db

# Blockchain Integration Mode ('cast' or 'off')
MARKTRAIL_CHAIN_MODE=cast
MARKTRAIL_CHAIN_RPC=http://127.0.0.1:8545
MARKTRAIL_CONTRACT=0xYourDeployedContractAddress
MARKTRAIL_CHAIN_PRIVATE_KEY=0xYourRelayerPrivateKey
```

---

## 5. First Administrator Bootstrap

When deploying to a fresh database, MarkTrail **blocks all logins** until the initial administrator is created.

Run the secure CLI bootstrap command as the `marktrail` user:

```bash
sudo -u marktrail python3 /opt/marktrail/run.py --create-admin
```

You will be interactively prompted:
```text
Administrator username: admin
Administrator full name: Academic Registrar Admin
Administrator password (12+ characters): ************
Confirm administrator password: ************
Initial administrator created (user ID 1).
```

> [!IMPORTANT]
> The `--create-admin` command enforces a strict minimum length of 12 characters and only functions when the user table is completely empty.

---

## 6. Systemd Managed Service

Install the hardened systemd unit file:

```bash
# 1. Copy service unit
sudo cp /opt/marktrail/deploy/systemd/marktrail.service /etc/systemd/system/marktrail.service

# 2. Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable marktrail

# 3. Start the service
sudo systemctl start marktrail

# 4. Check status and logs
sudo systemctl status marktrail
sudo journalctl -u marktrail -f
```

### Security Features of the Systemd Unit:
- **`ProtectSystem=strict`**: The entire OS filesystem is mounted read-only to the process.
- **`ReadWritePaths=/opt/marktrail/data`**: The application is restricted to writing solely to its designated data folder.
- **`ProtectHome=true`** & **`PrivateTmp=true`**: Complete isolation from user home directories and system `/tmp`.
- **`Restart=always`**: Automatically recovers within 5 seconds if the service terminates unexpectedly.

---

## 7. TLS Termination & Reverse Proxy

### Option A: Caddy (Recommended — Automatic TLS)

Caddy automatically provisions, verifies, and renews TLS certificates via Let's Encrypt / ZeroSSL with zero manual intervention.

```bash
# 1. Install Caddy (Debian/Ubuntu)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

# 2. Install MarkTrail Caddyfile
sudo cp /opt/marktrail/deploy/caddy/Caddyfile /etc/caddy/Caddyfile

# 3. Edit /etc/caddy/Caddyfile with your actual domain name and admin email
sudo nano /etc/caddy/Caddyfile

# 4. Restart Caddy
sudo systemctl restart caddy
```

### Option B: Nginx + Certbot

For environments requiring Nginx:

```bash
# 1. Install Nginx and Certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 2. Copy Nginx configuration
sudo cp /opt/marktrail/deploy/nginx/marktrail.conf /etc/nginx/sites-available/marktrail.conf
sudo ln -s /etc/nginx/sites-available/marktrail.conf /etc/nginx/sites-enabled/

# 3. Obtain TLS certificate
sudo certbot --nginx -d marks.university.ac.ke

# 4. Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### Configure Firewall:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

---

## 8. Automated SQLite Online Backups & Retention

MarkTrail includes `scripts/backup.sh` which uses SQLite's non-blocking `VACUUM INTO` command to generate clean, atomic snapshots of the live database without acquiring exclusive table locks or requiring service downtime.

### Testing the Backup Script
```bash
sudo -u marktrail /opt/marktrail/scripts/backup.sh
```

### Setting up Automated Cron Schedule
Schedule automatic backups daily at 02:00 UTC (and prune backups older than 14 days):

```bash
sudo crontab -u marktrail -e
```

Add the following line:
```cron
0 2 * * * /opt/marktrail/scripts/backup.sh >> /opt/marktrail/data/backup.log 2>&1
```

### Database Restore Procedure
If recovery is ever required:

```bash
# 1. Stop the application service
sudo systemctl stop marktrail

# 2. Run restore script (automatically performs pre-restore verification and backup)
sudo -u marktrail /opt/marktrail/scripts/restore.sh /opt/marktrail/backups/marktrail_backup_20261023_020000Z.db.gz

# 3. Restart application service
sudo systemctl start marktrail
```

---

## 9. Blockchain Network: Anvil to Testnet Migration

### Step 1: Local Pilot on Anvil
For initial internal validation, run Anvil as a managed systemd service or background daemon:
```bash
anvil --port 8545 --silent
```

Deploy the contract and authorize the relayer account:
```bash
forge create src/MarkTrailAudit.sol:MarkTrailAudit \
  --rpc-url http://127.0.0.1:8545 \
  --private-key YOUR_ANVIL_PRIVATE_KEY \
  --broadcast
```

### Step 2: Migrating to Institutional Testnet (e.g. Base Sepolia or Private Besu)
When ready to connect to a real distributed ledger:

1. **Obtain Testnet RPC Endpoint**:
   - Institutional Node: Run a private Hyperledger Besu or Go-Ethereum node within university infrastructure.
   - Public Testnet: Use an infrastructure provider (e.g. Alchemy, Infura, QuickNode) targeting Base Sepolia (`https://sepolia.base.org`).

2. **Deploy and Verify the Contract**:
   ```bash
   forge create src/MarkTrailAudit.sol:MarkTrailAudit \
     --rpc-url $MARKTRAIL_CHAIN_RPC \
     --private-key $DEPLOYER_PRIVATE_KEY \
     --broadcast \
     --verify
   ```

3. **Authorize Relayer Address**:
   Set the server's operational address as both lecturer and reviewer on the contract:
   ```bash
   cast send $CONTRACT_ADDRESS "setLecturer(address,bool)" $RELAYER_ADDRESS true \
     --rpc-url $MARKTRAIL_CHAIN_RPC --private-key $DEPLOYER_PRIVATE_KEY

   cast send $CONTRACT_ADDRESS "setReviewer(address,bool)" $RELAYER_ADDRESS true \
     --rpc-url $MARKTRAIL_CHAIN_RPC --private-key $DEPLOYER_PRIVATE_KEY
   ```

4. **Update Production Environment**:
   In `/etc/marktrail/marktrail.env`:
   ```ini
   MARKTRAIL_CHAIN_MODE=cast
   MARKTRAIL_CHAIN_RPC=https://sepolia.base.org
   MARKTRAIL_CONTRACT=0xYourVerifiedContractAddress
   MARKTRAIL_CHAIN_PRIVATE_KEY=0xYourRelayerAccountKey
   ```
   Restart service:
   ```bash
   sudo systemctl restart marktrail
   ```

---

## 10. Operational Runbook

### Handling Chain Transaction Failures
If the blockchain network experiences temporary downtime or gas price spikes:
1. MarkTrail automatically retries with exponential backoff (`1s`, `2s`, `4s`).
2. If all retries fail, the batch status is clearly flagged as `Chain error` (`ERROR`) in the web UI.
3. The database record is safely preserved locally — MarkTrail **never** silently discards marks or falls back to uncommitted state.
4. Once network connectivity is restored, lecturers, reviewers, or admins can click **Retry chain** on the batch view, or admins can click **Recover Pending / Error Batches** to reconcile all affected batches in bulk.
5. On service startup, MarkTrail automatically scans for any pending or interrupted transactions and completes their on-chain verification in the background.
