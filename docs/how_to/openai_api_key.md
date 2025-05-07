# Setup for Nodes that use OpenAI

## Account and API Key Creation

This guide will walk you through setting up an OpenAI account and creating an API key for use with Griptape Nodes.

!!! info

    If you already have an account skip ahead to [Step 2](#2-create-an-api-key)

### 1. Create a new account on OpenAI

1. Go to [https://openai.com/](https://openai.com/)
1. Click **Sign Up** in the top-right corner
1. Complete the registration process

<p align="center">
      <img src="../assets/00_OpenAI_MainPage.png" alt="OpenAI Site" width="500"/>
  </p>

<p align="center">
      <img src="../assets/01_OpenAI_signup.png" alt="Signup" width="300"/>
  </p>

### 2. Create an API Key

1. Go to [https://openai.com/](https://openai.com/)

1. Click on **Log in** in the top right corner, and be sure to select the **API Platform** option

```
<p align="center">
    <img src="../assets/openai_api_key_login_api_platform.png" alt="API login" width="300"/>
</p>
```

1. Log in by whatever method you signed up with.

1. Go to the "Dashboard" area

```
<p align="center">
    <img src="../assets/openai_api_key_dashboard.png" alt="Dashboard" width="500"/>
</p>

!!! warning "Account Verification Required"

    If you encounter issues during key creation, ensure you've verified your account. Complete the verification process before continuing.
```

1. Navigate to the **API Keys** section

```
<p align="center">
  <img src="../assets/03_OpenAI_APIKeys.png" alt="API Keys" width="500"/>
</p>
```

1. Click **Create New Secret Key**

1. Set the key permissions to "Read-Only" if desired

```
<p align="center">
  <img src="../assets/04_OpenAI_CreateKey.png" alt="Create Key" width="500"/>
</p>
```

1. Click **Create Secret Key**. That will bring up a window with your new API key. Read and understand the messages there; this really is the only time you'll be able to see or copy this key.

```
<p align="center">
  <img src="../assets/05_OpenAI_SaveKey.png" alt="Save Key" width="400"/>
</p>
```

1. Copy and securely store your API key

1. Click **Done** to close the key window

!!! danger "Security Notice"

    It is recommended to save this token in a password locker or secure notes app, so you can find it, but also keep it secure.

    Your access token is a personal identifier for requests made to Hugging Face services. Never share it with anyone, and take precautions to avoid displaying it in screenshots, videos, or during screen-sharing sessions.

    Treat it like you would a credit card number.
