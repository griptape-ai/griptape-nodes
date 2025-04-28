# Setup for Nodes that use Hugging Face

## Account and Token Creation

!!! info "Overview"

    This guide will walk you through setting up a Hugging Face account, creating an access token, and installing the required models for use with Griptape Nodes.

### 1. Create a new account on Hugging Face

1. Go to [https://huggingface.co/](https://huggingface.co/)
1. Click **Sign Up** in the top-right corner
1. Complete the verification step to prove you're not a robot
1. Create and record your credentials
1. Complete the email verification process

<p align="center">
  <img src="/assets/img/hugging_face/00_HF_MainPage.png" alt="HF Site" width="500"/>
</p>

<p align="center">
  <img src="/assets/img/hugging_face/01_HF_signup.png" alt="Signup" width="300"/>
</p>

### 2. Access Your Account Settings

1. Log in to your Hugging Face account
1. Click on your profile icon in the top right corner
1. Select **Settings** from the dropdown menu (or go directly to [Settings](https://huggingface.co/settings/profile/))

<p align="center">
  <img src="/assets/img/hugging_face/02_HF_Settings.png" alt="Settings" width="500"/>
</p>

### 3. Create an Access Token

!!! warning "Email Verification Required"

    If you encounter issues during token creation, ensure you've verified your email address. Complete the verification process before continuing.

1. Navigate to **Access Tokens** in the settings menu
1. Click **Create new token** in the top right area
1. Select **Read** as the token type for basic access
1. Give your token a descriptive name
1. Copy and securely store your token

<p align="center">
  <img src="/assets/img/hugging_face/03_HF_AccessTokens.png" alt="Access Tokens" width="500"/>
</p>

<p align="center">
  <img src="/assets/img/hugging_face/04_HF_TokenRead.png" alt="Token Read" width="500"/>
</p>

<p align="center">
  <img src="/assets/img/hugging_face/05_HF_SaveToken.png" alt="Save Token" width="500"/>
</p>

!!! danger "Security Notice"

    Your access token is a personal identifier for requests made to Hugging Face services. Never share it with anyone, and take precautions to avoid displaying it in screenshots, videos, or during screen-sharing sessions.

## Install Required Files

Now that you have a token associated with your account, you can install the Hugging Face CLI (Command Line Interface) to interact with Hugging Face from the command line.

### 1. Install the Hugging Face CLI

Open a terminal and run:

```bash
pip install -U "huggingface_hub[cli]"
```

For more information, visit the [official CLI documentation](https://huggingface.co/docs/huggingface_hub/main/en/guides/cli).

### 2. Login with Your Token

In your terminal, authenticate with your access token:

```bash
huggingface-cli login
```

You'll be prompted to enter your token.

### 3. Install Required Models

!!! note "Download Time"

    These model downloads may collectively take 30-50 minutes to complete, depending on your internet connection speed.

Install the following models for use with different Griptape Nodes:

#### For TilingSpandrelPipeline

```bash
huggingface-cli download skbhadra/ClearRealityV1 4x-ClearRealityV1.pth
```

#### For FluxPipeline and TilingFluxImg2ImgPipeline

```bash
huggingface-cli download black-forest-labs/FLUX.1-schnell
```

#### For FLUX.1-dev

```bash
huggingface-cli download black-forest-labs/FLUX.1-dev
```

## Add Your Token to Griptape Nodes settings

!!! info "Overview"

    Now that you've set up your Hugging Face account and installed the required models, you need to configure Griptape Nodes to use your token. This process is straightforward.

### 1. Open the Griptape Nodes Settings Menu

1. Launch Griptape Nodes
1. Look for the **Settings** menu located in the top menu bar (just to the right of File and Edit)
1. Click on **Settings** to open the configuration options

<p align="center">
  <img src="/assets/img/hugging_face/06_GN_Settings.png" alt="Settings Menu" width="500"/>
</p>

### 2. Add your Hugging Face Token in API Keys & Secrets

1. In the Configuration Editor, locate **API Keys and Secrets** in the bottom left
1. Click to expand this section
1. Scroll down to the **HUGGINGFACE_HUB_ACCESS_TOKEN** field
1. Paste your previously created token into this field
1. Close the Configuration Editor to automatically save your settings

<p align="center">
  <img src="/assets/img/hugging_face/07_GN_HFToken.png" alt="Token Configuration" width="500"/>
</p>

!!! success "Setup Complete"

    After completing these steps, the Hugging Face Nodes should be ready to use in Griptape Nodes!
