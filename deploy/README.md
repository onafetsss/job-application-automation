# VPS Deploy Runbook — Job Application Agent on the Hostinger `stack`

Deploys the current agent (phase 03-05 SDUI fixes + 05-02 display stack) onto the existing
Hostinger compose project at `/opt/stack`, exposing the Camoufox browser over noVNC at
`recaptcha.runlucid.co` for remote reCAPTCHA solving — without disrupting the running n8n.

**Target:** `root@srv1505084` (Hostinger, Ubuntu 24.04). Stack: postgres + n8n + browserless +
caddy + job-app-api on network `n8n-net`. Proxy: Caddy. Domain: `runlucid.co`.

Legend: **[MAC]** run on your laptop · **[VPS]** run on the server · **[DNS]** at your DNS provider.

---

## 1. Push code [MAC]
```bash
cd "/Users/stefano/Documents/Workspaces/Job Application Automation"
git ls-files | grep -E 'google_(token|credentials)' && echo "ABORT: secret tracked" || echo "ok, no secrets tracked"
git push origin main
```

## 2. Replace leaked token with an SSH deploy key [VPS]
```bash
ssh-keygen -t ed25519 -f /root/.ssh/job_app_deploy -N "" -C "job-app-vps-deploy"
cat /root/.ssh/job_app_deploy.pub      # add this to GitHub repo > Settings > Deploy keys (read-only)

cat >> /root/.ssh/config <<'EOF'
Host github.com
    IdentityFile /root/.ssh/job_app_deploy
    IdentitiesOnly yes
EOF

git -C /opt/job-app remote set-url origin git@github.com:onafetsss/job-application-automation.git
git -C /opt/job-app remote -v          # confirm NO ghp_ token remains
git -C /opt/job-app fetch origin && git -C /opt/job-app checkout main && git -C /opt/job-app pull --ff-only origin main
git -C /opt/job-app log --oneline -3
```
> After this the leaked PAT is unused — revoke it at github.com/settings/tokens, zero impact.

## 3. Transfer session + secrets [MAC]
```bash
cd "/Users/stefano/Documents/Workspaces/Job Application Automation"
rsync -az --delete data/linkedin_profile/ root@srv1505084:/opt/job-app/data/linkedin_profile/
scp .google_token.json root@srv1505084:/opt/job-app/.google_token.json
test -f .google_credentials.json && scp .google_credentials.json root@srv1505084:/opt/job-app/.google_credentials.json || true
```
Verify [VPS]: `ls /opt/job-app/data/linkedin_profile/ | head` (cookies.sqlite, key4.db present);
`df -T /opt/job-app/data` (ext4, not overlay/nfs).

## 4. Edit the stack [VPS]
```bash
cp /opt/stack/docker-compose.yml /opt/stack/docker-compose.yml.bak
cp /opt/stack/Caddyfile /opt/stack/Caddyfile.bak
```
- Replace the `job-app-api:` service block in `/opt/stack/docker-compose.yml` with
  `/opt/job-app/deploy/stack.job-app-browser.snippet.yml`.
- Append `/opt/job-app/deploy/Caddyfile.recaptcha.snippet` to `/opt/stack/Caddyfile`.
- Add to `/opt/stack/.env`:
  ```
  VNC_PASSWD=<strong password for the internal x11vnc>
  NOVNC_USER=stefano
  NOVNC_PASSWORD_HASH=<output of: docker exec stack-caddy-1 caddy hash-password --plaintext 'STRONG_PASSWORD'>
  ```
- Validate without touching running services:
  ```bash
  cd /opt/stack && docker compose config >/dev/null && echo "compose OK"
  ```

## 5. DNS [DNS]
Add A record `recaptcha` → VPS public IP (`curl -s ifconfig.me` on the VPS).
Verify: `dig +short recaptcha.runlucid.co` returns the VPS IP.

## 6. Build + deploy + verify [VPS]
```bash
cd /opt/stack
docker compose up -d --build job-app-api caddy     # only these two; n8n/postgres/browserless keep running

docker compose ps
docker exec stack-job-app-api-1 supervisorctl status   # xvfb fluxbox x11vnc novnc app = RUNNING
docker logs --tail 30 stack-job-app-api-1

# n8n untouched?
curl -sI https://n8n.runlucid.co | head -1             # 200/302
# noVNC auth-gated?
curl -sI https://recaptcha.runlucid.co | head -1       # 401 without creds
```
Then open `https://recaptcha.runlucid.co`, log in with NOVNC_USER / password, confirm the fluxbox desktop.

---

## Rollback
If anything breaks the stack:
```bash
cp /opt/stack/docker-compose.yml.bak /opt/stack/docker-compose.yml
cp /opt/stack/Caddyfile.bak /opt/stack/Caddyfile
git -C /opt/job-app checkout bf6d040          # the pre-deploy commit
cd /opt/stack && docker compose up -d --build job-app-api caddy
```
n8n, postgres, and browserless are never modified by this runbook, so they are unaffected by a rollback.
