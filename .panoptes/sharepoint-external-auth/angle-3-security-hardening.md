Perfect. Now I have comprehensive evidence. Let me compile the security analysis document:

## SECURITY ANALYSIS: Distributing Client Credentials in Desktop Apps

**Research Angle 3 of 5: Security Risks & Hardening**  
**Confidence Levels: HIGH (Microsoft docs), MEDIUM (threat modeling), HIGH (alternatives)**

---

### EXECUTIVE SUMMARY

**The core problem**: Embedding a client secret in a distributed desktop app is **fundamentally incompatible with security best practices**. Microsoft's official guidance explicitly states:

> "Public client applications run on devices, such as desktop, browserless APIs, mobile or client-side browser apps. They can't be trusted to safely keep application secrets, so they can only access web APIs on behalf of the user."

**Your scenario**: Distributing an "application password" to external users who enter it into a desktop app violates this principle. Once the secret is in the binary or user's hands, it's compromised by design.

**Threat model**: A malicious user (or anyone who reverse-engineers the app) gains:
- Full access to all Graph API permissions granted to the app
- Ability to upload/modify/delete files in the designated SharePoint site
- Ability to impersonate the app indefinitely (no MFA, no Conditional Access)
- Ability to exfiltrate data or establish persistence

**Microsoft's official stance**: This is **not recommended**. The docs explicitly warn against this pattern.

---

### 1. THREAT MODEL: What Malicious Users Can Do

**Evidence**: [Microsoft Graph API Attack Surface (2026)](https://infosecwriteups.com/microsoft-graph-api-attack-surface-oauth-flows-abused-endpoints-and-what-defenders-miss-9c303ea2aa02)

#### Attack Surface

| Capability | Impact | Confidence |
|---|---|---|
| **Token generation without MFA** | Attacker obtains valid Graph token with no second factor | HIGH |
| **No Conditional Access enforcement** | Client credentials flow bypasses CA policies (app-only auth) | HIGH |
| **Unlimited token lifetime** | Tokens valid for 60 minutes; attacker can request new ones indefinitely | HIGH |
| **Broad permission scope** | If app has `Files.ReadWrite.All`, attacker can access all SharePoint sites | HIGH |
| **No audit trail linking to user** | Logs show app activity, not which user ran the app | MEDIUM |
| **Credential reuse across machines** | Same secret works on any device; attacker can distribute it further | HIGH |

#### Real-World Attack Chain

1. **Attacker obtains the secret** (reverse-engineer binary, intercept network, social engineering)
2. **Attacker generates Graph token** using client credentials flow
3. **Attacker uploads malicious files** to SharePoint or exfiltrates data
4. **Attacker maintains persistence** by requesting new tokens repeatedly
5. **Detection is delayed** because logs show legitimate app activity, not the attacker

**Evidence**: [Token Theft in Microsoft Entra ID (2026)](https://medium.com/@pramathu2018/token-theft-in-microsoft-entra-id-attack-mitigation-42e64f2feee4)

> "Because access tokens function as bearer credentials, possession of the token alone is sufficient to access the API until the token expires."

---

### 2. MICROSOFT'S OFFICIAL GUIDANCE ON DISTRIBUTING CREDENTIALS

**Evidence**: [Security Best Practices for App Registration](https://learn.microsoft.com/en-us/entra/identity-platform/security-best-practices-for-app-registration)

#### Key Quotes

**On desktop apps and secrets**:
> "If an application is used only as a public or installed client (for example, mobile or desktop apps that are installed on the end user machine), make sure that there are no credentials specified on the application object."

**On client secrets in general**:
> "Don't use password credentials, also known as secrets. While it's convenient to use password secrets as a credential, password credentials are often mismanaged and can be easily compromised."

**On the risks**:
> "Client secrets, when exposed, provide attackers with the ability to blend their activities with legitimate operations, making it easier to bypass security controls. If an attacker compromises an application's client secret, they can escalate their privileges within the system, leading to broader access and control, depending on the permissions of the application."

**Evidence**: [Zero Trust: Protect Identities and Secrets](https://learn.microsoft.com/en-us/entra/fundamentals/zero-trust-protect-identities)

> "Applications that use client secrets might store them in configuration files, hardcode them in scripts, or risk their exposure in other ways. The complexities of secret management make client secrets susceptible to leaks and attractive to attackers."

#### Microsoft's Recommended Approach for Desktop Apps

**For desktop apps, Microsoft recommends**:
1. **User-based authentication** (delegated permissions) — user signs in interactively
2. **Managed identities** (if running on Azure)
3. **Federated credentials** (GitHub Actions, Kubernetes, etc.)
4. **NOT client secrets**

**Evidence**: [Public and Confidential Client Apps (MSAL)](https://learn.microsoft.com/en-us/entra/identity-platform/msal-client-applications)

> "Public client applications run on devices... They can't be trusted to safely keep application secrets, so they can only access web APIs on behalf of the user."

---

### 3. CLIENT SECRET SCOPING & RATE-LIMITING

**Confidence: MEDIUM** (Microsoft doesn't provide granular scoping for individual secrets)

#### What CAN Be Scoped

| Control | Capability | Limitation |
|---|---|---|
| **App Roles** | Restrict which API permissions the app has | Applies to ALL secrets for that app; can't differentiate per-secret |
| **Conditional Access** | Block app-only auth from certain locations/devices | Does NOT apply to client credentials flow (app-only auth is exempt) |
| **Application Management Policies** | Enforce max secret lifetime (e.g., 12 months) | Tenant-wide or per-app; not per-secret |
| **Multiple Secrets** | Create separate secrets with different lifetimes | Each secret grants FULL app permissions; no granular scoping |

#### Multiple Client Secrets

**Evidence**: [Maximum Allowed Client Secrets (Microsoft Q&A, 2025)](https://learn.microsoft.com/en-us/answers/questions/5655092/clarification-on-maximum-allowed-client-secrets-fo)

- **B2C apps** (personal Microsoft accounts): Max 2 secrets
- **Work/school apps** (single-tenant or multi-tenant): No hard limit, but Microsoft discourages "high counts"
- **Practical limit**: You can create multiple secrets, but each one grants the SAME permissions
- **Audit limitation**: You cannot differentiate which secret was used in logs

**Quote**:
> "If I understand you correctly, you have registered a single application in AAD and for that App Registration, you have created multiple Client Secrets each for a separate application code... In such a setup, it is not possible to figure out which application code actually initiated the request for the token."

#### Secret Lifetime

**Evidence**: [Client Secret Expiration (Microsoft Q&A, 2025)](https://learn.microsoft.com/en-ca/answers/questions/1485134/azure-app-registration-client-secret-expiration)

- **Max lifetime**: 24 months (2 years) via portal
- **Can be extended** via PowerShell/CLI to longer periods (not recommended)
- **Microsoft recommendation**: Rotate every 3-12 months
- **No automatic rotation**: You must manually create new secrets and update the app

**Verdict**: Multiple secrets don't solve the problem. Each one is equally dangerous if compromised.

---

### 4. SECURE ALTERNATIVES (Ranked by Security)

**Confidence: HIGH** (all documented by Microsoft and industry)

#### TIER 1: MOST SECURE (Recommended)

##### **Option 1A: Pre-Signed Upload URLs (SAS Tokens for Azure Blob Storage)**

**How it works**:
1. User clicks "Upload" in desktop app
2. App calls YOUR backend server (not Graph directly)
3. Backend generates a short-lived SAS token (15-60 min expiry)
4. Backend returns SAS URL to app
5. App uploads directly to Azure Blob Storage using SAS URL
6. SAS token expires; attacker cannot reuse it

**Security properties**:
- ✅ No client secret in app
- ✅ No client secret in user's hands
- ✅ Time-limited access (15-60 min)
- ✅ Scope-limited (single blob or container)
- ✅ Can revoke immediately by deleting token
- ✅ Audit trail shows which user requested token

**Evidence**: [SAS Tokens for SharePoint Scenarios (BlobBridge, 2025)](https://www.blobbridge.com/sas-tokens-sharepoint-least-privilege)

> "An over-permissive or expired SAS token is the number one cause of BlobBridge incidents. Keep scope narrow."

**Implementation**:
```python
# Backend generates SAS for user
from azure.storage.blob import BlobSasBuilder, generate_blob_sas_query_parameters

sas_token = generate_blob_sas_query_parameters(
    account_name="myaccount",
    container_name="uploads",
    blob_name=f"user_{user_id}_{timestamp}.json",
    permissions="cw",  # Create, Write only (no Delete, List)
    expiry=datetime.utcnow() + timedelta(minutes=15),
    account_key=account_key
)
```

**Limitation**: Requires Azure Blob Storage, not SharePoint directly. (See Option 1B for SharePoint.)

---

##### **Option 1B: Azure Functions as Proxy/Relay**

**How it works**:
1. User clicks "Upload" in desktop app
2. App sends file + metadata to Azure Function (HTTPS, no auth needed or with API key)
3. Function authenticates to SharePoint using a **server-side client secret** (never exposed to user)
4. Function uploads file to SharePoint
5. Function returns success/failure to app

**Security properties**:
- ✅ No client secret in app or user's hands
- ✅ Client secret stored securely in Azure Key Vault (server-side)
- ✅ Function can validate file content before upload
- ✅ Audit trail shows Function identity, not user
- ✅ Can rate-limit per user
- ⚠️ Function is a single point of failure

**Evidence**: [Azure Function App: Upload Files to SharePoint (2024)](https://powergi.net/blog/azure-function-upload-files-to-sharepoint/)

**Implementation**:
```python
# Azure Function (server-side, secret in Key Vault)
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

async def upload_to_sharepoint(req: func.HttpRequest) -> func.HttpResponse:
    # Get secret from Key Vault (not from user)
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url="https://myvault.vault.azure.net/", credential=credential)
    client_secret = secret_client.get_secret("graph-client-secret").value
    
    # Authenticate to Graph using server-side secret
    token = get_graph_token(client_id, client_secret)
    
    # Upload file
    file_content = req.get_body()
    upload_to_sharepoint_site(token, file_content)
    
    return func.HttpResponse("Upload successful", status_code=200)
```

**Limitation**: Adds infrastructure complexity; requires maintaining Azure Function.

---

##### **Option 1C: User-Based Authentication (Delegated Permissions)**

**How it works**:
1. User clicks "Upload" in desktop app
2. App prompts user to sign in interactively (browser opens)
3. User authenticates with their Microsoft account (MFA, Conditional Access apply)
4. App receives token on behalf of user
5. App uploads file to SharePoint as the user

**Security properties**:
- ✅ No client secret needed
- ✅ MFA enforced (if tenant policy requires it)
- ✅ Conditional Access policies apply
- ✅ Audit trail shows which user uploaded
- ✅ User can revoke access anytime
- ⚠️ Requires users to have Microsoft accounts (your constraint: external users don't have them)

**Evidence**: [Desktop App Configuration (Microsoft Learn)](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration)

**Limitation**: **Does NOT work for your use case** (external users without MS accounts).

---

#### TIER 2: ACCEPTABLE (With Hardening)

##### **Option 2A: Client Credentials Flow + Strict Guardrails**

**If you MUST use client credentials**, apply these hardening measures:

| Hardening Measure | Implementation | Effectiveness |
|---|---|---|
| **Minimal permissions** | Grant only `Sites.Selected` (not `Files.ReadWrite.All`) | HIGH |
| **Site-level scoping** | Use SharePoint site permissions to restrict which site the app can access | HIGH |
| **Short-lived secrets** | Rotate every 3 months (not 2 years) | MEDIUM |
| **Conditional Access for workload identities** | Block app-only auth from unexpected locations | MEDIUM |
| **Audit logging** | Monitor all app-only access in Azure Monitor | MEDIUM |
| **Rate limiting** | Implement throttling in your app | LOW |
| **Secret rotation automation** | Use Azure Automation to rotate secrets automatically | MEDIUM |

**Evidence**: [Client Credentials Flow (Microsoft Learn)](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)

> "Because the application's own credentials are being used, these credentials must be kept safe. Never publish that credential in your source code, embed it in web pages, or use it in a widely distributed native application."

---

### 5. GUARDRAILS FOR CLIENT CREDENTIALS FLOW

**Confidence: HIGH** (Microsoft docs)

#### Can You Restrict Which SharePoint Sites the App Can Access?

**YES, but with limitations**:

| Method | Scope | Effectiveness |
|---|---|---|
| **App-only permissions** (`Sites.Selected`) | Restrict to specific SharePoint sites | HIGH |
| **SharePoint site permissions** | Grant app access only to specific site | HIGH |
| **Conditional Access** | Block app-only auth from certain locations | MEDIUM (doesn't apply to all scenarios) |
| **Resource-based Conditional Access** | Restrict based on resource properties | MEDIUM |

**Evidence**: [Microsoft Entra Security Operations for Applications](https://aka.ms/app-security-operations-guide)

> "Always configure the least privileged set of permissions required by the app."

**Implementation**:
```
1. In Azure Portal: App Registration → API Permissions
2. Add "Sites.Selected" (not "Files.ReadWrite.All")
3. In SharePoint: Site Settings → Site Permissions → Grant app access to THIS site only
4. Result: App can only access that one site
```

---

#### Can You Set Up Conditional Access Policies for App-Only Auth?

**PARTIALLY**:

| Policy Type | Applies to App-Only Auth? | Notes |
|---|---|---|
| **Location-based** | ❌ NO | App-only auth is exempt from location policies |
| **Device compliance** | ❌ NO | Doesn't apply to service principals |
| **MFA** | ❌ NO | App-only auth has no MFA |
| **Authentication flows** | ✅ YES | Can block device code flow, ROPC, etc. |
| **Workload identity CA** | ✅ PARTIAL | New feature; limited support |

**Evidence**: [Authentication Flows as Condition in Conditional Access](https://docs.azure.cn/en-us/entra/identity/conditional-access/concept-authentication-flows)

> "Device code flow is a high-risk authentication method... Configure device code flow control along with other controls in Conditional Access policies."

**Verdict**: Conditional Access provides **minimal protection** for client credentials flow.

---

#### Can You Monitor/Audit App-Only Access Separately?

**YES**:

| Audit Source | What You See | Effectiveness |
|---|---|---|
| **Azure Monitor / Log Analytics** | All Graph API calls by app | HIGH |
| **Microsoft Entra Sign-in Logs** | Service principal sign-ins (app-only tokens) | HIGH |
| **SharePoint Audit Log** | File uploads/modifications by app | HIGH |
| **Microsoft Sentinel** | Anomaly detection on app activity | MEDIUM |

**Evidence**: [Learn About Sign-in Log Activity Details](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-sign-in-log-activity-details)

**Implementation**:
```kusto
// Azure Monitor query: Find all Graph calls by app
AuditLogs
| where OperationName == "Add application"
| where InitiatedBy.app.displayName == "YourAppName"
| summarize count() by OperationName, TimeGenerated
```

**Limitation**: Audit logs show **what** happened, not **who** (user) triggered it if the app is running on user's machine.

---

### 6. COMPARISON: Embedded Secret vs. User-Entered Credential

**Question**: Is there a security difference between:
- A) Embedding the secret in the app binary
- B) Prompting the user to enter a "password" that the app uses as the client secret

**Answer**: **NO meaningful difference from a security perspective.**

| Aspect | Embedded Secret | User-Entered Secret |
|---|---|---|
| **Exposure risk** | Attacker reverse-engineers binary | Attacker intercepts input or reads memory |
| **Reusability** | Attacker can use it indefinitely | Attacker can use it indefinitely |
| **Revocation** | Must rotate in Azure Portal | Must rotate in Azure Portal |
| **Audit trail** | Shows app activity | Shows app activity |
| **User awareness** | User unaware of secret | User aware but doesn't understand risk |
| **Compliance** | Violates Microsoft guidance | Violates Microsoft guidance |

**Verdict**: Both are equally insecure. User-entered credentials give a false sense of security ("the user controls it") but don't actually improve security.

---

### 7. RANKED SECURITY ALTERNATIVES

**From Most Secure to Least**:

| Rank | Approach | Security | Complexity | Cost | Recommendation |
|---|---|---|---|---|---|
| 1 | **Pre-signed SAS URLs** (Azure Blob) | ⭐⭐⭐⭐⭐ | Medium | Low | **BEST for file uploads** |
| 2 | **Azure Functions proxy** | ⭐⭐⭐⭐⭐ | High | Medium | **BEST for SharePoint** |
| 3 | **User-based auth** (delegated) | ⭐⭐⭐⭐⭐ | Low | None | **BEST if users have MS accounts** |
| 4 | **Client credentials + guardrails** | ⭐⭐ | Low | None | **ONLY if alternatives impossible** |
| 5 | **Embedded client secret** | ⭐ | Low | None | **DO NOT USE** |

---

### 8. PRACTICAL HARDENING IF CLIENT CREDENTIALS IS CHOSEN

**If you MUST use client credentials** (not recommended), implement:

```python
# Hardening checklist
1. ✅ Minimal permissions: Sites.Selected (not Files.ReadWrite.All)
2. ✅ Site-level scoping: Grant app access to ONE SharePoint site only
3. ✅ Secret rotation: Every 3 months (not 2 years)
4. ✅ Secure storage: Secret in Azure Key Vault, NOT in app config
5. ✅ Audit logging: Monitor all app-only access in Azure Monitor
6. ✅ Rate limiting: Throttle requests to 10/min per user
7. ✅ Conditional Access: Block from unexpected locations (if supported)
8. ✅ Incident response: Plan for secret compromise (rotation, revocation)
```

**Evidence**: [Security Best Practices for App Registration](https://learn.microsoft.com/en-us/entra/identity-platform/security-best-practices-for-app-registration)

---

### 9. THREAT MODEL FOR YOUR SPECIFIC SCENARIO

**Context**: Medical annotation data (hip landmarks), external research collaborators, low-risk academic setting.

#### Threat Actors

| Actor | Capability | Likelihood | Impact |
|---|---|---|---|
| **Malicious collaborator** | Reverse-engineer app, extract secret | MEDIUM | HIGH (can upload false data, exfiltrate) |
| **Compromised collaborator device** | Malware steals secret from memory | MEDIUM | HIGH |
| **Network attacker** | Intercepts secret in transit | LOW (if HTTPS) | HIGH |
| **Insider threat** | Admin with access to app binary | LOW | CRITICAL |

#### Attack Scenarios

**Scenario 1: Data Integrity**
- Attacker uploads false landmark annotations
- Corrupts research dataset
- Undetected until analysis phase
- **Mitigation**: Audit trail shows app uploaded data; can trace to user

**Scenario 2: Data Exfiltration**
- Attacker uses secret to download all annotations
- Violates research ethics (even if not PHI)
- **Mitigation**: Audit logging; restrict app to upload-only (no read)

**Scenario 3: Persistence**
- Attacker maintains access after being removed from project
- Continues uploading data under app identity
- **Mitigation**: Rotate secret immediately when user leaves

---

### 10. MICROSOFT'S OFFICIAL RECOMMENDATION

**Direct quote from Microsoft Entra security guidance**:

> "If an application is used only as a public or installed client (for example, mobile or desktop apps that are installed on the end user machine), make sure that there are no credentials specified on the application object."

**Translation**: Desktop apps should NOT have client secrets.

**For your use case**, Microsoft recommends:
1. **User-based auth** (if users have MS accounts) ← Not applicable
2. **Proxy service** (Azure Function) ← Applicable
3. **Pre-signed URLs** (SAS tokens) ← Applicable if using Blob Storage

---

### SUMMARY TABLE: Security Implications

| Aspect | Embedded Secret | SAS Tokens | Azure Function | User Auth |
|---|---|---|---|---|
| **Secret exposure risk** | CRITICAL | None | Low (server-side) | None |
| **Attacker can reuse** | Yes, indefinitely | No (time-limited) | No | No |
| **MFA enforced** | No | No | No | Yes |
| **Audit trail shows user** | No | Yes | No | Yes |
| **Microsoft approved** | ❌ NO | ✅ YES | ✅ YES | ✅ YES |
| **Complexity** | Low | Medium | High | Low |

---

### CONFIDENCE LEVELS

| Finding | Confidence | Source |
|---|---|---|
| Desktop apps shouldn't have secrets | **HIGH** | Microsoft official docs |
| Client credentials flow has no MFA/CA | **HIGH** | OAuth 2.0 spec, Microsoft docs |
| SAS tokens are time-limited and scoped | **HIGH** | Azure documentation, industry practice |
| Multiple secrets don't improve security | **HIGH** | Microsoft Q&A, MSAL docs |
| Conditional Access doesn't apply to app-only auth | **MEDIUM** | Microsoft docs (feature still evolving) |
| Audit logging can track app activity | **HIGH** | Azure Monitor, SharePoint audit logs |

---

### FINAL RECOMMENDATION

**For your medical annotation app**:

1. **DO NOT** distribute a client secret to external users
2. **INSTEAD**, use **Azure Functions as a proxy**:
   - User clicks "Upload" in app
   - App sends file to Azure Function (no auth needed, or API key)
   - Function authenticates to SharePoint using server-side secret (in Key Vault)
   - Function uploads file
   - Audit trail shows which user uploaded via Function logs

3. **If using Azure Blob Storage** instead of SharePoint:
   - Use **pre-signed SAS tokens** (15-min expiry)
   - Backend generates token per upload request
   - Much simpler than Functions

4. **If you MUST use client credentials**:
   - Minimal permissions (`Sites.Selected`)
   - Site-level scoping (one SharePoint site only)
   - Rotate every 3 months
   - Monitor audit logs continuously
   - Plan for immediate revocation if compromised

---

**End of Angle 3 Research**
