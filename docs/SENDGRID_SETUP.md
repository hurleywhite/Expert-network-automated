# SendGrid Webhook Configuration Guide

This guide covers the complete SendGrid setup for the expert-outreach system, including account configuration, webhook setup, and production deployment.

## Table of Contents

1. [SendGrid Account Setup](#1-sendgrid-account-setup)
2. [Inbound Parse Configuration](#2-inbound-parse-configuration)
3. [Event Webhook Configuration](#3-event-webhook-configuration)
4. [Environment Variables](#4-environment-variables)
5. [Testing Webhooks Locally](#5-testing-webhooks-locally)
6. [Production Checklist](#6-production-checklist)

---

## 1. SendGrid Account Setup

### Creating an Account

1. Go to [https://sendgrid.com](https://sendgrid.com) and sign up for an account
2. Verify your email address
3. Complete account setup and identity verification (required for sending emails)

### API Key Generation

1. Navigate to **Settings > API Keys** in the SendGrid dashboard
2. Click **Create API Key**
3. Name it something descriptive like `expert-outreach-production`
4. Select **Restricted Access** and enable the following permissions:

| Permission Category | Access Level | Purpose |
|---------------------|--------------|---------|
| Mail Send | Full Access | Send outbound emails |
| Inbound Parse | Full Access | Receive inbound emails |
| Event Notification | Read Access | Receive delivery events |
| Suppressions | Full Access | Manage bounces and unsubscribes |

5. Click **Create & View**
6. **Copy the API key immediately** - it will only be shown once
7. Store it securely (you'll add it to your environment variables)

### Domain Authentication (SPF, DKIM)

Domain authentication is **required** for production use to ensure email deliverability and prevent emails from being marked as spam.

#### Step 1: Add Domain

1. Navigate to **Settings > Sender Authentication**
2. Click **Authenticate Your Domain**
3. Select your DNS provider (or choose "Other" if not listed)
4. Enter your domain (e.g., `yourdomain.com`)

#### Step 2: Configure DNS Records

SendGrid will provide DNS records to add. Typically these include:

**CNAME Records for DKIM:**
```
em1234.yourdomain.com -> u1234567.wl.sendgrid.net
s1._domainkey.yourdomain.com -> s1.domainkey.u1234567.wl.sendgrid.net
s2._domainkey.yourdomain.com -> s2.domainkey.u1234567.wl.sendgrid.net
```

**SPF Record (if not using CNAME method):**
```
v=spf1 include:sendgrid.net ~all
```

#### Step 3: Verify Domain

1. After adding DNS records, wait for propagation (can take up to 48 hours)
2. Click **Verify** in SendGrid dashboard
3. Domain status should change to "Verified"

---

## 2. Inbound Parse Configuration

Inbound Parse allows SendGrid to receive emails sent to your domain and forward them to your webhook endpoint.

### Setting Up MX Records

Add an MX record for the subdomain that will receive inbound emails:

```
Type: MX
Host: parse.yourdomain.com (or just "parse" depending on your DNS provider)
Value: mx.sendgrid.net
Priority: 10
TTL: 3600
```

**Example DNS Configuration:**
```
parse.yourdomain.com.  IN MX 10 mx.sendgrid.net.
```

### Configuring the Parse Webhook URL

1. Navigate to **Settings > Inbound Parse** in SendGrid dashboard
2. Click **Add Host & URL**
3. Configure the following:

| Setting | Value |
|---------|-------|
| Receiving Domain | `parse.yourdomain.com` |
| Destination URL | `https://api.yourdomain.com/webhooks/inbound-email` |
| Check incoming emails for spam | Enabled (recommended) |
| POST the raw, full MIME message | Disabled (we use parsed format) |

### Required Settings Explained

- **Destination URL**: Your backend webhook endpoint
  ```
  https://api.yourdomain.com/webhooks/inbound-email
  ```

- **POST the raw, full MIME message**: Keep **disabled**
  - When disabled, SendGrid parses the email and sends form fields
  - Our endpoint expects `multipart/form-data` with fields: `to`, `from`, `subject`, `text`, `html`, `envelope`

- **Check incoming emails for spam**: **Enable**
  - Adds spam scoring to incoming emails
  - Helps filter out unwanted messages

### Email Flow

When an email is sent to `reply@parse.yourdomain.com`:
1. SendGrid receives it via the MX record
2. SendGrid parses the email
3. SendGrid POSTs the parsed data to your webhook
4. Your endpoint processes the reply

---

## 3. Event Webhook Configuration

The Event Webhook notifies your system about email delivery events (bounces, spam reports, etc.).

### Events to Enable

Navigate to **Settings > Mail Settings > Event Webhook** and enable:

| Event | Description | Action in System |
|-------|-------------|------------------|
| **Bounce** | Email permanently rejected | Add to do-not-contact list |
| **Dropped** | Email dropped before sending (previous bounce/spam) | Add to do-not-contact list |
| **Spam Report** | Recipient marked email as spam | Add to do-not-contact list |
| **Unsubscribe** | Recipient clicked unsubscribe link | Add to do-not-contact list |
| **Blocked** | Email blocked by receiving server | Add to do-not-contact list |

**Optional events (for analytics):**
- Delivered
- Opened
- Clicked

### Webhook URL Configuration

Configure the Event Webhook:

1. **HTTP Post URL**:
   ```
   https://api.yourdomain.com/webhooks/sendgrid-events
   ```

2. **Actions to be posted**: Select the events listed above

3. **Security settings**:
   - Enable **Signed Event Webhook Requests** (see below)

### Signature Verification Setup

SendGrid supports signed webhooks to verify that requests originate from SendGrid.

#### Enable Signed Webhooks

1. In **Event Webhook** settings, enable **Signed Event Webhook Requests**
2. Copy the **Verification Key** provided by SendGrid
3. Add this key to your environment as `SENDGRID_WEBHOOK_VERIFICATION_KEY`

#### Current Implementation Note

The current implementation uses a custom `X-Webhook-Secret` header for verification. For production, consider implementing SendGrid's native signature verification:

```python
from sendgrid.helpers.eventwebhook import EventWebhook, EventWebhookHeader

def verify_sendgrid_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    public_key: str
) -> bool:
    """Verify SendGrid webhook signature"""
    event_webhook = EventWebhook()
    ec_public_key = event_webhook.convert_public_key_to_ecdsa(public_key)
    return event_webhook.verify_signature(
        payload,
        signature,
        timestamp,
        ec_public_key
    )
```

---

## 4. Environment Variables

Add these environment variables to your `.env` file:

### Required Variables

```bash
# SendGrid API Key (from Step 1)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# From address for outbound emails (must be verified domain)
SENDGRID_FROM_EMAIL=outreach@yourdomain.com

# Display name for outbound emails
SENDGRID_FROM_NAME=Your Company Name

# Webhook authentication secret (generate a secure random string)
WEBHOOK_SECRET=your-secure-random-string-here
```

### Optional Variables (for enhanced security)

```bash
# SendGrid webhook signature verification key (from Event Webhook settings)
SENDGRID_WEBHOOK_VERIFICATION_KEY=MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...

# Reply-to domain for inbound parse
SENDGRID_INBOUND_DOMAIN=parse.yourdomain.com
```

### Generating a Secure Webhook Secret

```bash
# Option 1: Using openssl
openssl rand -hex 32

# Option 2: Using Python
python -c "import secrets; print(secrets.token_hex(32))"

# Option 3: Using /dev/urandom
head -c 32 /dev/urandom | base64
```

### Example .env File

```bash
# Security
API_KEY=your-api-key-for-internal-endpoints
WEBHOOK_SECRET=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

# SendGrid
SENDGRID_API_KEY=SG.abcdefghijklmnop.qrstuvwxyz123456789
SENDGRID_FROM_EMAIL=outreach@yourdomain.com
SENDGRID_FROM_NAME=Expert Outreach

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/expert_outreach

# Redis
REDIS_URL=redis://localhost:6379/0
```

---

## 5. Testing Webhooks Locally

### Using ngrok for Local Development

[ngrok](https://ngrok.com) creates a public URL that tunnels to your local server.

#### Step 1: Install ngrok

```bash
# macOS with Homebrew
brew install ngrok

# Or download from https://ngrok.com/download
```

#### Step 2: Start Your Local Server

```bash
cd /Users/hurleywhite/expert-outreach/backend
uvicorn app.main:app --reload --port 8000
```

#### Step 3: Start ngrok Tunnel

```bash
ngrok http 8000
```

You'll see output like:
```
Forwarding    https://abc123.ngrok.io -> http://localhost:8000
```

#### Step 4: Configure SendGrid with ngrok URL

Temporarily update your SendGrid webhook URLs:
- Inbound Parse: `https://abc123.ngrok.io/webhooks/inbound-email`
- Event Webhook: `https://abc123.ngrok.io/webhooks/sendgrid-events`

### Test Payloads

#### Inbound Email Test

Send a test request to simulate an inbound email:

```bash
curl -X POST "http://localhost:8000/webhooks/inbound-email" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "to=reply%40parse.yourdomain.com" \
  -d "from=expert%40example.com" \
  -d "subject=Re%3A%20Project%20Opportunity" \
  -d "text=I%20would%20love%20to%20discuss%20this%20further.%20Let%27s%20schedule%20a%20call." \
  -d "envelope=%7B%22to%22%3A%5B%22reply%40parse.yourdomain.com%22%5D%2C%22from%22%3A%22expert%40example.com%22%7D"
```

#### Bounce Event Test

```bash
curl -X POST "http://localhost:8000/webhooks/sendgrid-events" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "email": "bounced@example.com",
      "timestamp": 1704067200,
      "event": "bounce",
      "sg_message_id": "abc123.xyz",
      "reason": "550 User unknown",
      "status": "5.0.0"
    }
  ]'
```

#### Spam Report Event Test

```bash
curl -X POST "http://localhost:8000/webhooks/sendgrid-events" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "email": "complained@example.com",
      "timestamp": 1704067200,
      "event": "spamreport",
      "sg_message_id": "def456.xyz"
    }
  ]'
```

#### Unsubscribe Event Test

```bash
curl -X POST "http://localhost:8000/webhooks/sendgrid-events" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "email": "unsubscribed@example.com",
      "timestamp": 1704067200,
      "event": "unsubscribe",
      "sg_message_id": "ghi789.xyz"
    }
  ]'
```

#### Dropped Event Test

```bash
curl -X POST "http://localhost:8000/webhooks/sendgrid-events" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "email": "dropped@example.com",
      "timestamp": 1704067200,
      "event": "dropped",
      "sg_message_id": "jkl012.xyz",
      "reason": "Bounced Address"
    }
  ]'
```

#### Multiple Events Test

SendGrid batches events, so test with multiple events:

```bash
curl -X POST "http://localhost:8000/webhooks/sendgrid-events" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '[
    {"email": "user1@example.com", "event": "delivered", "timestamp": 1704067200},
    {"email": "user2@example.com", "event": "bounce", "timestamp": 1704067201, "reason": "550 User unknown"},
    {"email": "user3@example.com", "event": "spamreport", "timestamp": 1704067202}
  ]'
```

---

## 6. Production Checklist

### DNS Records

- [ ] **MX Record** for inbound parse subdomain points to `mx.sendgrid.net`
- [ ] **CNAME Records** for DKIM authentication are configured
- [ ] **SPF Record** includes `sendgrid.net`
- [ ] **DMARC Record** is configured (recommended)
  ```
  _dmarc.yourdomain.com. IN TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com"
  ```
- [ ] All DNS records have propagated (verify with `dig` or online tools)

### SSL/TLS Requirements

- [ ] Webhook endpoints are served over **HTTPS only**
- [ ] Valid SSL certificate (not self-signed) for production
- [ ] TLS 1.2 or higher enforced
- [ ] Certificate auto-renewal configured (e.g., Let's Encrypt with certbot)

### SendGrid Configuration

- [ ] Domain authentication completed and verified
- [ ] API key created with minimal required permissions
- [ ] Inbound Parse webhook URL configured
- [ ] Event Webhook URL configured
- [ ] Signed webhooks enabled (recommended)
- [ ] IP Access Management configured (if applicable)

### Environment Variables

- [ ] `SENDGRID_API_KEY` is set and valid
- [ ] `SENDGRID_FROM_EMAIL` uses verified domain
- [ ] `WEBHOOK_SECRET` is a strong, unique value
- [ ] All secrets are stored securely (not in version control)

### Application Configuration

- [ ] Webhook endpoints are accessible from SendGrid's IPs
- [ ] Error handling and logging configured for webhook failures
- [ ] Database connection pooling configured for high throughput
- [ ] Rate limiting on webhook endpoints (prevent abuse)

### Monitoring Recommendations

1. **SendGrid Activity Feed**
   - Monitor bounce rates (should be < 2%)
   - Monitor spam complaint rates (should be < 0.1%)
   - Set up alerts for unusual activity

2. **Application Monitoring**
   - Log all webhook requests (with appropriate redaction)
   - Track webhook processing latency
   - Alert on webhook processing failures
   - Monitor do-not-contact list growth

3. **Recommended Alerts**
   - Bounce rate exceeds threshold
   - Spam complaint rate exceeds threshold
   - Webhook endpoint returning errors
   - High latency on webhook processing

4. **SendGrid Email Statistics**
   ```bash
   # Fetch recent stats via API
   curl --request GET \
     --url "https://api.sendgrid.com/v3/stats?start_date=2024-01-01" \
     --header "Authorization: Bearer $SENDGRID_API_KEY"
   ```

### Security Best Practices

- [ ] Rotate API keys periodically
- [ ] Use separate API keys for staging and production
- [ ] Implement webhook signature verification
- [ ] Log authentication failures
- [ ] Rate limit webhook endpoints
- [ ] Validate all incoming data before processing

### Testing Before Go-Live

1. Send test emails through the system
2. Verify inbound parse processes replies correctly
3. Simulate bounce/spam events with test payloads
4. Confirm do-not-contact entries are created
5. Verify email threading works correctly
6. Test unsubscribe flow end-to-end

---

## Troubleshooting

### Common Issues

**Inbound emails not being received:**
- Verify MX record is correct: `dig MX parse.yourdomain.com`
- Check SendGrid Inbound Parse activity log
- Ensure webhook URL is accessible from internet

**Event webhooks not triggering:**
- Verify webhook URL is HTTPS
- Check Event Webhook settings in SendGrid
- Review SendGrid Activity Feed for delivery attempts

**Authentication failures:**
- Verify `X-Webhook-Secret` header matches environment variable
- Check for trailing whitespace in secrets

**Emails going to spam:**
- Verify domain authentication (SPF, DKIM)
- Check sender reputation in SendGrid
- Review email content for spam triggers

### Useful Commands

```bash
# Test MX record
dig MX parse.yourdomain.com

# Test DNS propagation
dig TXT yourdomain.com +short | grep sendgrid

# Test webhook endpoint
curl -I https://api.yourdomain.com/webhooks/sendgrid-events

# Check SSL certificate
openssl s_client -connect api.yourdomain.com:443 -servername api.yourdomain.com
```

---

## Support Resources

- [SendGrid Documentation](https://docs.sendgrid.com/)
- [SendGrid Inbound Parse Guide](https://docs.sendgrid.com/for-developers/parsing-email/setting-up-the-inbound-parse-webhook)
- [SendGrid Event Webhook Guide](https://docs.sendgrid.com/for-developers/tracking-events/getting-started-event-webhook)
- [SendGrid API Reference](https://docs.sendgrid.com/api-reference)
