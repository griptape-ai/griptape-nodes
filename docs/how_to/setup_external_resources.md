# Set Up External Resources

## Overview

Griptape Nodes integrates with various external services and resources to extend its capabilities. This guide provides an overview of the available integrations and links to detailed setup instructions for each resource.

!!! info "Prerequisites"

    Before setting up external resources, ensure you have:

    - A working installation of Griptape Nodes
    - Internet access to reach the external service endpoints
    - Appropriate permissions to create accounts and access tokens on third-party platforms

## Available Integrations

Griptape Nodes can connect to the following external resources:

### AI and Machine Learning Services

| Service                                 | Description                                                     | Setup Guide                                                          |
| --------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------- |
| [Hugging Face](https://huggingface.co/) | Access to state-of-the-art machine learning models and datasets | [Hugging Face Setup Guide](/nodes/hugging_face/hugging_face_install) |
| OpenAI                                  | Integration with OpenAI's models for various AI capabilities    | Coming soon                                                          |
| Anthropic                               | Access to Claude and other Anthropic AI models                  | Coming soon                                                          |

### Cloud Storage and Processing

| Service              | Description                                          | Setup Guide |
| -------------------- | ---------------------------------------------------- | ----------- |
| AWS S3               | Cloud storage for large datasets and model artifacts | Coming soon |
| Google Cloud Storage | Alternative cloud storage integration                | Coming soon |

### Data Sources and APIs

| Service              | Description                                        | Setup Guide |
| -------------------- | -------------------------------------------------- | ----------- |
| Database Connections | Connect to SQL and NoSQL databases                 | Coming soon |
| REST APIs            | Configure authentication for third-party REST APIs | Coming soon |

## Integration Setup Process

While each integration has its specific requirements, most follow a similar pattern:

1. **Account Creation** - Sign up for an account with the external service
1. **Authentication Setup** - Generate access tokens or API keys
1. **Resource Installation** - Install required models or libraries (if applicable)
1. **Griptape Configuration** - Add credentials to Griptape Nodes settings
1. **Verification** - Test the integration within Griptape Nodes

## Managing External Resources

### Security Best Practices

!!! danger "Security Notice"

    Always follow these security best practices when working with external resources:

    - Never share your access tokens or API keys
    - Regularly rotate credentials according to your organization's security policies
    - Use the minimum required permissions for each integration
    - Consider using environment variables rather than hardcoded credentials
    - Be mindful of usage costs associated with external services

### Troubleshooting Common Issues

If you encounter issues with external integrations:

1. Verify your credentials are correctly entered in Griptape Nodes settings
1. Check that the external service is operational
1. Ensure any required models or files are properly installed
1. Review the service's documentation for any recent changes
1. Check our [FAQ section](../faq.md) for known issues

## Adding New Integrations

As Griptape Nodes evolves, we continue to add support for new external resources. If you need an integration that isn't currently supported:

1. Check our roadmap for upcoming integrations
1. Consider [creating a custom node](making_custom_nodes.md) to interface with the resource
1. Request the integration through our community channels

## Getting Help

If you encounter any issues while setting up external resources, reach out to our community for assistance:

- [Discord Community](https://discord.gg/gnWRz88eym)
- [Griptape Nodes GitHub Repository](https://github.com/griptape-ai/griptape-nodes)
