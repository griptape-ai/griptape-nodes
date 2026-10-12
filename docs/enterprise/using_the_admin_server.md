# Using the Admin Server

Once your [Admin Server](admin_server.md) is up and running, users connect to it from the Griptape Nodes desktop application by activating with a license instead of logging in through Griptape Cloud. This page walks through that flow from the user's perspective.

## Before you start

Each user needs:

- **The Griptape Nodes desktop application** installed.
- **A license key.** These are issued to your organization; users should request one from their organization admin.
- **The Admin Server address.** The URL where your Admin Server is reachable on your network, for example `http://admin.internal.example.com:8080`. Your Admin Server operator can provide this.

## Activate with a license

### 1. Open the license form

Launch the desktop application. On the login screen, instead of signing in with Griptape Cloud, click **Activate with a License**.

![The login screen with the Activate with a License button below the Login or Sign-Up button](../assets/img/enterprise/admin_server-login.png)

### 2. Paste your license key

In the **License Key** field, paste the license key you received from your organization admin.

![The license activation form with the License Key field and Griptape Server Endpoint field](../assets/img/enterprise/admin_server-license_form.png)

### 3. Point at the Admin Server

In the **Griptape Server Endpoint** field, replace the default Griptape Cloud address (`https://cloud.griptape.ai`) with your Admin Server's address:

```text
http://admin.internal.example.com:8080
```

This routes the application's Griptape Cloud API requests through the Admin Server. Downloads from storage, library, and model hosts need separate proxy settings; the endpoint alone does not route them. Your operator can configure [HTTPS traffic routing](admin_server.md#routing-other-https-traffic) for the engine and browser.

![The license form with a license key pasted and the server endpoint pointed at an on-prem Admin Server](../assets/img/enterprise/admin_server-license_filled.png)

### 4. Activate

Click **Activate License**. The application validates the license and launches the engine as normal, taking you to the editor. Licensing, sessions, and permitted Cloud API requests use the configured Admin Server endpoint.

## Reusing a saved license

Licenses you have activated before are remembered. If you log out (or the license is deactivated), the login screen shows a **Saved licenses** section after you click **Activate with a License**. Click **Use** next to a saved license to re-activate it without pasting the key again. The configured server endpoint is also remembered, so you only need to enter the Admin Server address once.

## Troubleshooting

- **Activation fails immediately.** Check that the license key was pasted completely and has not expired. If the key looks right, confirm the **Griptape Server Endpoint** is correct and that the machine can reach it — try opening `http://<admin-server-address>/health` in a browser; a healthy server responds with `{"status":"ok"}`.
- **Activation worked before but fails now.** The license may have expired. Ask your organization admin for a new one.
- **Some features return errors after activating.** If the Admin Server is configured with [forwarding rules](admin_server.md#forwarding), paths that are not permitted are rejected with `403 {"error":"path not permitted"}`. Ask your Admin Server operator whether the feature's routes are allowed to egress.
- **Activation succeeds, but downloads or previews fail.** Ask your operator to check the engine's proxy settings, the browser's proxy settings, and the Admin Server's allowed tunnel destinations. Browser previews need separate proxy configuration from engine downloads. See [HTTPS traffic routing](admin_server.md#routing-other-https-traffic).
- **A download reports `tunnel host not permitted` or `tunnel host unreachable`.** Give your operator the error and the destination host, if shown. These indicate a blocked tunnel destination or a connection failure from the Admin Server, not a license problem. See [Admin Server troubleshooting](admin_server.md#troubleshooting).
- **Everything returns errors.** If every request fails, the Admin Server itself may be unable to reach Griptape Cloud. This is an operator-side issue — see the [Admin Server troubleshooting section](admin_server.md#troubleshooting).
