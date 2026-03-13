# Deploy AgentCart on AWS EC2 with Namecheap domain `kiroz.xyz`

This guide uses the simplest production path:
- One Ubuntu EC2 instance
- Docker Compose
- Caddy for automatic HTTPS certificates
- Two subdomains:
  - `app.kiroz.xyz` -> frontend
  - `api.kiroz.xyz` -> backend

## 1. Prerequisites

You need:
- AWS account
- Domain `kiroz.xyz` in Namecheap
- Cognito domain and app client id
- SSH key pair for EC2

## 2. Launch EC2

In AWS Console:
1. Go to `EC2 -> Launch instances`.
2. Choose:
   - AMI: `Ubuntu Server 24.04 LTS` (22.04 also works)
   - Instance type: `t3.small` minimum, `t3.medium` recommended
   - Storage: 30 GB or more
3. Security Group inbound rules:
   - TCP `22` from your own IP
   - TCP `80` from `0.0.0.0/0`
   - TCP `443` from `0.0.0.0/0`
4. Launch instance and note the `Public IPv4`.

## 3. Configure Namecheap DNS

Open `Namecheap -> Domain List -> kiroz.xyz -> Manage -> Advanced DNS`.

Create 2 records:
1. `A Record`
   - Host: `app`
   - Value: `<EC2_PUBLIC_IPV4>`
   - TTL: `Automatic`
2. `A Record`
   - Host: `api`
   - Value: `<EC2_PUBLIC_IPV4>`
   - TTL: `Automatic`

Wait for DNS propagation (usually a few minutes, sometimes longer).

## 4. SSH and install Docker

From your local machine:

```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IPV4>
```

On EC2:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/<your-org-or-user>/Agentic-Shopping-Assistant.git
cd Agentic-Shopping-Assistant

chmod +x deploy/ec2/bootstrap_ubuntu_docker.sh
sudo ./deploy/ec2/bootstrap_ubuntu_docker.sh
exit
```

SSH again (to refresh docker group permissions):

```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IPV4>
cd Agentic-Shopping-Assistant
```

## 5. Configure Cognito callback/logout URLs

In Cognito app client settings:
- Callback URL: `https://app.kiroz.xyz`
- Sign-out URL: `https://app.kiroz.xyz`

## 6. Deploy with script

Run on EC2:

```bash
chmod +x deploy/ec2/configure_and_deploy.sh
./deploy/ec2/configure_and_deploy.sh \
  --domain-root kiroz.xyz \
  --acme-email you@example.com \
  --cognito-domain <your-cognito-domain>.auth.us-east-1.amazoncognito.com \
  --cognito-client-id <your-cognito-client-id> \
  --cognito-user-pool-id <your-cognito-user-pool-id> \
  --aws-region us-east-1 \
  --mock-model true
```

After deployment:
- Frontend: `https://app.kiroz.xyz`
- Backend health (same-origin route): `https://app.kiroz.xyz/api/health`
- Backend health (direct api subdomain): `https://api.kiroz.xyz/health`

First HTTPS issuance from Caddy may take 1-2 minutes.

## 7. Warm up product catalog

```bash
chmod +x deploy/ec2/warmup_catalog.sh
./deploy/ec2/warmup_catalog.sh 1600
```

## 8. Redeploy after new commits

```bash
chmod +x deploy/ec2/redeploy.sh
./deploy/ec2/redeploy.sh
```

## 9. Useful debug commands

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f caddy
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs -f backend
```

## 10. Switch from mock model to Bedrock

If you want real model calls:
1. Attach an IAM role to EC2 with `bedrock:InvokeModel` and `bedrock:Converse`.
2. Re-run deploy with:

```bash
./deploy/ec2/configure_and_deploy.sh \
  --domain-root kiroz.xyz \
  --acme-email you@example.com \
  --cognito-domain <your-cognito-domain>.auth.us-east-1.amazoncognito.com \
  --cognito-client-id <your-cognito-client-id> \
  --cognito-user-pool-id <your-cognito-user-pool-id> \
  --aws-region us-east-1 \
  --mock-model false
```

## Added files

- `docker-compose.prod.yml`
- `deploy/ec2/Caddyfile`
- `deploy/ec2/bootstrap_ubuntu_docker.sh`
- `deploy/ec2/configure_and_deploy.sh`
- `deploy/ec2/redeploy.sh`
- `deploy/ec2/warmup_catalog.sh`
