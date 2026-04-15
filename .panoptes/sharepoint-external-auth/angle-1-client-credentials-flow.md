Perfect. Now let me compile the comprehensive research findings:

---

## DEEP RESEARCH: MS Graph Client Credentials Flow for SharePoint File Operations

**Angle Type**: Conceptual / Docs  
**Confidence Levels**: HIGH for protocol/permissions, MEDIUM for desktop app security implications  
**Current Date**: April 15, 2026

---

## EXECUTIVE SUMMARY

**The short answer**: YES, client credentials flow works for SharePoint file uploads via MS Graph. **BUT** embedding a client secret in a desktop app distributed to external users is a **critical security anti-pattern** that Microsoft explicitly warns against.

---

## 1. HOW ClientSecretCredential WORKS IN AZURE-IDENTITY

### Python Implementation

**Evidence** ([azure-identity docs](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential?view=azure-python)):

```python
from azure.identity import ClientSecretCredential
from azure.identity import AzureAuthorityHosts

# Create credential with client secret
credential = ClientSecretCredential(
    tenant_id="<tenant_id>",
    client_id="<client_id>",
    client_secret="<client_secret>",
    authority=AzureAuthorityHosts.AZURE_PUBLIC_CLOUD  # Optional
)

# Get access token (called automatically by msgraph SDK)
token = credential.get_token("https://graph.microsoft.com/.default")
```

**How it works**:
- `ClientSecretCredential` implements OAuth 2.0 client credentials grant flow
- Sends `client_id` + `client_secret` to Entra ID token endpoint
- Receives bearer token with **application permissions** (not delegated)
- Token contains `roles` claim (not `scp` claim) — this is the key difference
- **No user sign-in required** — app authenticates as itself

**Confidence**: HIGH — This is official Microsoft documentation.

---

## 2. APPLICATION PERMISSIONS FOR SHAREPOINT FILE OPERATIONS

### Required Permissions (NOT Delegated)

**Evidence** ([MS Graph file upload docs](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0)):

| Operation | Least Privileged | Higher Privileged |
|-----------|------------------|-------------------|
| **Application** (app-only) | `Files.ReadWrite.All` | `Sites.ReadWrite.All` |
| **Delegated** (user-based) | `Files.ReadWrite` | `Files.ReadWrite.All` |

**For your scenario (external users, no sign-in)**:
- Use **Application permission**: `Files.ReadWrite.All`
- Alternative (more restrictive): `Sites.Selected` (requires per-site admin grant)

**Key distinction** ([Entra ID docs](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/application-delegated-permission-access-tokens-identity-platform)):

```
Delegated permissions (scp claim):
  - App acts ON BEHALF OF signed-in user
  - Intersection of app permissions + user permissions
  - User must have access to the resource

Application permissions (roles claim):
  - App acts AS ITSELF, no user involved
  - App has full access to what permission grants
  - Admin consent ALWAYS required
```

**Confidence**: HIGH — Official Microsoft Graph API reference.

---

## 3. ADMIN CONSENT REQUIREMENTS

### How Application Permissions Get Granted

**Evidence** ([OAuth 2.0 client credentials flow docs](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)):

**Step 1: Configure permissions in app registration**
```
Azure Portal → App Registrations → Your App → API Permissions
→ Add Permission → Microsoft Graph → Application permissions
→ Select: Files.ReadWrite.All
→ Click "Grant admin consent for [tenant]"
```

**Step 2: Admin consent endpoint (if you want to build a consent flow)**
```
GET https://login.microsoftonline.com/{tenant}/adminconsent
?client_id=YOUR_CLIENT_ID
&redirect_uri=https://localhost/callback
&state=12345
```

**Step 3: Token request (no user interaction)**
```http
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id=YOUR_CLIENT_ID
&scope=https://graph.microsoft.com/.default
&client_secret=YOUR_CLIENT_SECRET
&grant_type=client_credentials
```

**Response**:
```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6Ik1uQ19WWmNBVGZNNXBP..."
}
```

**Confidence**: HIGH — Official OAuth 2.0 protocol documentation.

---

## 4. PYTHON CODE EXAMPLE: CLIENT CREDENTIALS + MSGRAPH SDK

**Evidence** (synthesized from [MS Graph service auth docs](https://learn.microsoft.com/en-us/graph/auth-v2-service) + azure-identity):

```python
from azure.identity import ClientSecretCredential
from msgraph.core import GraphClient
from azure.core.exceptions import ClientAuthenticationError

# Configuration
TENANT_ID = "your-tenant-id"
CLIENT_ID = "your-app-id"
CLIENT_SECRET = "your-app-password"  # ⚠️ SECURITY RISK if embedded
SITE_ID = "sharepoint-site-id"
DRIVE_ID = "sharepoint-drive-id"

def upload_file_app_only(file_path: str, file_name: str) -> dict:
    """Upload file to SharePoint using app-only (client credentials) auth."""
    
    try:
        # 1. Create credential (no user sign-in)
        credential = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        
        # 2. Create Graph client
        client = GraphClient(credential=credential)
        
        # 3. Read file to upload
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # 4. Upload to SharePoint
        # PUT /sites/{site-id}/drive/items/{parent-id}:/{filename}:/content
        upload_url = f"/sites/{SITE_ID}/drive/items/root:/{file_name}:/content"
        
        response = client.put(
            upload_url,
            content=file_content,
            headers={"Content-Type": "application/octet-stream"}
        )
        
        return response.json()
    
    except ClientAuthenticationError as e:
        print(f"Auth failed: {e}")
        # Likely causes:
        # - Invalid client_secret
        # - Client secret expired
        # - App not granted Files.ReadWrite.All permission
        # - Admin consent not granted
        raise

# Usage
result = upload_file_app_only("local_file.pdf", "uploaded_file.pdf")
print(f"Uploaded: {result['id']}")
```

**Confidence**: HIGH — Follows official patterns from MS docs.

---

## 5. PERMISSION MODEL: APP ACTS AS ITSELF

**Evidence** ([Entra ID permissions overview](https://learn.microsoft.com/en-us/entra/identity-platform/permissions-consent-overview)):

```
┌─────────────────────────────────────────────────────────────┐
│ DELEGATED (Current Implementation)                          │
├─────────────────────────────────────────────────────────────┤
│ User signs in → App acts ON BEHALF OF user                  │
│ Permissions = MIN(app permissions, user permissions)        │
│ Example: User can read 5 files → App can read those 5       │
│ Scope claim: "scp": "Files.ReadWrite.All"                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ APPLICATION (Client Credentials)                            │
├─────────────────────────────────────────────────────────────┤
│ No user sign-in → App acts AS ITSELF                         │
│ Permissions = What admin granted to app                     │
│ Example: App can read ALL files in tenant                   │
│ Roles claim: "roles": ["Files.ReadWrite.All"]               │
└─────────────────────────────────────────────────────────────┘
```

**Key insight**: With application permissions, the app has **unrestricted access** to what the permission grants. There's no user-level filtering.

**Confidence**: HIGH — Official Microsoft documentation.

---

## 6. CRITICAL SECURITY ISSUE: EMBEDDING CLIENT SECRET IN DESKTOP APP

### The Problem

**Evidence** ([OAuth 2.0 client credentials flow docs](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)):

> "Because the application's own credentials are being used, these credentials must be kept safe. **Never publish that credential in your source code, embed it in web pages, or use it in a widely distributed native application.**"

### Why This Is Dangerous

1. **Credential Extraction**
   - Desktop apps are easily decompiled (Python bytecode, .NET IL, etc.)
   - External users can extract the client secret from the app binary
   - Secret is now compromised for ALL users

2. **Impersonation**
   - Anyone with the secret can authenticate as your app
   - They can upload/delete files in your SharePoint tenant
   - No audit trail linking actions to specific users

3. **Revocation Nightmare**
   - If one user's copy is compromised, you must rotate the secret
   - All distributed copies become invalid
   - Users can't work until they get the new version

4. **Compliance Violations**
   - HIPAA/GDPR require audit trails linking actions to individuals
   - Shared app credentials break this requirement
   - Medical annotation app = high compliance risk

**Confidence**: HIGH — This is explicit Microsoft guidance.

---

## 7. WHAT YOU COULD NOT FIND / VERIFY

❌ **No official Microsoft guidance** on "distributing client secrets to external users"  
❌ **No documented pattern** for "user-provided app password" scenario  
❌ **No security analysis** of embedding secrets in Tkinter apps specifically  

**Interpretation**: Microsoft doesn't document this because it's **not a supported pattern**. The absence of guidance is itself a signal.

---

## 8. ALTERNATIVE APPROACHES (NOT CLIENT CREDENTIALS)

### Option A: Device Code Flow (Current)
- ✅ Each user signs in with their own account
- ✅ No shared credentials
- ✅ Full audit trail
- ❌ Requires users to have Microsoft accounts in your tenant

### Option B: Client Credentials + Managed Identity (Azure-hosted only)
- ✅ Secret stored in Azure Key Vault, not in app
- ✅ No credential distribution needed
- ❌ Only works if app runs on Azure (not desktop)

### Option C: Federated Credentials (Workload Identity)
- ✅ No client secret needed
- ✅ Uses external identity provider (GitHub, Kubernetes, etc.)
- ❌ Complex setup, not suitable for desktop users

### Option D: Refresh Token + Delegated Permissions
- ✅ User signs in once, app stores refresh token
- ✅ App acts on behalf of user (delegated)
- ✅ Audit trail preserved
- ❌ Requires initial user sign-in

**Confidence**: HIGH — These are documented Microsoft patterns.

---

## 9. TOKEN CLAIMS: HOW TO VERIFY PERMISSION TYPE

**Evidence** ([Entra ID token claims docs](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/application-delegated-permission-access-tokens-identity-platform)):

Decode token at [jwt.ms](https://jwt.ms) to inspect claims:

```json
// APPLICATION PERMISSION TOKEN (client credentials)
{
  "oid": "00000000-0000-0000-0000-000000000000",
  "roles": ["Files.ReadWrite.All"],  // ← Application permissions here
  "sub": "...",
  "appid": "YOUR_CLIENT_ID"
  // NOTE: NO "scp" claim
}

// DELEGATED PERMISSION TOKEN (user sign-in)
{
  "scp": "Files.ReadWrite.All",  // ← Delegated permissions here
  "sub": "...",
  "upn": "user@tenant.onmicrosoft.com"
  // NOTE: "roles" might exist but lists user's Azure roles, not app permissions
}
```

**Confidence**: HIGH — Official Microsoft documentation.

---

## 10. ENTRA ID ADMIN CONSENT FLOW

### Who Can Grant Consent?

**Evidence** ([MS Graph service auth docs](https://learn.microsoft.com/en-us/graph/auth-v2-service)):

- **Global Administrator** (required for Microsoft Graph application permissions)
- **Privileged Role Administrator** (for some APIs)
- **Application Administrator** (for third-party APIs only, NOT Microsoft Graph)

### Consent Persistence

- Once granted, consent is **permanent** until revoked
- Stored in Entra ID as `appRoleAssignment` object
- Survives app updates (no re-consent needed)
- Can be revoked by admin at any time

**Confidence**: HIGH — Official documentation.

---

## SUMMARY TABLE: CLIENT CREDENTIALS FOR YOUR SCENARIO

| Aspect | Status | Evidence |
|--------|--------|----------|
| **Does it work for SharePoint uploads?** | ✅ YES | MS Graph file upload API supports `Files.ReadWrite.All` application permission |
| **Can desktop app use it?** | ✅ YES | `ClientSecretCredential` works in Python 3.13 + Tkinter |
| **Required permissions** | `Files.ReadWrite.All` (application) | MS Graph API reference |
| **Admin consent required?** | ✅ YES, always | OAuth 2.0 client credentials flow docs |
| **Can you embed secret in app?** | ❌ NO, explicitly forbidden | Microsoft: "Never publish that credential in a widely distributed native application" |
| **Can external users provide password?** | ❌ NO, security risk | Credential extraction, impersonation, audit trail loss |
| **Audit trail preserved?** | ❌ NO | All actions appear as app, not individual users |
| **Compliant with HIPAA/GDPR?** | ❌ LIKELY NOT | Shared credentials break individual accountability |

---

## RECOMMENDATION FOR YOUR PROJECT

**Current approach (device code flow) is correct for your use case.**

**Why**:
1. Each annotator signs in with their own identity
2. Full audit trail (actions linked to individuals)
3. HIPAA/GDPR compliant
4. No credential distribution needed

**If you must support external users without Microsoft accounts**:
- **Do NOT** use client credentials with embedded secret
- **Instead**: Use **refresh token flow** (user signs in once, app stores refresh token securely)
- Or: Require external users to create Microsoft accounts (B2B invitation)

---

## WHAT YOU COULD NOT VERIFY

- **Exact security implications** of embedding secrets in Tkinter apps (no published analysis found)
- **Whether Microsoft has deprecated** client credentials for desktop apps (no explicit deprecation notice found, but strong discouragement)
- **Specific attack vectors** for extracting secrets from Python bytecode (general knowledge, not MS-specific)

---

## SOURCES

1. [OAuth 2.0 Client Credentials Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow) — Microsoft Entra ID docs
2. [Get Access Without a User (MS Graph)](https://learn.microsoft.com/en-us/graph/auth-v2-service) — Microsoft Graph docs
3. [Permissions and Consent Overview](https://learn.microsoft.com/en-us/entra/identity-platform/permissions-consent-overview) — Microsoft Entra ID docs
4. [Application vs Delegated Permissions](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/application-delegated-permission-access-tokens-identity-platform) — Microsoft troubleshooting guide
5. [azure-identity ClientSecretCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential?view=azure-python) — Azure SDK for Python
6. [MS Graph File Upload API](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0) — Microsoft Graph API reference

---

**Research completed**: April 15, 2026  
**Angle**: MS Graph Client Credentials Flow (Application Permissions)  
**Status**: ✅ COMPLETE with evidence links
