# External Auth — Implementation TODO

_Generated 2026-04-15 from research in `sharepoint-external-auth/synthesis.org`_

---

## Recommended path: try in this order

### Option C — B2B Guest + Email OTP (try first, zero code changes)

If external users are willing to receive a one-time passcode by email, this
requires no code changes at all — they just sign in through the existing
DeviceCode flow.

**Steps (all in Azure Portal / Entra, ~10 min):**

1. **Enable email OTP for guests**
   - Portal → Entra ID → External Identities → External collaboration settings
   - Set "Email one-time passcode for guests" → **Enabled**

2. **Invite each external collaborator**
   - Portal → Entra ID → Users → New guest user
   - Enter their email address, send invitation
   - They receive an email, click the link, and get an OTP — no Microsoft
     account required

3. **Test**: have a guest user run the app and authenticate via DeviceCode.
   Their experience: browser opens → they enter their email → they enter the
   OTP from their inbox → done. Your existing `auth/internal.py` handles
   everything from here.

**If this works: you're done. No Azure Function, no API keys, no Blob Storage.**

**Known risk**: some organisations block B2B guest invitations via Entra
Conditional Access or tenant policies. Test before committing.

---

### Option B — Azure Function → Blob Storage (if B2B doesn't work)

No SharePoint permissions, no Graph API, no Entra app registration needed
beyond the Function itself. The desktop app (`auth/external.py`) is already
written for this — you just need to deploy the Function and fill in two values.

#### Desktop-app side (code already done)

- `auth/external.py` is complete
- Fill in `_DEFAULT_FUNCTION_URL` with your deployed function URL, e.g.:
  ```python
  _DEFAULT_FUNCTION_URL = "https://odi-annotations.azurewebsites.net/api/upload"
  ```
- Distribute a per-user API key to each external collaborator (any random
  string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- They enter it once on first launch; it's saved to `<auth_dir>/external_config.json`

#### Azure setup

1. **Create a Storage Account**
   - Portal → Storage accounts → Create
   - Create a container named `pelvic-2d-points-backup`, access level: Private
   - Copy the connection string (Settings → Access keys)

2. **Create an Azure Function App**
   - Portal → Function Apps → Create
   - Runtime: Python 3.11+, plan: Consumption (free tier for this volume)
   - Add application settings (env vars):
     - `STORAGE_CONN` = the connection string from step 1
     - `ANNOTATOR_API_KEYS` = comma-separated list of valid keys, e.g.
       `key-for-alice,key-for-bob,key-for-carol`
       (or use a single shared key if audit trail per-user isn't needed)

3. **Deploy the Function** — `function_app.py`:

   ```python
   import json
   import logging
   import os
   from datetime import datetime

   import azure.functions as func
   from azure.storage.blob import BlobServiceClient

   app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

   def _valid_key(key: str) -> bool:
       allowed = {k.strip() for k in os.environ.get("ANNOTATOR_API_KEYS", "").split(",")}
       return bool(key) and key in allowed

   @app.route(route="upload", methods=["PUT"])
   def upload(req: func.HttpRequest) -> func.HttpResponse:
       api_key = req.headers.get("X-API-Key", "")
       if not _valid_key(api_key):
           logging.warning("Rejected upload: bad API key")
           return func.HttpResponse("Unauthorized", status_code=401)

       username = req.headers.get("X-Username", "unknown")
       filename = req.headers.get("X-Filename", "upload.json")
       date = datetime.now().strftime("%Y-%m-%d")
       blob_name = f"{username}/{date}/{filename}"

       try:
           conn = os.environ["STORAGE_CONN"]
           client = BlobServiceClient.from_connection_string(conn)
           container = client.get_container_client("pelvic-2d-points-backup")
           container.upload_blob(blob_name, req.get_body(), overwrite=True)
           logging.info("Uploaded %s", blob_name)
           return func.HttpResponse(
               json.dumps({"status": "ok", "blob": blob_name}),
               status_code=200,
               mimetype="application/json",
           )
       except Exception as e:
           logging.error("Upload failed: %s", e)
           return func.HttpResponse("Upload failed", status_code=500)
   ```

4. **requirements.txt** for the Function:
   ```
   azure-functions
   azure-storage-blob
   ```

5. **Test locally** with Azure Functions Core Tools:
   ```bash
   # In the function directory:
   func start
   # Then in the app:
   ANNOTATOR_FUNCTION_URL=http://localhost:7071/api/upload \
   ANNOTATOR_API_KEY=test-key \
   ANNOTATOR_DEV_MODE=0 \
   pixi run annotator
   ```

---

### Option A — Azure Function → SharePoint (if you want to stay on SharePoint)

Same desktop-app code as Option B. The Function uses `ClientSecretCredential`
and the MS Graph API instead of Blob Storage. More moving parts.

#### Azure / Entra setup

1. **Create a new App Registration** for the Function (separate from the
   existing DeviceCode registration in `internal.py`):
   - Portal → Entra ID → App registrations → New registration
   - Note the Application (client) ID and Directory (tenant) ID
   - Add a client secret (Certificates & secrets → New client secret); set
     expiry to 12 months and calendar a rotation reminder

2. **Grant `Sites.Selected` permission** (Application, not Delegated):
   - App registration → API permissions → Add permission → Microsoft Graph →
     Application permissions → `Sites.Selected`
   - Click "Grant admin consent for [tenant]" (requires Global Admin)

3. **Assign write access to just your SharePoint site** (PowerShell, one-time):
   ```powershell
   Connect-MgGraph -Scopes "Sites.FullControl.All"

   $appClientId = "<YOUR_FUNCTION_APP_CLIENT_ID>"
   $app = Get-MgServicePrincipal -Filter "appId eq '$appClientId'"
   $graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
   $sitesSelected = $graphSp.AppRoles | Where-Object {
       $_.Value -eq "Sites.Selected" -and $_.AllowedMemberTypes -contains "Application"
   }
   New-MgServicePrincipalAppRoleAssignment `
       -ServicePrincipalId $app.Id `
       -AppRoleId $sitesSelected.Id `
       -ResourceId $graphSp.Id `
       -PrincipalId $app.Id

   # Grant site-level write:
   $siteId = "<your-sharepoint-site-id>"   # from internal.py / SharePoint URL
   $body = @{
       roles = @("write")
       grantedToIdentities = @(@{ application = @{ id = $appClientId } })
   }
   Invoke-MgGraphRequest -Method POST `
       -Uri "https://graph.microsoft.com/v1.0/sites/$siteId/permissions" `
       -Body $body
   ```

4. **Function app settings** (env vars):
   - `TENANT_ID` = your tenant ID
   - `CLIENT_ID` = the Function's app registration client ID
   - `CLIENT_SECRET` = the secret created in step 1 (or fetch from Key Vault)
   - `SHAREPOINT_DRIVE_ID` = same value as in `internal.py`
   - `ANNOTATOR_API_KEYS` = comma-separated user API keys

5. **Function code** — same structure as Option B but replace the Blob upload
   with a Graph API PUT:
   ```python
   from azure.identity import ClientSecretCredential
   
   def _get_graph_token() -> str:
       cred = ClientSecretCredential(
           tenant_id=os.environ["TENANT_ID"],
           client_id=os.environ["CLIENT_ID"],
           client_secret=os.environ["CLIENT_SECRET"],
       )
       return cred.get_token("https://graph.microsoft.com/.default").token
   
   # In the upload handler:
   token = _get_graph_token()
   drive_id = os.environ["SHAREPOINT_DRIVE_ID"]
   url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/root:/{blob_name}:/content"
   import requests
   resp = requests.put(url, data=file_bytes,
                       headers={"Authorization": f"Bearer {token}",
                                "Content-Type": "application/octet-stream"})
   ```

---

## Testing the external path locally (no Azure needed)

```bash
# Dev mode: files go to <auth_dir>/dev_uploads/ instead of any cloud resource
ANNOTATOR_DEV_MODE=1 pixi run annotator
```

On first launch with no saved user type, you'll see the "internal or external"
dialog. Pick **external**. Since dev mode is on, uploads copy files to disk —
no API key, no network.

**Reset the user type choice:**
```bash
python -c "import sys; sys.path.insert(0,'src'); from auth.selector import clear_user_type; clear_user_type()"
```

**Run the tests (fully offline):**
```bash
pixi run python -m pytest tests/test_external_auth.py -v
```

---

## Things NOT to do (from research)

- **Do not distribute a shared client secret** to external users (embedded in
  binary or typed in by hand). Microsoft explicitly prohibits this for desktop
  apps and it provides no meaningful security.
- **Do not use `Sites.ReadWrite.All` (Application)** — it grants access to
  every SharePoint site in the tenant. Use `Sites.Selected` instead.
- **Do not use `Files.ReadWrite.All` (Application)** for app-only auth for the
  same reason.
