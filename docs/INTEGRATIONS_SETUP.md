# Zenith — Art & Design Integrations Setup Guide

This guide explains how to set up, configure, and use the **Figma** and **Canva** OAuth integrations in Zenith, as well as the **Figma Plugin Bridge**.

---

## 1. Figma Integration Setup

### A. Register a Figma Developer Application
1. Go to the [Figma Developer Apps Portal](https://www.figma.com/developers/apps).
2. Click **Create a new app**.
3. Fill in the App details:
   - **Name**: `Zenith AI Assistant`
   - **Website URL**: `http://localhost:8005` (or your domain)
   - **Callback URL**: `http://localhost:8005/api/integrations/figma/callback`
4. Copy your **Client ID** and **Client Secret**.

### B. Configure Scopes
Ensure your Figma app requests the following minimum scopes:
- `current_user:read` — Access basic user profile (id, name/email)
- `file_content:read` — Read Figma design files, layers, styles, and nodes

### C. Configure in Zenith
Add the following to your `.env` file or enter them in Zenith Settings → **Art & Design**:
```env
FIGMA_CLIENT_ID="your_figma_client_id"
FIGMA_CLIENT_SECRET="your_figma_client_secret"
FIGMA_REDIRECT_URI="http://localhost:8005/api/integrations/figma/callback"
```

---

## 2. Canva Connect Integration Setup

### A. Register a Canva Developer Integration
1. Go to the [Canva Developer Portal](https://www.canva.dev/).
2. Create a new integration under **Developer Portal → Integrations**.
3. Configure the integration settings:
   - **App Name**: `Zenith AI Assistant`
   - **Redirect URI**: `http://localhost:8005/api/integrations/canva/callback`
   - **Auth Type**: OAuth 2.0 with PKCE (S256)
4. Copy your **Client ID** and **Client Secret**.

### B. Configure Scopes
Ensure your Canva integration requests the following scopes:
- `design:content:read` — Read design content and elements
- `design:meta:read` — Read metadata of user designs
- `profile:read` — Access user profile info

### C. Configure in Zenith
Add the following to your `.env` file or enter them in Zenith Settings → **Art & Design**:
```env
CANVA_CLIENT_ID="your_canva_client_id"
CANVA_CLIENT_SECRET="your_canva_client_secret"
CANVA_REDIRECT_URI="http://localhost:8005/api/integrations/canva/callback"
```

---

## 3. Connecting Your Accounts in Zenith

1. Open Zenith and navigate to **Settings** (`/` → Gear Icon).
2. Click on the **Art & Design** category.
3. You will see cards for **Figma** and **Canva**.
4. Click **Connect Figma** or **Connect Canva**.
5. You will be redirected to the provider's consent page to authorize Zenith.
6. Once authorized, you will be returned to Zenith and the connection status will update to **Connected**.

---

## 4. Figma Plugin Bridge Setup

Because Figma's REST API is read-only for file structure, modifying files or creating new components requires the **Figma Plugin API**. Zenith includes a native Figma Plugin Bridge.

### Installing the Plugin in Figma
1. Open Figma (Desktop or Web).
2. Go to **Plugins → Development → Import plugin from manifest...**.
3. Select the file: `figma-plugin/manifest.json` (or `zenith/integrations/figma/plugin/manifest.json`).
4. Run the plugin in any Figma document.
5. The plugin connects to Zenith's WebSocket endpoint (`ws://localhost:8005/ws/figma-plugin`).
6. You can now use AI commands like:
   - *"Create a landing page layout in Figma with a headline, subtitle, and CTA button."*
   - *"Add a dark mode card component to the current frame."*

---

## 5. Security & Token Lifecycle

- **Token Encryption**: All OAuth tokens (`access_token`, `refresh_token`) are encrypted at rest using AES-128-CBC (Fernet) derived from `SESSION_SECRET`.
- **PKCE Support**: Canva OAuth uses PKCE (Proof Key for Code Exchange) with SHA-256 challenges to prevent authorization code injection.
- **CSRF Protection**: Every authorization flow uses a cryptographically secure, single-use state token with a 10-minute expiration.
- **Token Security**: Raw access tokens are never returned to the frontend UI; status APIs only expose connection state and metadata.

---

## 6. Verification & Troubleshooting

To run the integration test suite:
```bash
python -m pytest tests/test_integrations.py -v
```

If connection fails:
1. Verify `FIGMA_REDIRECT_URI` / `CANVA_REDIRECT_URI` match the exact URI registered in the provider portal.
2. Check Zenith server logs for error details.
3. Use the **Disconnect** button in Settings → Art & Design to clear existing tokens and re-authorize.
